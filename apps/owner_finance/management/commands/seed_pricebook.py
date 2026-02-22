"""Seed LLMPriceBook with current OpenAI pricing."""

from datetime import date

from django.core.management.base import BaseCommand

from apps.owner_finance.models import ThirdPartyVendor, LLMPriceBook


class Command(BaseCommand):
    help = 'Seed LLMPriceBook with current OpenAI model pricing'

    def handle(self, *args, **options):
        openai, _ = ThirdPartyVendor.objects.get_or_create(
            name='OpenAI', defaults={'category': 'LLM'},
        )

        entries = [
            {
                'model_name': 'gpt-4o',
                'effective_start': date(2024, 5, 1),
                'input_cost_per_1m_tokens_usd': '2.50',
                'output_cost_per_1m_tokens_usd': '10.00',
            },
            {
                'model_name': 'gpt-4o-mini',
                'effective_start': date(2024, 7, 1),
                'input_cost_per_1m_tokens_usd': '0.15',
                'output_cost_per_1m_tokens_usd': '0.60',
            },
            {
                'model_name': 'whisper-1',
                'effective_start': date(2024, 1, 1),
                'input_cost_per_1m_tokens_usd': '0.00',
                'output_cost_per_1m_tokens_usd': '0.00',
            },
        ]

        created = 0
        for entry in entries:
            _, was_created = LLMPriceBook.objects.get_or_create(
                vendor=openai,
                model_name=entry['model_name'],
                effective_start=entry['effective_start'],
                defaults={
                    'input_cost_per_1m_tokens_usd': entry['input_cost_per_1m_tokens_usd'],
                    'output_cost_per_1m_tokens_usd': entry['output_cost_per_1m_tokens_usd'],
                    'is_active': True,
                },
            )
            if was_created:
                created += 1
                self.stdout.write(f"  Created: {entry['model_name']}")
            else:
                self.stdout.write(f"  Exists:  {entry['model_name']}")

        self.stdout.write(self.style.SUCCESS(
            f'PriceBook seeded: {created} new, {len(entries) - created} existing'
        ))
