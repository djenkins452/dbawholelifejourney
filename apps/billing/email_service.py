"""
Email service for billing-related notifications.

Sends emails using Django's email backend with HTML templates.
"""

import logging
from datetime import date

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)

DEFAULT_FROM_EMAIL = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@wholelifejourney.com')


def send_billing_email(template_name, subject, recipient_email, context=None):
    """
    Send a billing-related email.

    Args:
        template_name: Name of template in billing/email/ (without .html)
        subject: Email subject line
        recipient_email: Recipient's email address
        context: Template context dict

    Returns:
        Boolean indicating success
    """
    context = context or {}
    context['current_year'] = date.today().year

    try:
        html_content = render_to_string(
            f'billing/email/{template_name}.html',
            context
        )
        text_content = strip_tags(html_content)

        send_mail(
            subject=subject,
            message=text_content,
            from_email=DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            html_message=html_content,
            fail_silently=False,
        )

        logger.info(f"Sent {template_name} email to {recipient_email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send {template_name} email to {recipient_email}: {e}")
        return False


# Convenience functions for each email type

def send_payment_confirmation(user, profile, amount, next_billing_date=None):
    """Send payment confirmation email after successful payment."""
    return send_billing_email(
        'payment_confirmation',
        'Payment Confirmed - Whole Life Journey',
        user.email,
        {
            'user': user,
            'profile': profile,
            'amount': amount,
            'next_billing_date': next_billing_date,
        }
    )


def send_payment_failed(user):
    """Send payment failed notification."""
    return send_billing_email(
        'payment_failed',
        'Payment Issue - Whole Life Journey',
        user.email,
        {'user': user}
    )


def send_referral_signup(referrer, referred_user):
    """Send notification when someone signs up via referral."""
    return send_billing_email(
        'referral_signup',
        'Someone Joined Using Your Link!',
        referrer.email,
        {
            'referrer': referrer,
            'referred_user': referred_user,
        }
    )


def send_referral_converted(referrer, referred_user, new_balance):
    """Send notification when referral becomes paying member."""
    return send_billing_email(
        'referral_converted',
        'You Earned $5!',
        referrer.email,
        {
            'referrer': referrer,
            'referred_user': referred_user,
            'new_balance': new_balance,
        }
    )


def send_referral_quarterly_bonus(founding_member, quarter, referral_count, payout_amount):
    """Send quarterly bonus notification to Founding Member."""
    return send_billing_email(
        'referral_quarterly_bonus',
        f'Quarterly Bonus Earned - {quarter}',
        founding_member.email,
        {
            'founding_member': founding_member,
            'quarter': quarter,
            'referral_count': referral_count,
            'payout_amount': payout_amount,
        }
    )


def send_referral_payout_sent(founding_member, payout_amount, payout_method, payout_reference=None):
    """Send notification when payout is sent."""
    return send_billing_email(
        'referral_payout_sent',
        'Your Payout Has Been Sent',
        founding_member.email,
        {
            'founding_member': founding_member,
            'payout_amount': payout_amount,
            'payout_method': payout_method,
            'payout_reference': payout_reference,
        }
    )


def send_birthday_preview(user, birthday):
    """Send preview email 30 days before 23rd birthday."""
    return send_billing_email(
        'birthday_preview',
        'Your 23rd Birthday is Coming!',
        user.email,
        {
            'user': user,
            'birthday': birthday,
        }
    )


def send_birthday_celebration(user, graduation_date):
    """Send celebration email on 23rd birthday."""
    return send_billing_email(
        'birthday_celebration',
        'Happy 23rd Birthday!',
        user.email,
        {
            'user': user,
            'graduation_date': graduation_date,
        }
    )


def send_graduation_reminder(user, graduation_date):
    """Send reminder 30 days before graduation."""
    return send_billing_email(
        'graduation_reminder',
        'Your Student Rate Ends Soon',
        user.email,
        {
            'user': user,
            'graduation_date': graduation_date,
        }
    )


def send_graduation_complete(user):
    """Send notification when graduation is complete."""
    return send_billing_email(
        'graduation_complete',
        'Welcome to the Adult Plan!',
        user.email,
        {'user': user}
    )


def send_suggestion_received(user, suggestion_text):
    """Send confirmation when suggestion is submitted."""
    return send_billing_email(
        'suggestion_received',
        'Thanks for Your Suggestion!',
        user.email,
        {
            'user': user,
            'suggestion_text': suggestion_text,
        }
    )


def send_suggestion_implemented(user, suggestion_text, reward_amount):
    """Send notification when suggestion is implemented."""
    return send_billing_email(
        'suggestion_implemented',
        'Your Feature Idea is Live!',
        user.email,
        {
            'user': user,
            'suggestion_text': suggestion_text,
            'reward_amount': reward_amount,
        }
    )
