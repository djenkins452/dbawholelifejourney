# Bible Reading Plans Reference (Claude Code)

**Roadmap:** `docs/reading_plans_roadmap.md`

An ongoing project to create comprehensive Bible reading plans across multiple categories. Each plan includes:
- Context summaries for each day
- Commentary appropriate to each level
- Reflection prompts

## Quality Standards

- Biblical accuracy (verified Scripture, no assumptions)
- Non-denominational, Bible-based content
- Appropriate complexity per difficulty level
- Pastor review before deployment

## To Continue This Project

1. Read `docs/reading_plans_roadmap.md` for current status
2. Implement the next plan marked as "Next Plan to Implement"
3. After deployment, update the roadmap status
4. Prompt user for confirmation before starting next plan

**Current Status:** Starting with "Jonah: The Reluctant Prophet" (Phase 1)

**Command pattern:** `apps/faith/management/commands/load_<plan>_plan.py`
