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
            # GPT-4o family
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
            # GPT-4.1 family
            {
                'model_name': 'gpt-4.1',
                'effective_start': date(2025, 4, 1),
                'input_cost_per_1m_tokens_usd': '2.00',
                'output_cost_per_1m_tokens_usd': '8.00',
            },
            {
                'model_name': 'gpt-4.1-mini',
                'effective_start': date(2025, 4, 1),
                'input_cost_per_1m_tokens_usd': '0.40',
                'output_cost_per_1m_tokens_usd': '1.60',
            },
            {
                'model_name': 'gpt-4.1-nano',
                'effective_start': date(2025, 4, 1),
                'input_cost_per_1m_tokens_usd': '0.10',
                'output_cost_per_1m_tokens_usd': '0.40',
            },
            # Reasoning models
            {
                'model_name': 'o3-mini',
                'effective_start': date(2025, 1, 1),
                'input_cost_per_1m_tokens_usd': '1.10',
                'output_cost_per_1m_tokens_usd': '4.40',
            },
            {
                'model_name': 'o4-mini',
                'effective_start': date(2025, 4, 1),
                'input_cost_per_1m_tokens_usd': '1.10',
                'output_cost_per_1m_tokens_usd': '4.40',
            },
            # Audio
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
