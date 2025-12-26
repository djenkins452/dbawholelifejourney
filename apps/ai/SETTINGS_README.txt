# =============================================================================
# AI SETTINGS - Add to your settings.py
# =============================================================================

# OpenAI Configuration
import os

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

# Model to use - gpt-4o-mini is cost-effective, gpt-4o for higher quality
OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')

# =============================================================================
# Add 'apps.ai' to INSTALLED_APPS
# =============================================================================

# INSTALLED_APPS = [
#     ...
#     'apps.ai',
# ]

# =============================================================================
# .env file additions
# =============================================================================

# OPENAI_API_KEY=sk-your-key-here
# OPENAI_MODEL=gpt-4o-mini  # or gpt-4o for higher quality
