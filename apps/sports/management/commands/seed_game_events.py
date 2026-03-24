"""
Management command to seed realistic upcoming GameEvent data.

Usage: python manage.py seed_game_events [--clear]

Creates scheduled games for the next 5 days across all pro leagues
and in-season college leagues. Uses real teams from the DB.
Idempotent — uses get_or_create keyed on home_team + away_team + start_time.

Safe to re-run. Use --clear to wipe existing games and regenerate fresh.
"""
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.sports.models import GameEvent, League, Team

ET = ZoneInfo("America/New_York")
CT = ZoneInfo("America/Chicago")
PT = ZoneInfo("America/Los_Angeles")


# ═══════════════════════════════════════════════════════════════════════
# MATCHUP DEFINITIONS
# Each entry: (league_slug, home_abbr, away_abbr, day_offset, hour, minute, tz, venue)
# day_offset: 0=today, 1=tomorrow, etc.
# ═══════════════════════════════════════════════════════════════════════

MATCHUPS = [
    # ───────────────────────────────────────────────────────────────
    # MLB — Daily games, typical 7pm ET / 7pm CT / 7pm PT starts
    # ───────────────────────────────────────────────────────────────
    # Today
    ("mlb", "ATL", "LAD", 0, 19, 10, ET, "Truist Park"),
    ("mlb", "NYY", "BOS", 0, 19, 5, ET, "Yankee Stadium"),
    ("mlb", "CHC", "STL", 0, 19, 15, CT, "Wrigley Field"),
    ("mlb", "HOU", "TEX", 0, 19, 10, CT, "Minute Maid Park"),
    ("mlb", "SFG", "SD", 0, 18, 45, PT, "Oracle Park"),
    ("mlb", "SEA", "LAA", 0, 19, 10, PT, "T-Mobile Park"),
    ("mlb", "DET", "CLE", 0, 18, 40, ET, "Comerica Park"),
    ("mlb", "MIL", "CIN", 0, 18, 40, CT, "American Family Field"),
    # Tomorrow
    ("mlb", "LAD", "ATL", 1, 19, 10, PT, "Dodger Stadium"),
    ("mlb", "BOS", "NYY", 1, 19, 10, ET, "Fenway Park"),
    ("mlb", "STL", "CHC", 1, 19, 15, CT, "Busch Stadium"),
    ("mlb", "TB", "TOR", 1, 18, 40, ET, "Tropicana Field"),
    ("mlb", "PHI", "NYM", 1, 19, 5, ET, "Citizens Bank Park"),
    ("mlb", "MIN", "KC", 1, 19, 10, CT, "Target Field"),
    ("mlb", "COL", "ARI", 1, 18, 40, PT, "Coors Field"),
    # Day 2
    ("mlb", "ATL", "LAD", 2, 13, 20, ET, "Truist Park"),
    ("mlb", "NYY", "BOS", 2, 13, 5, ET, "Yankee Stadium"),
    ("mlb", "TEX", "HOU", 2, 19, 5, CT, "Globe Life Field"),
    ("mlb", "BAL", "WSH", 2, 19, 5, ET, "Camden Yards"),
    ("mlb", "OAK", "SFG", 2, 18, 40, PT, "Oakland Coliseum"),
    # Day 3
    ("mlb", "LAD", "SFG", 3, 19, 10, PT, "Dodger Stadium"),
    ("mlb", "BOS", "TB", 3, 19, 10, ET, "Fenway Park"),
    ("mlb", "CHC", "MIL", 3, 14, 20, CT, "Wrigley Field"),
    ("mlb", "ATL", "PHI", 3, 19, 20, ET, "Truist Park"),
    # Day 4
    ("mlb", "NYM", "ATL", 4, 19, 10, ET, "Citi Field"),
    ("mlb", "NYY", "BAL", 4, 19, 5, ET, "Yankee Stadium"),
    ("mlb", "SD", "LAD", 4, 19, 10, PT, "Petco Park"),

    # ───────────────────────────────────────────────────────────────
    # NBA — Playoff-style schedule, every other day
    # ───────────────────────────────────────────────────────────────
    # Today
    ("nba", "BOS", "CLE", 0, 19, 30, ET, "TD Garden"),
    ("nba", "LAL", "DEN", 0, 22, 0, ET, "Crypto.com Arena"),
    ("nba", "OKC", "DAL", 0, 20, 30, CT, "Paycom Center"),
    # Tomorrow
    ("nba", "MIL", "IND", 1, 19, 0, CT, "Fiserv Forum"),
    ("nba", "PHX", "MIN", 1, 22, 0, ET, "Footprint Center"),
    ("nba", "ATL", "CHI", 1, 19, 30, ET, "State Farm Arena"),
    # Day 2
    ("nba", "CLE", "BOS", 2, 20, 0, ET, "Rocket Mortgage FieldHouse"),
    ("nba", "DEN", "LAL", 2, 22, 0, ET, "Ball Arena"),
    ("nba", "DAL", "OKC", 2, 20, 30, CT, "American Airlines Center"),
    # Day 3
    ("nba", "NYK", "PHI", 3, 19, 30, ET, "Madison Square Garden"),
    ("nba", "GSW", "LAC", 3, 22, 0, ET, "Chase Center"),
    # Day 4
    ("nba", "BOS", "CLE", 4, 20, 0, ET, "TD Garden"),
    ("nba", "LAL", "DEN", 4, 21, 30, ET, "Crypto.com Arena"),

    # ───────────────────────────────────────────────────────────────
    # NHL — Playoff-style schedule
    # ───────────────────────────────────────────────────────────────
    # Today
    ("nhl", "FLA", "BOS", 0, 19, 0, ET, "Amerant Bank Arena"),
    ("nhl", "DAL", "COL", 0, 21, 30, CT, "American Airlines Center"),
    ("nhl", "EDM", "VAN", 0, 22, 0, ET, "Rogers Place"),
    # Tomorrow
    ("nhl", "NYR", "CAR", 1, 19, 30, ET, "Madison Square Garden"),
    ("nhl", "WPG", "NSH", 1, 20, 0, CT, "Canada Life Centre"),
    # Day 2
    ("nhl", "BOS", "FLA", 2, 19, 0, ET, "TD Garden"),
    ("nhl", "COL", "DAL", 2, 21, 0, CT, "Ball Arena"),
    ("nhl", "VAN", "EDM", 2, 22, 0, ET, "Rogers Arena"),
    # Day 3
    ("nhl", "CAR", "NYR", 3, 19, 0, ET, "PNC Arena"),
    ("nhl", "NSH", "WPG", 3, 20, 0, CT, "Bridgestone Arena"),
    # Day 4
    ("nhl", "FLA", "BOS", 4, 19, 30, ET, "Amerant Bank Arena"),
    ("nhl", "DAL", "COL", 4, 21, 30, CT, "American Airlines Center"),

    # ───────────────────────────────────────────────────────────────
    # MLS — Weekend-heavy schedule
    # ───────────────────────────────────────────────────────────────
    # Today
    ("mls", "ATL", "MIA", 0, 19, 30, ET, "Mercedes-Benz Stadium"),
    ("mls", "LAFC", "LAG", 0, 22, 0, ET, "BMO Stadium"),
    # Day 1
    ("mls", "SEA", "POR", 1, 19, 30, PT, "Lumen Field"),
    ("mls", "NYC", "NYRB", 1, 17, 0, ET, "Yankee Stadium"),
    # Day 2
    ("mls", "DAL", "HOU", 2, 20, 0, CT, "Toyota Stadium"),
    ("mls", "CLB", "CIN", 2, 19, 30, ET, "Lower.com Field"),
    # Day 3
    ("mls", "ATL", "CLT", 3, 19, 30, ET, "Mercedes-Benz Stadium"),
    ("mls", "MIN", "CHI", 3, 20, 0, CT, "Allianz Field"),
    # Day 4
    ("mls", "PHI", "DC", 4, 19, 30, ET, "Subaru Park"),
    ("mls", "COL", "RSL", 4, 21, 0, CT, "Dick's Sporting Goods Park"),

    # ───────────────────────────────────────────────────────────────
    # NFL — Offseason, but add a few preseason/OTA placeholders?
    # Skip — NFL doesn't play in March. No fake games.
    # ───────────────────────────────────────────────────────────────

    # ───────────────────────────────────────────────────────────────
    # NCAA Baseball — In season, daily games
    # ───────────────────────────────────────────────────────────────
    # Today
    ("ncaabb", "VAN", "LSU", 0, 18, 0, CT, "Hawkins Field"),
    ("ncaabb", "FLA", "TENN", 0, 18, 0, ET, "Florida Ballpark"),
    ("ncaabb", "AUB", "MSU", 0, 18, 30, CT, "Plainsman Park"),
    ("ncaabb", "ALA", "UK", 0, 18, 0, CT, "Sewell-Thomas Stadium"),
    ("ncaabb", "TEX", "OU", 0, 18, 30, CT, "UFCU Disch-Falk Field"),
    ("ncaabb", "MISS", "ARK", 0, 18, 30, CT, "Swayze Field"),
    # Tomorrow
    ("ncaabb", "LSU", "VAN", 1, 14, 0, CT, "Alex Box Stadium"),
    ("ncaabb", "TENN", "FLA", 1, 14, 0, ET, "Lindsey Nelson Stadium"),
    ("ncaabb", "SC", "UGA", 1, 18, 0, ET, "Founders Park"),
    ("ncaabb", "TAMU", "MIZ", 1, 18, 30, CT, "Blue Bell Park"),
    # Day 2
    ("ncaabb", "VAN", "LSU", 2, 13, 0, CT, "Hawkins Field"),
    ("ncaabb", "FLA", "TENN", 2, 13, 0, ET, "Florida Ballpark"),
    ("ncaabb", "MSU", "AUB", 2, 14, 0, CT, "Dudy Noble Field"),
    ("ncaabb", "ARK", "MISS", 2, 14, 0, CT, "Baum-Walker Stadium"),
    # Day 3
    ("ncaabb", "UGA", "SC", 3, 18, 0, ET, "Foley Field"),
    ("ncaabb", "MIZ", "TAMU", 3, 18, 30, CT, "Taylor Stadium"),
    ("ncaabb", "FSU", "CLEM", 3, 18, 0, ET, "Dick Howser Stadium"),
    ("ncaabb", "UNC", "DUKE", 3, 18, 0, ET, "Boshamer Stadium"),
    # Day 4
    ("ncaabb", "LSU", "ALA", 4, 18, 30, CT, "Alex Box Stadium"),
    ("ncaabb", "TENN", "VAN", 4, 18, 0, ET, "Lindsey Nelson Stadium"),
    ("ncaabb", "TEX", "TAMU", 4, 18, 30, CT, "UFCU Disch-Falk Field"),

    # ───────────────────────────────────────────────────────────────
    # NCAA Basketball — Tournament time
    # ───────────────────────────────────────────────────────────────
    # Today
    ("ncaab", "DUKE", "HOU", 0, 19, 9, ET, "State Farm Stadium"),
    ("ncaab", "AUB", "TENN", 0, 21, 49, ET, "State Farm Stadium"),
    # Tomorrow
    ("ncaab", "KU", "GONZ", 1, 18, 9, ET, "Chase Center"),
    ("ncaab", "FLA", "MARQ", 1, 20, 49, ET, "Chase Center"),
    # Day 2 — no games (travel day)
    # Day 3 — Final Four
    ("ncaab", "DUKE", "AUB", 3, 18, 9, ET, "Alamodome"),
    ("ncaab", "KU", "FLA", 3, 20, 49, ET, "Alamodome"),
    # Day 4 — Championship (if applicable)
    # Skip — TBD based on winners

    # ───────────────────────────────────────────────────────────────
    # NCAA Football — Spring games only (offseason)
    # ───────────────────────────────────────────────────────────────
    # Skip — no regular-season games in March
]

# Also seed a few recently completed games for "Last Result"
COMPLETED_MATCHUPS = [
    # MLB — yesterday's results
    ("mlb", "ATL", "NYM", -1, 19, 10, ET, "Truist Park", 5, 3),
    ("mlb", "LAD", "SFG", -1, 19, 10, PT, "Dodger Stadium", 7, 2),
    ("mlb", "NYY", "TOR", -1, 19, 5, ET, "Yankee Stadium", 4, 6),
    ("mlb", "HOU", "SEA", -1, 19, 10, CT, "Minute Maid Park", 8, 1),
    ("mlb", "CHC", "MIL", -1, 14, 20, CT, "Wrigley Field", 3, 5),
    ("mlb", "BOS", "BAL", -1, 19, 10, ET, "Fenway Park", 6, 4),
    # NBA — recent results
    ("nba", "BOS", "MIA", -1, 19, 30, ET, "TD Garden", 112, 98),
    ("nba", "OKC", "LAL", -1, 20, 0, CT, "Paycom Center", 108, 104),
    ("nba", "DAL", "PHX", -2, 20, 30, CT, "American Airlines Center", 115, 109),
    ("nba", "ATL", "MIL", -1, 19, 30, ET, "State Farm Arena", 105, 118),
    # NHL — recent results
    ("nhl", "FLA", "TBL", -1, 19, 0, ET, "Amerant Bank Arena", 4, 2),
    ("nhl", "DAL", "MIN", -1, 20, 0, CT, "American Airlines Center", 3, 1),
    ("nhl", "EDM", "CGY", -2, 21, 0, ET, "Rogers Place", 5, 3),
    # NCAA Baseball — yesterday
    ("ncaabb", "VAN", "ALA", -1, 18, 0, CT, "Hawkins Field", 8, 5),
    ("ncaabb", "LSU", "MISS", -1, 18, 30, CT, "Alex Box Stadium", 6, 3),
    ("ncaabb", "TENN", "SC", -1, 18, 0, ET, "Lindsey Nelson Stadium", 7, 4),
    ("ncaabb", "FLA", "UGA", -1, 18, 0, ET, "Florida Ballpark", 9, 2),
    ("ncaabb", "AUB", "ARK", -1, 18, 30, CT, "Plainsman Park", 4, 7),
    # NCAA Basketball — earlier round results
    ("ncaab", "DUKE", "ALA", -2, 19, 9, ET, "State Farm Stadium", 78, 65),
    ("ncaab", "AUB", "MICH", -2, 21, 49, ET, "State Farm Stadium", 82, 71),
    ("ncaab", "HOU", "PUR", -2, 19, 9, ET, "State Farm Stadium", 68, 63),
    ("ncaab", "TENN", "MARQ", -2, 21, 49, ET, "State Farm Stadium", 75, 72),
]


# ═══════════════════════════════════════════════════════════════════════
# TEAM RECORDS — realistic early-season 2026
# Format: (league_slug, abbreviation): (wins, losses)
# ═══════════════════════════════════════════════════════════════════════

TEAM_RECORDS = {
    # MLB
    ("mlb", "ATL"): (18, 7), ("mlb", "LAD"): (16, 9), ("mlb", "NYY"): (15, 10),
    ("mlb", "BOS"): (14, 11), ("mlb", "HOU"): (17, 8), ("mlb", "CHC"): (12, 13),
    ("mlb", "STL"): (11, 14), ("mlb", "SFG"): (13, 12), ("mlb", "SD"): (14, 11),
    ("mlb", "NYM"): (10, 15), ("mlb", "PHI"): (16, 9), ("mlb", "TB"): (13, 12),
    ("mlb", "SEA"): (12, 13), ("mlb", "TEX"): (11, 14), ("mlb", "BAL"): (15, 10),
    ("mlb", "DET"): (9, 16), ("mlb", "CLE"): (14, 11), ("mlb", "MIL"): (15, 10),
    ("mlb", "CIN"): (10, 15), ("mlb", "MIN"): (13, 12), ("mlb", "KC"): (8, 17),
    ("mlb", "COL"): (7, 18), ("mlb", "ARI"): (12, 13), ("mlb", "OAK"): (6, 19),
    ("mlb", "LAA"): (11, 14), ("mlb", "TOR"): (12, 13), ("mlb", "WSH"): (9, 16),
    ("mlb", "PIT"): (10, 15), ("mlb", "CWS"): (5, 20),
    # NBA
    ("nba", "BOS"): (58, 18), ("nba", "CLE"): (52, 24), ("nba", "OKC"): (55, 21),
    ("nba", "DAL"): (46, 30), ("nba", "LAL"): (44, 32), ("nba", "DEN"): (50, 26),
    ("nba", "ATL"): (38, 38), ("nba", "MIL"): (48, 28), ("nba", "CHI"): (30, 46),
    ("nba", "IND"): (42, 34), ("nba", "PHX"): (40, 36), ("nba", "MIN"): (44, 32),
    ("nba", "NYK"): (46, 30), ("nba", "PHI"): (39, 37), ("nba", "MIA"): (40, 36),
    ("nba", "GSW"): (38, 38), ("nba", "LAC"): (36, 40),
    # NHL
    ("nhl", "FLA"): (48, 20), ("nhl", "BOS"): (44, 24), ("nhl", "DAL"): (46, 22),
    ("nhl", "COL"): (45, 23), ("nhl", "EDM"): (43, 25), ("nhl", "VAN"): (38, 30),
    ("nhl", "NYR"): (42, 26), ("nhl", "CAR"): (44, 24), ("nhl", "WPG"): (40, 28),
    ("nhl", "NSH"): (36, 32), ("nhl", "TBL"): (38, 30), ("nhl", "MIN"): (37, 31),
    ("nhl", "CGY"): (34, 34),
    # MLS (early season)
    ("mls", "ATL"): (5, 2), ("mls", "MIA"): (4, 3), ("mls", "LAFC"): (6, 1),
    ("mls", "LAG"): (4, 3), ("mls", "SEA"): (5, 2), ("mls", "POR"): (3, 4),
    ("mls", "NYC"): (4, 3), ("mls", "NYRB"): (3, 4), ("mls", "DAL"): (3, 4),
    ("mls", "HOU"): (2, 5), ("mls", "CLB"): (4, 3), ("mls", "CIN"): (3, 4),
    ("mls", "CLT"): (2, 5), ("mls", "MIN"): (4, 3), ("mls", "CHI"): (2, 5),
    ("mls", "PHI"): (5, 2), ("mls", "DC"): (1, 6), ("mls", "COL"): (3, 4),
    ("mls", "RSL"): (4, 3),
}

# ═══════════════════════════════════════════════════════════════════════
# PROBABLE PITCHERS — (home_abbr, away_abbr): (home_pitcher, away_pitcher)
# Applied to MLB games only
# ═══════════════════════════════════════════════════════════════════════

PROBABLE_PITCHERS = {
    ("ATL", "LAD"): ("Max Fried", "Yoshinobu Yamamoto"),
    ("NYY", "BOS"): ("Gerrit Cole", "Brayan Bello"),
    ("CHC", "STL"): ("Justin Steele", "Sonny Gray"),
    ("HOU", "TEX"): ("Framber Valdez", "Nathan Eovaldi"),
    ("SFG", "SD"): ("Logan Webb", "Yu Darvish"),
    ("SEA", "LAA"): ("Luis Castillo", "Tyler Anderson"),
    ("DET", "CLE"): ("Tarik Skubal", "Tanner Bibee"),
    ("MIL", "CIN"): ("Freddy Peralta", "Hunter Greene"),
    ("LAD", "ATL"): ("Walker Buehler", "Chris Sale"),
    ("BOS", "NYY"): ("Tanner Houck", "Carlos Rodon"),
    ("STL", "CHC"): ("Miles Mikolas", "Shota Imanaga"),
    ("TB", "TOR"): ("Zack Littell", "Kevin Gausman"),
    ("PHI", "NYM"): ("Zack Wheeler", "Kodai Senga"),
    ("MIN", "KC"): ("Pablo Lopez", "Seth Lugo"),
    ("COL", "ARI"): ("Cal Quantrill", "Zac Gallen"),
    ("BAL", "WSH"): ("Corbin Burnes", "Patrick Corbin"),
    ("OAK", "SFG"): ("JP Sears", "Blake Snell"),
    ("LAD", "SFG"): ("Tyler Glasnow", "Robbie Ray"),
    ("BOS", "TB"): ("Kutter Crawford", "Shane McClanahan"),
    ("ATL", "PHI"): ("Spencer Strider", "Aaron Nola"),
    ("NYM", "ATL"): ("Sean Manaea", "Reynaldo Lopez"),
    ("NYY", "BAL"): ("Marcus Stroman", "Grayson Rodriguez"),
    ("SD", "LAD"): ("Joe Musgrove", "Gavin Stone"),
    ("TEX", "HOU"): ("Jon Gray", "Hunter Brown"),
}


class Command(BaseCommand):
    help = "Seed realistic upcoming GameEvent data, team records, and pitchers."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing GameEvents before seeding",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            deleted = GameEvent.objects.all().delete()[0]
            self.stdout.write(self.style.WARNING(f"Cleared {deleted} existing game events"))

        today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        created_upcoming = 0
        created_completed = 0
        skipped = 0
        errors = 0

        # Build team lookup: (league_slug, abbreviation) → Team
        team_cache = {}
        for team in Team.objects.select_related("league").all():
            key = (team.league.slug, team.abbreviation)
            team_cache[key] = team

        # Seed upcoming games
        for league_slug, home_abbr, away_abbr, day_offset, hour, minute, tz, venue in MATCHUPS:
            home = team_cache.get((league_slug, home_abbr))
            away = team_cache.get((league_slug, away_abbr))
            if not home or not away:
                self.stdout.write(self.style.WARNING(
                    f"  SKIP: {away_abbr} @ {home_abbr} ({league_slug}) — team not found"
                ))
                errors += 1
                continue

            game_day = today + timedelta(days=day_offset)
            start_time = game_day.replace(
                hour=hour, minute=minute, second=0, microsecond=0, tzinfo=tz
            )

            _, created = GameEvent.objects.get_or_create(
                home_team=home,
                away_team=away,
                start_time=start_time,
                defaults={
                    "status": GameEvent.STATUS_SCHEDULED,
                    "venue": venue,
                },
            )
            if created:
                created_upcoming += 1
            else:
                skipped += 1

        # Seed completed games (for "Last Result")
        for entry in COMPLETED_MATCHUPS:
            league_slug, home_abbr, away_abbr, day_offset, hour, minute, tz, venue, home_score, away_score = entry
            home = team_cache.get((league_slug, home_abbr))
            away = team_cache.get((league_slug, away_abbr))
            if not home or not away:
                self.stdout.write(self.style.WARNING(
                    f"  SKIP completed: {away_abbr} @ {home_abbr} ({league_slug}) — team not found"
                ))
                errors += 1
                continue

            game_day = today + timedelta(days=day_offset)
            start_time = game_day.replace(
                hour=hour, minute=minute, second=0, microsecond=0, tzinfo=tz
            )

            _, created = GameEvent.objects.get_or_create(
                home_team=home,
                away_team=away,
                start_time=start_time,
                defaults={
                    "status": GameEvent.STATUS_FINAL,
                    "venue": venue,
                    "home_score": home_score,
                    "away_score": away_score,
                },
            )
            if created:
                created_completed += 1
            else:
                skipped += 1

        # Summary
        total = GameEvent.objects.count()
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Game events seeded: {created_upcoming} upcoming, {created_completed} completed "
            f"({skipped} skipped, {errors} errors)"
        ))
        self.stdout.write(f"Total GameEvents in DB: {total}")
        self.stdout.write("")

        # Show sample by league
        for league in League.objects.filter(is_college=False).order_by("abbreviation"):
            upcoming = GameEvent.objects.filter(
                home_team__league=league,
                status=GameEvent.STATUS_SCHEDULED,
            ).count()
            completed = GameEvent.objects.filter(
                home_team__league=league,
                status=GameEvent.STATUS_FINAL,
            ).count()
            self.stdout.write(f"  {league.abbreviation:6s} — {upcoming} upcoming, {completed} completed")

        for league in League.objects.filter(is_college=True).order_by("abbreviation"):
            upcoming = GameEvent.objects.filter(
                home_team__league=league,
                status=GameEvent.STATUS_SCHEDULED,
            ).count()
            completed = GameEvent.objects.filter(
                home_team__league=league,
                status=GameEvent.STATUS_FINAL,
            ).count()
            if upcoming + completed > 0:
                self.stdout.write(f"  {league.abbreviation:6s} — {upcoming} upcoming, {completed} completed")

        # Seed team records
        records_updated = 0
        for (league_slug, abbr), (wins, losses) in TEAM_RECORDS.items():
            count = Team.objects.filter(
                league__slug=league_slug, abbreviation=abbr
            ).exclude(wins=wins, losses=losses).update(wins=wins, losses=losses)
            records_updated += count
        if records_updated:
            self.stdout.write(f"\n  Updated {records_updated} team records")

        # Seed probable pitchers on MLB games
        pitchers_set = 0
        for (home_abbr, away_abbr), (hp, ap) in PROBABLE_PITCHERS.items():
            count = GameEvent.objects.filter(
                home_team__abbreviation=home_abbr,
                away_team__abbreviation=away_abbr,
                home_team__league__slug="mlb",
                home_probable_pitcher="",
            ).update(home_probable_pitcher=hp, away_probable_pitcher=ap)
            pitchers_set += count
        if pitchers_set:
            self.stdout.write(f"  Set pitchers on {pitchers_set} MLB games")
