"""
Tests for Artifacts as Truth — uploaded artifacts as a first-class, retrievable
Truth Surface. WLJ owns deterministic retrieval/provenance; the model reasons.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.ai.cos_services.domain_entity import get_domain_entity
from apps.capture.models import MultimodalArtifact
from apps.capture.services.artifact_domain_truth import ArtifactDomainTruth
from apps.capture.services.artifact_queries import ArtifactQueries

User = get_user_model()


def _artifact(user, **kw):
    defaults = dict(
        sha256=kw.pop("sha", "x" * 64), content_type="application/pdf", kind="document",
        perception_status=MultimodalArtifact.PERCEPTION_DONE,
    )
    defaults.update(kw)
    return MultimodalArtifact.objects.create(user=user, **defaults)


class ArtifactQueriesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="q@ex.com", password="x")

    def test_search_by_content(self):
        _artifact(self.user, sha="a" * 64, extracted_text="MRI of the lumbar spine: mild disc bulge.",
                  original_filename="scan.pdf")
        _artifact(self.user, sha="b" * 64, extracted_text="Grocery receipt total $42.10",
                  original_filename="receipt.pdf")
        hits = ArtifactQueries.search(self.user, "MRI")
        self.assertEqual(len(hits), 1)
        self.assertIn("lumbar spine", hits[0].extracted_text)

    def test_search_by_filename_and_kind(self):
        _artifact(self.user, sha="c" * 64, original_filename="payroll.xlsx",
                  content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                  extracted_text="", perception_status=MultimodalArtifact.PERCEPTION_UNSUPPORTED)
        self.assertEqual(len(ArtifactQueries.search(self.user, "payroll")), 1)
        _artifact(self.user, sha="d" * 64, kind="image", content_type="image/png", extracted_text="")
        self.assertEqual(len(ArtifactQueries.search(self.user, "image")), 1)

    def test_excludes_duplicate_and_rejected(self):
        _artifact(self.user, sha="e" * 64, status="duplicate")
        _artifact(self.user, sha="f" * 64, status="rejected")
        _artifact(self.user, sha="g" * 64, status="resolved")
        self.assertEqual(len(ArtifactQueries.recent(self.user)), 1)

    def test_last_uploaded(self):
        old = _artifact(self.user, sha="h" * 64, extracted_text="bloodwork panel A")
        MultimodalArtifact.objects.filter(id=old.id).update(
            created_at=timezone.now() - timedelta(days=30))
        _artifact(self.user, sha="i" * 64, extracted_text="something else")
        last_blood = ArtifactQueries.last_uploaded(self.user, query="bloodwork")
        self.assertIsNotNone(last_blood)
        self.assertIn("bloodwork", last_blood.extracted_text)

    def test_counts_by_kind(self):
        _artifact(self.user, sha="j" * 64, kind="document")
        _artifact(self.user, sha="k" * 64, kind="image")
        _artifact(self.user, sha="l" * 64, kind="image")
        counts = ArtifactQueries.counts_by_kind(self.user)
        self.assertEqual(counts.get("image"), 2)
        self.assertEqual(counts.get("document"), 1)


class ArtifactDomainTruthTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="t@ex.com", password="x")

    def test_describe_one_returns_content(self):
        _artifact(self.user, sha="a" * 64, original_filename="mri.pdf", page_count=3,
                  extracted_text="[Page 1]\nMRI: mild disc bulge at L4-L5.")
        ent = ArtifactDomainTruth(self.user).describe_one("MRI")
        self.assertIsNotNone(ent)
        d = ent.to_dict()
        self.assertEqual(d["definition"]["filename"], "mri.pdf")
        self.assertIn("disc bulge", d["performance"]["content"])

    def test_describe_lists_by_kind(self):
        _artifact(self.user, sha="a" * 64, kind="document")
        _artifact(self.user, sha="b" * 64, kind="image", content_type="image/png", extracted_text="")
        docs = ArtifactDomainTruth(self.user).describe("document")
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].kind, "document")

    def test_current_recent_uploads(self):
        _artifact(self.user, sha="a" * 64, kind="document")
        cur = ArtifactDomainTruth(self.user).current("recent_uploads")
        self.assertTrue(cur.present)
        self.assertEqual(cur.value, 1)


class GetDomainEntityTests(TestCase):
    """The CoS retrieval path: get_domain_entity(domain='artifacts', name=...)."""

    def setUp(self):
        self.user = User.objects.create_user(email="e@ex.com", password="x")

    def test_retrieve_mri_by_name(self):
        _artifact(self.user, sha="a" * 64, original_filename="mri-report.pdf",
                  extracted_text="[Page 1]\nMRI IMPRESSION: mild degenerative changes.")
        env = get_domain_entity(self.user, "artifacts", name="MRI")
        self.assertEqual(env["status"], "ready")
        # The extracted content is present so the model can answer "what did it say".
        blob = str(env)
        self.assertIn("degenerative changes", blob)

    def test_owner_scoped(self):
        other = User.objects.create_user(email="o@ex.com", password="x")
        _artifact(other, sha="a" * 64, original_filename="theirs.pdf", extracted_text="secret MRI")
        env = get_domain_entity(self.user, "artifacts", name="MRI")
        self.assertEqual(env["status"], "empty")
