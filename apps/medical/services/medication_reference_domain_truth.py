"""
MedicationReferenceDomainTruth — the ONE deterministic producer of authoritative,
IMPERSONAL medication product truth.

Design of record: `docs/WLJ_MEDICATION_INSTRUCTION_TRUTH_INVESTIGATION.md` Part B.

THE OWNERSHIP BOUNDARY (both directions, absolute):
    * `medicine` owns PERSONAL regimen truth — what this person takes, dose, schedule,
      adherence, last taken, their own recorded instructions. It must never serve
      product-label facts.
    * `medication_reference` (this domain) owns AUTHORITATIVE PRODUCT truth — what the
      approved labelling says. It is impersonal and must never serve personal facts:
      nothing here is user-scoped, and no method takes truth from `Intake` beyond the
      already-resolved identity link.
    The two are separate DOMAINS rather than one enriched medication record precisely
    so that `medicine` can never quietly become a second, informal label authority
    (Constitution III.1).

NO NEW RETRIEVAL TOOL. This registers as an ordinary domain in the existing truth
catalog, so the existing `get_entity` tool reaches it (its `domain` enum is derived
from the catalog) with the existing envelope, freshness and confidence.

WLJ NEVER INTERPRETS THE LABEL. `dosage_and_administration` is returned verbatim.
Deciding what it means for a person on a given evening is reasoning, and reasoning
belongs to the model (Constitution I.4).

REQUEST-PATH SAFE. Every read here is one indexed database query. Resolution and
fetching are background-only (`medication_reference.py`, invoked from Celery). A miss
returns an honest unavailable state — it NEVER triggers a live network call.
"""
import logging

from apps.core.truth.domain import DomainTruth, register_domain_truth
from apps.core.truth.entity import CompleteEntity
from apps.core.truth.freshness import CURRENT, MISSING

logger = logging.getLogger(__name__)

_DOMAIN = "medication_reference"

# What WLJ says when it has nothing — an honest, bounded refusal. Never a guess, and
# never a blanket "ask your provider" (the failure class removed in `e360a8e6`).
_UNAVAILABLE_MEANS = (
    "WLJ has no authoritative product labelling for this medication. Say so plainly "
    "and answer what you can from the person's own regimen truth; do NOT supply the "
    "product's instructions from general knowledge and present them as authoritative."
)


@register_domain_truth
class MedicationReferenceDomainTruth(DomainTruth):
    domain = _DOMAIN
    current_metrics = ()
    history_metrics = ()
    entity_types = ("product_label",)

    # -- listing: the labels WLJ actually holds --------------------------------
    def describe(self, entity_type="product_label"):
        if entity_type not in (None, "product_label"):
            raise KeyError(f"{_DOMAIN} cannot describe {entity_type!r} "
                           f"(have {self.entity_types})")
        from apps.medical.models import MedicationProductLabel
        qs = (MedicationProductLabel.objects
              .filter(resolution_state=MedicationProductLabel.RESOLUTION_RESOLVED)
              .order_by("brand_name")[:50])
        return [self._entity(row) for row in qs]

    # -- by name: what the model actually calls --------------------------------
    def describe_one(self, name):
        """Resolve a medication NAME to the authoritative label WLJ already holds.

        The name is matched against labels ALREADY RESOLVED in the background — this
        is a local lookup of a deterministic identity link, never a fresh identity
        resolution and never an outbound call. If nothing is linked, the honest
        unavailable entity is returned rather than nothing, so the model can say WHY
        instead of silently falling back to its own knowledge.
        """
        q = (name or "").strip()
        if not q:
            return None
        from apps.medical.models import MedicationProductLabel

        # 1. Prefer the identity link a background resolve established for a real
        #    Intake — that is the audited, deterministic path.
        setid, note = self._linked_setid(q)
        if setid:
            row = MedicationProductLabel.objects.filter(
                spl_setid=setid,
                resolution_state=MedicationProductLabel.RESOLUTION_RESOLVED).first()
            if row is not None:
                return self._entity(row)

        # 2. Otherwise match a held label by its own brand name. Exact, case-insensitive
        #    only: a substring match is how the wrong product gets attached.
        row = MedicationProductLabel.objects.filter(
            brand_name__iexact=q,
            resolution_state=MedicationProductLabel.RESOLUTION_RESOLVED).first()
        if row is not None:
            return self._entity(row)

        return self._unavailable_entity(q, note)

    # -- helpers ---------------------------------------------------------------
    def _linked_setid(self, name):
        """(setid, note) from the user's own resolved medication link, if any.

        Reading the identity LINK is not serving personal truth: no dose, schedule,
        adherence or history crosses this boundary — only the pointer that says which
        product label applies, plus why resolution refused when it did.
        """
        if self.user is None:
            return "", ""
        try:
            from apps.health.models import Intake
            row = (Intake.objects.filter(user=self.user, name__iexact=name)
                   .values("reference_spl_setid", "reference_identity_confidence")
                   .first())
            if not row:
                return "", ""
            return (row.get("reference_spl_setid") or "",
                    row.get("reference_identity_confidence") or "")
        except Exception:
            logger.warning("%s: identity link lookup failed", _DOMAIN, exc_info=True)
            return "", ""

    def _entity(self, row):
        return CompleteEntity(
            kind="product_label",
            identity=row.brand_name or row.generic_name or row.spl_setid,
            definition={
                "brand_name": row.brand_name or None,
                "generic_name": row.generic_name or None,
                "rxcui": row.rxcui or None,
                "rxcui_term_type": row.rxcui_tty or None,
                "scope": ("IMPERSONAL product labelling — true of this product for "
                          "everyone. It is NOT this person's regimen; their dose, "
                          "schedule, last dose and adherence live in the `medicine` "
                          "domain and must be retrieved separately."),
            },
            status=row.resolution_state,
            plan={
                # The ONE authoritative fact class carried in M1, VERBATIM.
                "dosage_and_administration": row.dosage_and_administration or None,
                "verbatim": True,
                "means": ("The approved labelling's own words, unedited. WLJ does not "
                          "interpret, summarize or condense it — apply it to the "
                          "person's situation yourself, and attribute it."),
            },
            standing={
                "provenance": {
                    "source": row.source,
                    "source_url": row.source_url or None,
                    "spl_setid": row.spl_setid,
                    "spl_version": row.spl_version or None,
                    "effective_time": row.effective_time or None,
                    "published_date": row.published_date or None,
                    "labeler": row.labeler or None,
                    "content_source": row.content_source or None,
                    "retrieved_at": (row.retrieved_at.isoformat()
                                     if row.retrieved_at else None),
                },
                "identity_resolution": {
                    "state": row.resolution_state,
                    "means": ("How WLJ established that THIS label is the right one "
                              "for this product. Only 'resolved' is safe to rely on."),
                },
            },
            freshness=CURRENT,
        )

    def _unavailable_entity(self, name, note):
        """An honest, bounded refusal — the fail-closed contract made visible.

        This is deliberately an ENTITY rather than a None: the difference between
        "WLJ refuses to attach a label it cannot verify" and "no answer" is exactly
        what stops the model quietly substituting its own knowledge.
        """
        state = note or "unresolved"
        return CompleteEntity(
            kind="product_label",
            identity=name,
            definition={"scope": "IMPERSONAL product labelling"},
            status="unavailable",
            plan={"dosage_and_administration": None,
                  "means": _UNAVAILABLE_MEANS},
            standing={"identity_resolution": {
                "state": state,
                "means": ({
                    "unsupported": ("This medication could not be identified as a single "
                                    "branded product. Multi-source generics are not "
                                    "supported yet — WLJ refuses rather than risk "
                                    "attaching another manufacturer's label."),
                    "ambiguous": ("More than one authoritative label could match. WLJ "
                                  "fails closed rather than choose."),
                    "no_label": "No product labelling exists for this item.",
                }.get(state, "WLJ has not resolved an authoritative label for this.")),
            }},
            freshness=MISSING,
        )
