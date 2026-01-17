# Process emails from the Automate folder

Manually trigger the Email Intake Service to check for new emails in the "Automate" folder and create AdminTasks.

## Execution

1. Output: `Checking Automate folder for emails...`

2. Run the management command on Railway:
```bash
curl -s -X POST "https://api.railway.app/graphql/v2" \
  -H "Authorization: Bearer $RAILWAY_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"mutation { serviceInstanceDeploy(serviceId: \"YOUR_SERVICE_ID\", input: { command: \"python manage.py process_email_tasks\" }) { id } }"}'
```

**Alternative - Run locally if you have env vars set:**
```bash
python manage.py process_email_tasks
```

3. Report results:
   - How many emails were found
   - Tasks created (with IDs and titles)
   - Any errors encountered

## What happens when emails are processed

1. **Email found in Automate folder** → AdminTask created
2. **Task location**: Admin Console → "Email Intake" project
3. **Confirmation email** sent to original sender with task ID
4. **Email moved** to "New Requests" folder (out of Automate)

## Where to see results

After processing, go to:
- **Admin Console** → Look for "Email Intake" project
- Or check your email for confirmation messages

## Dry run (preview without creating tasks)

```bash
python manage.py process_email_tasks --dry-run
```

## Authority

Full authority to run the command. No confirmation needed.
