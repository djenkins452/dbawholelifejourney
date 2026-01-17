# Process emails from the Automate folder

Manually trigger the Email Intake Service to check for new emails in the "Automate" folder and create AdminTasks.

## Execution

1. Output: `Checking Automate folder for emails...`

2. Call the API endpoint:
```bash
curl -s -X POST -H "X-Claude-API-Key: a3f8b2c9d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1" "https://wholelifejourney.com/admin-console/api/claude/process-emails/"
```

3. Report results:
   - How many emails were found
   - Tasks created (with IDs and titles)
   - Any errors encountered

## Response format

```json
{
  "success": true,
  "dry_run": false,
  "processed": 3,
  "errors_count": 0,
  "tasks_created": [
    {"id": 123, "title": "Email: Subject line here"}
  ],
  "error_messages": []
}
```

## What happens when emails are processed

1. **Email found in Automate folder** → AdminTask created
2. **Task location**: Admin Console → "Email Intake" project
3. **Confirmation email** sent to original sender with task ID
4. **Email moved** to "New Requests" folder (out of Automate)

## Dry run (preview without creating tasks)

```bash
curl -s -X POST -H "X-Claude-API-Key: a3f8b2c9d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1" "https://wholelifejourney.com/admin-console/api/claude/process-emails/?dry_run=true"
```

## Authority

Full authority to run the command. No confirmation needed.
