"""
Management command to seed sports reference data (sports, leagues, teams).

Usage: python manage.py load_sports_data
"""
import logging

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from apps.sports.models import League, Sport, Team
from apps.sports.services.provider_adapter import FixtureSportsProvider

logger = logging.getLogger(__name__)


LEAGUE_DEFINITIONS = [
    {"sport": "Football", "name": "National Football League", "abbr": "NFL", "slug": "nfl", "college": False},
    {"sport": "Football", "name": "NCAA Football", "abbr": "NCAAF", "slug": "ncaaf", "college": True},
    {"sport": "Basketball", "name": "National Basketball Association", "abbr": "NBA", "slug": "nba", "college": False},
    {"sport": "Basketball", "name": "NCAA Basketball", "abbr": "NCAAB", "slug": "ncaab", "college": True},
    {"sport": "Baseball", "name": "Major League Baseball", "abbr": "MLB", "slug": "mlb", "college": False},
    {"sport": "Baseball", "name": "NCAA Baseball", "abbr": "NCAABB", "slug": "ncaabb", "college": True},
]


class Command(BaseCommand):
    help = "Seed sports, leagues, and teams from fixture data."

    def handle(self, *args, **options):
        provider = FixtureSportsProvider()
        created_sports = 0
        created_leagues = 0
        created_teams = 0

        for league_def in LEAGUE_DEFINITIONS:
            # Create sport
            sport, sport_created = Sport.objects.get_or_create(
                slug=slugify(league_def["sport"]),
                defaults={"name": league_def["sport"]},
            )
            if sport_created:
                created_sports += 1

            # Create league
            league, league_created = League.objects.get_or_create(
                slug=league_def["slug"],
                defaults={
                    "sport": sport,
                    "name": league_def["name"],
                    "abbreviation": league_def["abbr"],
                    "is_college": league_def["college"],
                },
            )
            if league_created:
                created_leagues += 1

            # Create teams from fixture provider
            normalized_teams = provider.fetch_teams(league_def["slug"])
            for nt in normalized_teams:
                _, team_created = Team.objects.get_or_create(
                    league=league,
                    abbreviation=nt.abbreviation,
                    defaults={
                        "name": nt.name,
                        "location": nt.location,
                        "external_id": nt.external_id,
                        "logo_url": nt.logo_url,
                    },
                )
                if team_created:
                    created_teams += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Sports data loaded: {created_sports} sports, "
                f"{created_leagues} leagues, {created_teams} teams"
            )
        )
