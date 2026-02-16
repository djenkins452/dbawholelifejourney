# Process emails from the Automate folder

Manually trigger the Email Intake Service to check for new emails in the "Automate" folder and create AdminTasks.

## Execution

1. Output: `Checking Automate folder for emails...`

2. Call the API endpoint (processes up to 10 emails per batch to avoid timeouts):
```bash
curl -s -X POST -H "X-Claude-API-Key: $WLJ_CLAUDE_API_KEY" "https://wholelifejourney.com/admin-console/api/claude/process-emails/"
```

3. Check `remaining` in response. If `remaining > 0`, **automatically call again** to process the next batch. Repeat until `remaining` is 0.

4. Report cumulative results:
   - Total emails found and processed across all batches
   - Tasks created (with IDs and titles)
   - Any errors encountered

## Response format

```json
{
  "success": true,
  "dry_run": false,
  "processed": 10,
  "total_found": 46,
  "remaining": 36,
  "errors_count": 0,
  "tasks_created": [
    {"id": 123, "title": "Email: Subject line here"}
  ],
  "error_messages": []
}
```

## Batch processing

Emails are processed in batches of 10 (default) to avoid Cloudflare 524 timeouts. The `remaining` field tells you how many are left. **Loop automatically until remaining is 0.**

To override batch size (max 50):
```bash
curl -s -X POST -H "X-Claude-API-Key: $WLJ_CLAUDE_API_KEY" "https://wholelifejourney.com/admin-console/api/claude/process-emails/?max_emails=20"
```

## What happens when emails are processed

1. **Email found in Automate folder** → AdminTask created
2. **Task location**: Admin Console → "Email Intake" project
3. **Confirmation email** sent to original sender with task ID
4. **Email moved** to "New Requests" folder (out of Automate)

## Dry run (preview without creating tasks)

```bash
curl -s -X POST -H "X-Claude-API-Key: $WLJ_CLAUDE_API_KEY" "https://wholelifejourney.com/admin-console/api/claude/process-emails/?dry_run=true"
```

## Diagnostics (check settings, connection, folder access)

```bash
curl -s -X POST -H "X-Claude-API-Key: $WLJ_CLAUDE_API_KEY" "https://wholelifejourney.com/admin-console/api/claude/process-emails/?diagnose=true"
```

## Authority

Full authority to run the command. No confirmation needed.
