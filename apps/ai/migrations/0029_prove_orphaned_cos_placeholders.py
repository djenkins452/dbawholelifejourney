# ==============================================================================
# File: apps/ai/migrations/0029_prove_orphaned_cos_placeholders.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: READ-ONLY production proof of CoS worker process-death.
# ==============================================================================
"""
Production artifact for the navigation/"processing stops" failure.

There is no CLI/SSH to production, so this read-only data migration runs on the
deploy and prints the DB fingerprint of process death to the deploy logs.

An assistant placeholder is created EMPTY (content="", status="processing") at
apps/ai/chatgpt_cos/tasks.py:108, immediately before generate(). Every clean
exit FILLS it: success (:148), soft-time-limit (:161), exception (:170), and the
finally always publishes a terminal status (:173). Therefore a placeholder that
is STILL content="" / status="processing" long past the 110s hard time-limit is
IMPOSSIBLE unless the worker process was hard-killed mid-generate() before any
of those ran — i.e. SIGKILL / OOM / worker-exited-prematurely / missing process.

This migration writes NOTHING. It only counts and prints, including each
orphan's job_id (metadata.request_id) so the exact COS_REQUEST_START can be
cross-checked for a missing COS_REQUEST_FINISH.
"""

from datetime import timedelta

from django.db import migrations


def prove_orphaned_placeholders(apps, schema_editor):
    from django.utils import timezone

    AssistantMessage = apps.get_model("ai", "AssistantMessage")
    now = timezone.now()
    # 10 min is far past the 110s hard time_limit + any conceivable slow run.
    cutoff = now - timedelta(minutes=10)

    orphans = list(
        AssistantMessage.objects.filter(
            role="assistant",
            content="",
            metadata__status="processing",
            created_at__lt=cutoff,
        ).order_by("-created_at")[:50]
    )
    orphan_total = AssistantMessage.objects.filter(
        role="assistant",
        content="",
        metadata__status="processing",
        created_at__lt=cutoff,
    ).count()

    # Contrast: completed answers prove the path works when NOT killed.
    completed_recent = AssistantMessage.objects.filter(
        role="assistant",
        metadata__status="completed",
        created_at__gte=now - timedelta(days=2),
    ).count()

    bar = "=" * 78
    print(bar, flush=True)
    print("[WLJ PROOF] CoS worker process-death fingerprint (read-only)", flush=True)
    print(f"[WLJ PROOF] orphaned placeholders (content='' + status='processing' "
          f"+ age>10m): {orphan_total}", flush=True)
    print(f"[WLJ PROOF] completed assistant answers (last 2d, for contrast): "
          f"{completed_recent}", flush=True)
    print("[WLJ PROOF] An orphan = task ran COS_REQUEST_START, created the empty "
          "placeholder,", flush=True)
    print("[WLJ PROOF] then DIED before success(:148)/soft-limit(:161)/"
          "exception(:170)/finally(:173).", flush=True)
    print("[WLJ PROOF] No clean exit can leave this state -> the process was "
          "hard-killed.", flush=True)
    print("[WLJ PROOF] --- sample orphans (cross-check COS_REQUEST_START/FINISH "
          "by job_id) ---", flush=True)
    for m in orphans:
        md = m.metadata or {}
        age_min = (now - m.created_at).total_seconds() / 60.0
        print(
            f"[WLJ PROOF] job_id={md.get('request_id')} msg_id={m.id} "
            f"conv={m.conversation_id} created={m.created_at.isoformat()} "
            f"age_min={age_min:.1f} content_len={len(m.content or '')} "
            f"cos_path={md.get('cos_path')} status={md.get('status')}",
            flush=True,
        )
    if not orphans:
        print("[WLJ PROOF] (no aged orphans found at deploy time — trigger a "
              "reasoning request, navigate away, then redeploy to capture one)",
              flush=True)
    print(bar, flush=True)


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0028_seed_persona_templates"),
    ]

    operations = [
        migrations.RunPython(
            prove_orphaned_placeholders, migrations.RunPython.noop
        ),
    ]
