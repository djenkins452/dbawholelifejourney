# Account Deletion Documentation

## Overview

Whole Life Journey provides users with the ability to permanently delete their account and all associated data. This feature complies with:

- **GDPR Article 17**: Right to erasure ("right to be forgotten")
- **Apple App Store**: Account deletion requirement
- **CCPA**: California Consumer Privacy Act

## User-Facing Process

### Step 1: Information Screen
Located at: `/user/delete-account/`

Users see:
- Warning that action cannot be undone
- Summary of data that will be deleted (with counts)
- List of additional items being deleted
- Option to download their data first
- "Continue to Delete" button

### Step 2: Confirmation Screen
Located at: `/user/delete-account/?step=confirm`

Users must:
1. Enter their password (for identity verification)
2. Optionally select a reason for leaving
3. Optionally confirm they've downloaded their data
4. Check the "I understand" confirmation checkbox
5. Click "Delete My Account Forever"

### Step 3: Deletion & Logout
- Audit record is created (before deletion)
- All user files are deleted from storage
- User account is deleted (CASCADE deletes all related data)
- User is logged out
- Goodbye message is displayed

## Data Deleted

When a user deletes their account, the following is **permanently deleted**:

### User & Authentication
- User account (email, name, password hash)
- UserPreferences (theme, settings, AI preferences)
- WebAuthn credentials (biometric login)
- MFA codes and sessions
- All active sessions

### Journal Module
- All journal entries
- Entry tags
- Soft-deleted entries (restored before final deletion)

### Health Module
- Weight entries
- Steps entries
- Water entries
- Sleep entries
- Fasting windows
- Heart rate entries
- Blood glucose entries
- Blood pressure entries
- Body temperature entries
- Blood oxygen entries
- Workout sessions
- Personal records
- Workout templates
- Medicines and medicine logs
- Food entries and custom foods
- Daily nutrition summaries
- Medical providers and staff
- Cycle settings and logs (menstrual tracking)

### Faith Module
- Prayer requests
- Saved verses
- Faith milestones
- Bible highlights, bookmarks, and study notes
- Reading plans and progress
- Assessment responses

### Life/Organize Module
- Tasks (including recurring tasks)
- Life events
- Projects
- Inventory items and maintenance logs
- Pets
- Recipes
- Documents (files deleted from storage)
- Significant events
- Google Calendar credentials
- Gmail credentials and processed emails

### Purpose/Goals Module
- Annual directions
- Life goals
- Change intentions
- Reflections
- Planning actions
- Habit goals

### AI Module
- AI insights
- AI usage logs
- Assistant conversations and messages
- User state snapshots
- Daily priorities
- Trend analyses
- Reflection prompt queues
- Values guardrail patterns and suggestions

### Billing Module
- Billing profile
- Referral rewards and qualifications
- Credit transactions
- Promo code usage
- VIP promo codes
- Feature suggestions

### Capture Module
- Capture entries (audio files deleted from storage)
- Pending captures

### Mobile Module
- Mobile devices
- Mobile API tokens
- Token exchange codes
- Health ingestion runs

### Core Module
- Tags
- Favorites
- Page views
- Camera scans (images deleted from storage)
- API request logs
- Notifications
- Release note view tracking

### Other
- System announcement dismissals
- User avatar (file deleted from storage)

## Audit Trail

For compliance and fraud detection, the following is **retained** after deletion:

### AccountDeletionAudit Record
- `email_hash`: SHA-256 hash of email (for fraud detection, not reversible)
- `user_id_was`: Original user ID (no longer links to a user)
- `account_created_at`: When the account was created
- `account_deleted_at`: When the account was deleted
- `deletion_method`: How deletion was initiated (user_self_service, admin_request, etc.)
- `ip_hash`: SHA-256 hash of IP address (for fraud detection)
- `deletion_summary`: Counts of deleted records (e.g., {"journal_entries": 50, "weight_entries": 100})
- `reason`: User's stated reason (sanitized of PII)
- `data_exported`: Whether user downloaded their data first

This audit record contains **no personally identifiable information (PII)**. Email and IP are hashed and cannot be reversed.

## Data Export

Users can download their data before deletion:
- Endpoint: `/user/export-data/`
- Format: JSON file
- Includes: All user data from all modules
- Filename: `wlj_data_export_{user_id}_{timestamp}.json`

## Technical Implementation

### Views
- `DeleteAccountView` (`apps/users/views.py`): Handles the deletion flow
- `ExportAccountDataView` (`apps/users/views.py`): Generates data export

### Models
- `AccountDeletionAudit` (`apps/users/models.py`): Audit trail record

### Templates
- `templates/users/delete_account.html`: Two-step deletion UI

### URLs
- `/user/delete-account/`: Delete account flow
- `/user/export-data/`: Download user data

### Cascade Deletion
All user-related models use `ForeignKey(..., on_delete=models.CASCADE)`, so deleting the User automatically deletes all related records.

### File Cleanup
The `_cleanup_user_files()` method explicitly deletes:
- User avatar
- Documents
- Capture recordings (audio files)
- Camera scans (images)

## Security Considerations

1. **Password Required**: Users must enter their password to confirm deletion
2. **Confirmation Checkbox**: Users must explicitly confirm they understand
3. **IP Logging**: IP address is logged (hashed) for fraud detection
4. **Audit Trail**: All deletions are logged for compliance
5. **No Grace Period**: Deletion is immediate and permanent

## Admin Capabilities

Administrators can view AccountDeletionAudit records in the Django admin to:
- Monitor deletion patterns
- Detect potential fraud (same IP/email hash creating multiple accounts)
- Respond to legal requests for deletion records
- Generate compliance reports

## Responding to Data Requests

If asked "What data do you retain after account deletion?":

> "After account deletion, we retain only an anonymized audit record for legal compliance. This record contains:
> - A one-way hash of your email address (cannot be reversed to reveal your email)
> - A one-way hash of your IP address (cannot be reversed)
> - The date your account was created and deleted
> - A count of how many records were deleted (e.g., "50 journal entries")
> - Any reason you provided for leaving (optional and sanitized of personal info)
>
> No personally identifiable information is retained. This audit record exists solely for fraud detection and legal compliance purposes."
