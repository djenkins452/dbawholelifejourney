# Whole Life Journey

A personal life operating system built with calm, clarity, and intention.

**Built by Beacon Innovations LLC**

## Overview

Whole Life Journey helps people live with clarity, intention, and steadiness across all areas of life — without pressure or guilt. Unlike single-purpose apps, it integrates journaling, health tracking, and faith (optional) in one calm, connected space.

## Core Philosophy

- **Calm over clever** — Simple, peaceful design
- **Simple over complex** — Easy to use, nothing overwhelming
- **Respect over pressure** — No gamification, no streaks, no guilt
- **Clarity over features** — Focused functionality
- **Reflection over performance** — Growth, not metrics
- **Stewardship over control** — Your data belongs to you

## Features (MVP)

- **Journal** — A safe space for reflection with mood tracking, categories, and prompts
- **Dashboard** — Your calm landing space with daily encouragement
- **Themes** — Five visual themes to match your journey
- **Faith Module** (Optional) — Scripture prompts and faith-aware content

## Tech Stack

- **Backend**: Django 5.x, PostgreSQL
- **Frontend**: Django Templates, HTMX, CSS Custom Properties
- **Authentication**: django-allauth
- **Deployment**: Railway

## Local Development

### Prerequisites

- Python 3.12+
- PostgreSQL (or use SQLite for local dev)
- Git

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/djenkins452/dbawholelifejourney.git
   cd dbawholelifejourney
   ```

2. Create virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create `.env` file:
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

5. Run migrations:
   ```bash
   python manage.py migrate
   ```

6. Load initial data:
   ```bash
   python manage.py loaddata apps/core/fixtures/categories.json
   python manage.py loaddata apps/journal/fixtures/prompts.json
   ```

7. Create superuser:
   ```bash
   python manage.py createsuperuser
   ```

8. Run development server:
   ```bash
   python manage.py runserver
   ```

9. Visit `http://localhost:8000`

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `SECRET_KEY` | Django secret key | Yes |
| `DEBUG` | Debug mode (True/False) | Yes |
| `DATABASE_URL` | PostgreSQL connection URL | Yes (production) |
| `ALLOWED_HOSTS` | Comma-separated list of hosts | Yes (production) |
| `RESEND_API_KEY` | Resend API key for emails | Yes (production) |
| `DEFAULT_FROM_EMAIL` | From address for emails | Yes |

## Deployment (Railway)

1. Connect your GitHub repository to Railway
2. Add PostgreSQL service
3. Set environment variables
4. Deploy!

Railway will automatically:
- Detect the Django app
- Run migrations via `Procfile`
- Collect static files
- Start the Gunicorn server

## Project Structure

```
whole_life_journey/
├── config/              # Django settings and configuration
├── apps/
│   ├── core/           # Shared models, utilities, landing pages
│   ├── users/          # Custom user model, preferences, auth
│   ├── dashboard/      # Dashboard views and tiles
│   └── journal/        # Journal entries, prompts, tags
├── templates/          # HTML templates
├── static/             # CSS, JS, icons
└── requirements.txt
```

## Themes

Five visual themes are available:

1. **Christian Faith** — Peaceful, grounded, spiritually respectful
2. **Sports & Performance** — Goal-driven, disciplined, focused
3. **Animals & Nature** — Warm, calming, emotionally safe
4. **Outdoors & Adventure** — Curious, expansive, journey-focused
5. **Minimal / Life Focus** — Quiet, clear, intentional (default)

## License

Proprietary — Beacon Innovations LLC. All rights reserved.

## Contact

For questions or support, contact Beacon Innovations LLC.
# Force redeploy
