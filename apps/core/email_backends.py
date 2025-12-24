"""
Custom Email Backend for Resend.

Resend is a modern email API that's simple to use and has a generous free tier.
This backend integrates Resend with Django's email system.
"""

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class ResendEmailBackend(BaseEmailBackend):
    """
    Email backend that sends emails using Resend API.
    
    Requires RESEND_API_KEY to be set in settings.
    """

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = getattr(settings, "RESEND_API_KEY", None)

    def send_messages(self, email_messages):
        """
        Send one or more EmailMessage objects and return the number of
        email messages sent.
        """
        if not self.api_key:
            if not self.fail_silently:
                raise ValueError("RESEND_API_KEY is not configured")
            return 0

        try:
            import resend
            resend.api_key = self.api_key
        except ImportError:
            if not self.fail_silently:
                raise ImportError("resend package is not installed")
            return 0

        num_sent = 0
        for message in email_messages:
            try:
                # Build the email parameters
                params = {
                    "from": message.from_email or settings.DEFAULT_FROM_EMAIL,
                    "to": list(message.to),
                    "subject": message.subject,
                }

                # Handle HTML vs plain text
                if message.content_subtype == "html":
                    params["html"] = message.body
                else:
                    params["text"] = message.body

                # Add CC and BCC if present
                if message.cc:
                    params["cc"] = list(message.cc)
                if message.bcc:
                    params["bcc"] = list(message.bcc)

                # Add reply-to if present
                if message.reply_to:
                    params["reply_to"] = message.reply_to[0]

                # Send the email
                resend.Emails.send(params)
                num_sent += 1

            except Exception as e:
                if not self.fail_silently:
                    raise e

        return num_sent
