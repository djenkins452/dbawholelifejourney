# Troubleshoot a problem

model: haiku

## Instructions

Read the troubleshooting guide: `docs/wlj_claude_troubleshoot.md`

## Known Issues Covered

1. Property shadowing database fields (FieldError)
2. Railway migration state issues (missing columns)
3. Railway Nixpacks caching (Procfile changes ignored)
4. Test users require onboarding (302 redirects)
5. CSRF trusted origins (Origin checking failed)
6. PostgreSQL schema checks (table_schema = 'public')

## Process

1. Read the user's error message or problem description
2. Match against known issues in the troubleshooting guide
3. If match found: provide the documented solution
4. If no match: suggest diagnostic steps

## Output Format

**Issue Identified:** [Name of known issue or "Unknown"]

**Solution:**
[Steps to fix]

**Prevention:**
[How to avoid in future]
