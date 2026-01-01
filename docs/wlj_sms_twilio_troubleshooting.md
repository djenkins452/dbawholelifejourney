# ==============================================================================
# File: docs/wlj_sms_twilio_troubleshooting.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Twilio SMS troubleshooting history and investigation notes
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-31
# Last Updated: 2025-12-31
# ==============================================================================

# Twilio SMS Troubleshooting

## Issue Summary

SMS notifications are failing to send via Twilio. Multiple errors have been encountered and partially resolved.

**Status:** UNRESOLVED - Suspected cause identified but not confirmed.

---

## Error Timeline

### Error 1: Twilio Error 21212 (RESOLVED)

**Timestamp:** 2:33am UTC 2026-Jan-01 (9:33pm EST Dec 31)

**Error Message:** "The 'From' parameter you supplied was not a valid phone number, Alphanumeric Sender ID or approved WhatsApp Sender."

**Cause:** `TWILIO_PHONE_NUMBER` environment variable in Railway was set to `14233094701` without the `+` prefix.

**Fix Applied:**
- Added phone number normalization to `apps/sms/services.py`
- `_normalize_phone_number()` method auto-converts:
  - `14233094701` → `+14233094701`
  - `4233094701` → `+14233094701`
  - Removes formatting chars (spaces, dashes, parens)
- Added detailed error logging for Twilio errors
- Added 6 new tests for phone normalization

**Files Modified:**
- `apps/sms/services.py`
- `apps/sms/tests/test_sms_comprehensive.py`

**Commit:** `8c09d6d` - "Fix Twilio Error 21212 - Add phone number validation and normalization"

---

### Error 2: Twilio Error 21659 (UNRESOLVED)

**Timestamp:** 3:02am UTC 2026-Jan-01 (10:02pm EST Dec 31)

**Error Message:** "You can only send SMS messages from a phone number, Alphanumeric Sender ID or short code provided by or ported to Twilio."

**Error Code:** 21659

**Resource SID:** SM88bfabebf3f41c4415c7dbb67262a72a

**Configuration at time of error:**
- `TWILIO_PHONE_NUMBER`: `+14233094701` (From number)
- User's verified phone: `+14233094702` (To number)
- Both numbers appear in Twilio Console under "Verified Caller IDs"
- Account is a Trial Account ($15.37 balance shown)

---

## Investigation Notes

### What We Know

1. **Phone number format is now correct** - Error 21212 was resolved by adding the `+` prefix via normalization code.

2. **Both numbers are in Twilio's "Verified Caller IDs":**
   - `+1 423 309 4701` - Configured as TWILIO_PHONE_NUMBER (From)
   - `+1 423 309 4702` - User's personal phone (To)

3. **The numbers are suspiciously similar** - They differ by only one digit (4701 vs 4702), suggesting they may both be personal phone numbers rather than Twilio-purchased numbers.

4. **Error 21659 specifically states:** "from a phone number... **provided by or ported to Twilio**"

### Suspected Root Cause

**The `+14233094701` number is likely NOT a Twilio-purchased phone number.**

In Twilio, there's a critical distinction:
- **Verified Caller IDs:** Numbers you OWN that you've verified with Twilio (for caller ID purposes, receiving SMS/calls)
- **Active/Purchased Numbers:** Numbers you've BOUGHT from Twilio (~$1.15/month) that can SEND SMS

You cannot send SMS FROM a Verified Caller ID - you can only send FROM:
1. A phone number purchased from Twilio
2. A number ported TO Twilio
3. An alphanumeric sender ID (SMS only, limited countries)
4. A short code

### Action Required

**Check Twilio Console:**
1. Go to: **Phone Numbers** → **Manage** → **Active Numbers**
2. Verify if `+14233094701` is listed as an **Active Number** (purchased)
3. If NOT listed there, you need to **Buy a Number** from Twilio with SMS capability

**To Buy a Twilio Number:**
1. Twilio Console → Phone Numbers → Buy a Number
2. Search for numbers in your area (423 area code for Tennessee)
3. Ensure "SMS" capability is checked
4. Purchase (~$1.15/month)
5. Update Railway's `TWILIO_PHONE_NUMBER` to the new purchased number

---

## Current Configuration

### Railway Environment Variables
```
TWILIO_ACCOUNT_SID=*******
TWILIO_AUTH_TOKEN=*******
TWILIO_PHONE_NUMBER=14233094701  (should be +14233094701 or new purchased number)
TWILIO_VERIFY_SERVICE_SID=*******
TWILIO_TEST_MODE=False (production)
SMS_TRIGGER_TOKEN=*******
```

### User's SMS Settings (in WLJ app)
- Phone Number: `+14233094702`
- Phone Verified: Yes (verified via Twilio Verify service)
- SMS Enabled: Yes
- SMS Consent: Granted
- Medicine Reminders: Enabled

---

## Code Changes Made (Session: SMS Error Handling)

### Files Modified

1. **`apps/sms/services.py`**
   - Added `E164_PATTERN` regex for phone validation
   - Added `_normalize_phone_number()` method
   - Updated `__init__()` to validate phone at startup
   - Updated `send_sms()` with:
     - Detailed configuration error messages
     - Destination phone normalization
     - Specific error messages for 21212/21211 errors
     - Better logging with From/To values

2. **`apps/sms/tests/test_sms_comprehensive.py`**
   - Added `TwilioServicePhoneNormalizationTests` class
   - 6 new tests covering E.164 format, US number conversion, formatting removal

3. **`docs/wlj_claude_changelog.md`**
   - Documented Error 21212 fix

4. **`docs/wlj_claude_features.md`**
   - Added "Phone Number Normalization" section to SMS documentation

### Test Results
- SMS tests: 46/46 passing
- All normalization tests passing

---

## References

- [Twilio Error 21212](https://www.twilio.com/docs/api/errors/21212) - Invalid 'From' Phone Number
- [Twilio Error 21659](https://www.twilio.com/docs/api/errors/21659) - Number not provided by Twilio
- [Twilio E.164 Format](https://www.twilio.com/docs/glossary/what-e164)
- [Twilio Verified Caller IDs](https://support.twilio.com/hc/en-us/articles/223180048)
- [Buy a Twilio Phone Number](https://www.twilio.com/console/phone-numbers/search)

---

## Next Steps

1. [ ] Verify in Twilio Console if `+14233094701` is an Active (purchased) number
2. [ ] If not, purchase a Twilio phone number with SMS capability
3. [ ] Update `TWILIO_PHONE_NUMBER` in Railway with the purchased number
4. [ ] Test SMS sending again
5. [ ] Update this document with resolution

---

*Last Updated: 2025-12-31 ~10:30pm EST*
