"""
Management command to seed complete sports reference data.

Usage: python manage.py load_sports_data [--clean]

Populates all pro league teams (NFL 32, NBA 30, MLB 30, NHL 32, MLS 29)
and major NCAA programs (Football, Basketball, Baseball).

Fully idempotent — uses get_or_create everywhere. Safe to re-run.
"""
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from apps.sports.models import League, Sport, Team


# ═══════════════════════════════════════════════════════════════════════
# SPORTS
# ═══════════════════════════════════════════════════════════════════════

SPORTS = ["Football", "Basketball", "Baseball", "Hockey", "Soccer"]

# ═══════════════════════════════════════════════════════════════════════
# LEAGUES
# ═══════════════════════════════════════════════════════════════════════

LEAGUES = [
    # Pro
    {"sport": "Football", "name": "National Football League", "abbr": "NFL", "slug": "nfl", "college": False},
    {"sport": "Basketball", "name": "National Basketball Association", "abbr": "NBA", "slug": "nba", "college": False},
    {"sport": "Baseball", "name": "Major League Baseball", "abbr": "MLB", "slug": "mlb", "college": False},
    {"sport": "Hockey", "name": "National Hockey League", "abbr": "NHL", "slug": "nhl", "college": False},
    {"sport": "Soccer", "name": "Major League Soccer", "abbr": "MLS", "slug": "mls", "college": False},
    # College
    {"sport": "Football", "name": "NCAA Football (FBS)", "abbr": "NCAAF", "slug": "ncaaf", "college": True},
    {"sport": "Basketball", "name": "NCAA Men's Basketball", "abbr": "NCAAB", "slug": "ncaab", "college": True},
    {"sport": "Baseball", "name": "NCAA Baseball", "abbr": "NCAABB", "slug": "ncaabb", "college": True},
]

# ═══════════════════════════════════════════════════════════════════════
# TEAMS — Complete pro rosters + top NCAA programs
# Format: (location, name, abbreviation)
# ═══════════════════════════════════════════════════════════════════════

TEAMS = {
    # ───────────────────────────────────────────────────────────────────
    # NFL — 32 teams
    # ───────────────────────────────────────────────────────────────────
    "nfl": [
        # AFC East
        ("Buffalo", "Bills", "BUF"),
        ("Miami", "Dolphins", "MIA"),
        ("New England", "Patriots", "NE"),
        ("New York", "Jets", "NYJ"),
        # AFC North
        ("Baltimore", "Ravens", "BAL"),
        ("Cincinnati", "Bengals", "CIN"),
        ("Cleveland", "Browns", "CLE"),
        ("Pittsburgh", "Steelers", "PIT"),
        # AFC South
        ("Houston", "Texans", "HOU"),
        ("Indianapolis", "Colts", "IND"),
        ("Jacksonville", "Jaguars", "JAX"),
        ("Tennessee", "Titans", "TEN"),
        # AFC West
        ("Denver", "Broncos", "DEN"),
        ("Kansas City", "Chiefs", "KC"),
        ("Las Vegas", "Raiders", "LV"),
        ("Los Angeles", "Chargers", "LAC"),
        # NFC East
        ("Dallas", "Cowboys", "DAL"),
        ("New York", "Giants", "NYG"),
        ("Philadelphia", "Eagles", "PHI"),
        ("Washington", "Commanders", "WAS"),
        # NFC North
        ("Chicago", "Bears", "CHI"),
        ("Detroit", "Lions", "DET"),
        ("Green Bay", "Packers", "GB"),
        ("Minnesota", "Vikings", "MIN"),
        # NFC South
        ("Atlanta", "Falcons", "ATL"),
        ("Carolina", "Panthers", "CAR"),
        ("New Orleans", "Saints", "NO"),
        ("Tampa Bay", "Buccaneers", "TB"),
        # NFC West
        ("Arizona", "Cardinals", "ARI"),
        ("Los Angeles", "Rams", "LAR"),
        ("San Francisco", "49ers", "SF"),
        ("Seattle", "Seahawks", "SEA"),
    ],

    # ───────────────────────────────────────────────────────────────────
    # NBA — 30 teams
    # ───────────────────────────────────────────────────────────────────
    "nba": [
        # Atlantic
        ("Boston", "Celtics", "BOS"),
        ("Brooklyn", "Nets", "BKN"),
        ("New York", "Knicks", "NYK"),
        ("Philadelphia", "76ers", "PHI"),
        ("Toronto", "Raptors", "TOR"),
        # Central
        ("Chicago", "Bulls", "CHI"),
        ("Cleveland", "Cavaliers", "CLE"),
        ("Detroit", "Pistons", "DET"),
        ("Indiana", "Pacers", "IND"),
        ("Milwaukee", "Bucks", "MIL"),
        # Southeast
        ("Atlanta", "Hawks", "ATL"),
        ("Charlotte", "Hornets", "CHA"),
        ("Miami", "Heat", "MIA"),
        ("Orlando", "Magic", "ORL"),
        ("Washington", "Wizards", "WAS"),
        # Northwest
        ("Denver", "Nuggets", "DEN"),
        ("Minnesota", "Timberwolves", "MIN"),
        ("Oklahoma City", "Thunder", "OKC"),
        ("Portland", "Trail Blazers", "POR"),
        ("Utah", "Jazz", "UTA"),
        # Pacific
        ("Golden State", "Warriors", "GSW"),
        ("Los Angeles", "Clippers", "LAC"),
        ("Los Angeles", "Lakers", "LAL"),
        ("Phoenix", "Suns", "PHX"),
        ("Sacramento", "Kings", "SAC"),
        # Southwest
        ("Dallas", "Mavericks", "DAL"),
        ("Houston", "Rockets", "HOU"),
        ("Memphis", "Grizzlies", "MEM"),
        ("New Orleans", "Pelicans", "NOP"),
        ("San Antonio", "Spurs", "SAS"),
    ],

    # ───────────────────────────────────────────────────────────────────
    # MLB — 30 teams
    # ───────────────────────────────────────────────────────────────────
    "mlb": [
        # AL East
        ("Baltimore", "Orioles", "BAL"),
        ("Boston", "Red Sox", "BOS"),
        ("New York", "Yankees", "NYY"),
        ("Tampa Bay", "Rays", "TB"),
        ("Toronto", "Blue Jays", "TOR"),
        # AL Central
        ("Chicago", "White Sox", "CWS"),
        ("Cleveland", "Guardians", "CLE"),
        ("Detroit", "Tigers", "DET"),
        ("Kansas City", "Royals", "KC"),
        ("Minnesota", "Twins", "MIN"),
        # AL West
        ("Houston", "Astros", "HOU"),
        ("Los Angeles", "Angels", "LAA"),
        ("Oakland", "Athletics", "OAK"),
        ("Seattle", "Mariners", "SEA"),
        ("Texas", "Rangers", "TEX"),
        # NL East
        ("Atlanta", "Braves", "ATL"),
        ("Miami", "Marlins", "MIA"),
        ("New York", "Mets", "NYM"),
        ("Philadelphia", "Phillies", "PHI"),
        ("Washington", "Nationals", "WSH"),
        # NL Central
        ("Chicago", "Cubs", "CHC"),
        ("Cincinnati", "Reds", "CIN"),
        ("Milwaukee", "Brewers", "MIL"),
        ("Pittsburgh", "Pirates", "PIT"),
        ("St. Louis", "Cardinals", "STL"),
        # NL West
        ("Arizona", "Diamondbacks", "ARI"),
        ("Colorado", "Rockies", "COL"),
        ("Los Angeles", "Dodgers", "LAD"),
        ("San Diego", "Padres", "SD"),
        ("San Francisco", "Giants", "SFG"),
    ],

    # ───────────────────────────────────────────────────────────────────
    # NHL — 32 teams
    # ───────────────────────────────────────────────────────────────────
    "nhl": [
        # Atlantic
        ("Boston", "Bruins", "BOS"),
        ("Buffalo", "Sabres", "BUF"),
        ("Detroit", "Red Wings", "DET"),
        ("Florida", "Panthers", "FLA"),
        ("Montreal", "Canadiens", "MTL"),
        ("Ottawa", "Senators", "OTT"),
        ("Tampa Bay", "Lightning", "TBL"),
        ("Toronto", "Maple Leafs", "TOR"),
        # Metropolitan
        ("Carolina", "Hurricanes", "CAR"),
        ("Columbus", "Blue Jackets", "CBJ"),
        ("New Jersey", "Devils", "NJD"),
        ("New York", "Islanders", "NYI"),
        ("New York", "Rangers", "NYR"),
        ("Philadelphia", "Flyers", "PHI"),
        ("Pittsburgh", "Penguins", "PIT"),
        ("Washington", "Capitals", "WSH"),
        # Central
        ("Arizona", "Coyotes", "ARI"),
        ("Chicago", "Blackhawks", "CHI"),
        ("Colorado", "Avalanche", "COL"),
        ("Dallas", "Stars", "DAL"),
        ("Minnesota", "Wild", "MIN"),
        ("Nashville", "Predators", "NSH"),
        ("St. Louis", "Blues", "STL"),
        ("Winnipeg", "Jets", "WPG"),
        # Pacific
        ("Anaheim", "Ducks", "ANA"),
        ("Calgary", "Flames", "CGY"),
        ("Edmonton", "Oilers", "EDM"),
        ("Los Angeles", "Kings", "LAK"),
        ("San Jose", "Sharks", "SJS"),
        ("Seattle", "Kraken", "SEA"),
        ("Vancouver", "Canucks", "VAN"),
        ("Vegas", "Golden Knights", "VGK"),
    ],

    # ───────────────────────────────────────────────────────────────────
    # MLS — 29 teams
    # ───────────────────────────────────────────────────────────────────
    "mls": [
        # Eastern Conference
        ("Atlanta", "United FC", "ATL"),
        ("Charlotte", "FC", "CLT"),
        ("Chicago", "Fire FC", "CHI"),
        ("Cincinnati", "FC Cincinnati", "CIN"),
        ("Columbus", "Crew", "CLB"),
        ("D.C.", "United", "DC"),
        ("Inter Miami", "CF", "MIA"),
        ("CF Montreal", "CF Montreal", "MTL"),
        ("Nashville", "SC", "NSH"),
        ("New England", "Revolution", "NE"),
        ("New York", "Red Bulls", "NYRB"),
        ("New York City", "FC", "NYC"),
        ("Orlando City", "SC", "ORL"),
        ("Philadelphia", "Union", "PHI"),
        ("Toronto", "FC", "TOR"),
        # Western Conference
        ("Austin", "FC", "ATX"),
        ("Colorado", "Rapids", "COL"),
        ("FC Dallas", "FC Dallas", "DAL"),
        ("Houston", "Dynamo FC", "HOU"),
        ("LA", "Galaxy", "LAG"),
        ("Los Angeles", "FC", "LAFC"),
        ("Minnesota", "United FC", "MIN"),
        ("Portland", "Timbers", "POR"),
        ("Real Salt Lake", "Real Salt Lake", "RSL"),
        ("San Jose", "Earthquakes", "SJ"),
        ("Seattle", "Sounders FC", "SEA"),
        ("Sporting Kansas City", "Sporting KC", "SKC"),
        ("St. Louis", "City SC", "STL"),
        ("Vancouver", "Whitecaps FC", "VAN"),
    ],

    # ───────────────────────────────────────────────────────────────────
    # NCAA Football (FBS) — Top 40 programs
    # ───────────────────────────────────────────────────────────────────
    "ncaaf": [
        # SEC
        ("Alabama", "Crimson Tide", "ALA"),
        ("Arkansas", "Razorbacks", "ARK"),
        ("Auburn", "Tigers", "AUB"),
        ("Florida", "Gators", "FLA"),
        ("Georgia", "Bulldogs", "UGA"),
        ("Kentucky", "Wildcats", "UK"),
        ("LSU", "Tigers", "LSU"),
        ("Mississippi State", "Bulldogs", "MSU"),
        ("Missouri", "Tigers", "MIZ"),
        ("Ole Miss", "Rebels", "MISS"),
        ("South Carolina", "Gamecocks", "SC"),
        ("Tennessee", "Volunteers", "TENN"),
        ("Texas A&M", "Aggies", "TAMU"),
        ("Vanderbilt", "Commodores", "VAN"),
        ("Oklahoma", "Sooners", "OU"),
        ("Texas", "Longhorns", "TEX"),
        # Big Ten
        ("Illinois", "Fighting Illini", "ILL"),
        ("Indiana", "Hoosiers", "IU"),
        ("Iowa", "Hawkeyes", "IOWA"),
        ("Maryland", "Terrapins", "MD"),
        ("Michigan", "Wolverines", "MICH"),
        ("Michigan State", "Spartans", "MSU2"),
        ("Minnesota", "Golden Gophers", "MINN"),
        ("Nebraska", "Cornhuskers", "NEB"),
        ("Northwestern", "Wildcats", "NW"),
        ("Ohio State", "Buckeyes", "OSU"),
        ("Oregon", "Ducks", "ORE"),
        ("Penn State", "Nittany Lions", "PSU"),
        ("Purdue", "Boilermakers", "PUR"),
        ("Rutgers", "Scarlet Knights", "RUT"),
        ("USC", "Trojans", "USC"),
        ("UCLA", "Bruins", "UCLA"),
        ("Washington", "Huskies", "UW"),
        ("Wisconsin", "Badgers", "WIS"),
        # ACC / Other Power
        ("Clemson", "Tigers", "CLEM"),
        ("Florida State", "Seminoles", "FSU"),
        ("Miami", "Hurricanes", "UM"),
        ("Notre Dame", "Fighting Irish", "ND"),
        ("North Carolina", "Tar Heels", "UNC"),
        ("NC State", "Wolfpack", "NCST"),
    ],

    # ───────────────────────────────────────────────────────────────────
    # NCAA Men's Basketball — Top 40 programs
    # ───────────────────────────────────────────────────────────────────
    "ncaab": [
        # Traditional powers + recent contenders
        ("Kansas", "Jayhawks", "KU"),
        ("Duke", "Blue Devils", "DUKE"),
        ("North Carolina", "Tar Heels", "UNC"),
        ("Kentucky", "Wildcats", "UK"),
        ("Connecticut", "Huskies", "UCON"),
        ("Purdue", "Boilermakers", "PUR"),
        ("Gonzaga", "Bulldogs", "GONZ"),
        ("Villanova", "Wildcats", "NOVA"),
        ("Houston", "Cougars", "HOU"),
        ("Alabama", "Crimson Tide", "ALA"),
        ("Tennessee", "Volunteers", "TENN"),
        ("Arizona", "Wildcats", "ARIZ"),
        ("Baylor", "Bears", "BAY"),
        ("Creighton", "Bluejays", "CRE"),
        ("Indiana", "Hoosiers", "IU"),
        ("Iowa State", "Cyclones", "ISU"),
        ("Marquette", "Golden Eagles", "MARQ"),
        ("Michigan State", "Spartans", "MSU"),
        ("Auburn", "Tigers", "AUB"),
        ("Texas", "Longhorns", "TEX"),
        ("UCLA", "Bruins", "UCLA"),
        ("Virginia", "Cavaliers", "UVA"),
        ("Michigan", "Wolverines", "MICH"),
        ("Florida Atlantic", "Owls", "FAU"),
        ("San Diego State", "Aztecs", "SDSU"),
        ("Arkansas", "Razorbacks", "ARK"),
        ("Illinois", "Fighting Illini", "ILL"),
        ("Miami", "Hurricanes", "UM"),
        ("Ohio State", "Buckeyes", "OSU"),
        ("Oregon", "Ducks", "ORE"),
        ("Syracuse", "Orange", "SYR"),
        ("Louisville", "Cardinals", "LOU"),
        ("Xavier", "Musketeers", "XAV"),
        ("Wisconsin", "Badgers", "WIS"),
        ("Florida", "Gators", "FLA"),
        ("Memphis", "Tigers", "MEM"),
        ("St. John's", "Red Storm", "STJ"),
        ("Georgetown", "Hoyas", "GTWN"),
        ("Texas Tech", "Red Raiders", "TTU"),
        ("NC State", "Wolfpack", "NCST"),
    ],

    # ───────────────────────────────────────────────────────────────────
    # NCAA Baseball — Top 25 programs
    # ───────────────────────────────────────────────────────────────────
    "ncaabb": [
        ("LSU", "Tigers", "LSU"),
        ("Florida", "Gators", "FLA"),
        ("Vanderbilt", "Commodores", "VAN"),
        ("Virginia", "Cavaliers", "UVA"),
        ("Mississippi State", "Bulldogs", "MSU"),
        ("Oregon State", "Beavers", "ORST"),
        ("Texas", "Longhorns", "TEX"),
        ("Stanford", "Cardinal", "STAN"),
        ("Arkansas", "Razorbacks", "ARK"),
        ("Arizona State", "Sun Devils", "ASU"),
        ("Miami", "Hurricanes", "UM"),
        ("Florida State", "Seminoles", "FSU"),
        ("South Carolina", "Gamecocks", "SC"),
        ("Texas A&M", "Aggies", "TAMU"),
        ("Cal State Fullerton", "Titans", "CSUF"),
        ("Coastal Carolina", "Chanticleers", "CCU"),
        ("Ole Miss", "Rebels", "MISS"),
        ("Tennessee", "Volunteers", "TENN"),
        ("Oklahoma", "Sooners", "OU"),
        ("Wake Forest", "Demon Deacons", "WF"),
        ("North Carolina", "Tar Heels", "UNC"),
        ("Georgia", "Bulldogs", "UGA"),
        ("Auburn", "Tigers", "AUB"),
        ("TCU", "Horned Frogs", "TCU"),
        ("Rice", "Owls", "RICE"),
    ],
}


class Command(BaseCommand):
    help = "Seed complete sports, leagues, and teams data. Idempotent — safe to re-run."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clean",
            action="store_true",
            help="Delete all existing sports data before seeding (use with caution)",
        )

    def handle(self, *args, **options):
        if options["clean"]:
            deleted_teams = Team.objects.all().delete()[0]
            deleted_leagues = League.objects.all().delete()[0]
            deleted_sports = Sport.objects.all().delete()[0]
            self.stdout.write(
                self.style.WARNING(
                    f"Cleaned: {deleted_teams} teams, {deleted_leagues} leagues, {deleted_sports} sports"
                )
            )

        created_sports = 0
        created_leagues = 0
        created_teams = 0

        # Create sports
        sport_objects = {}
        for sport_name in SPORTS:
            sport, created = Sport.objects.get_or_create(
                slug=slugify(sport_name),
                defaults={"name": sport_name},
            )
            sport_objects[sport_name] = sport
            if created:
                created_sports += 1

        # Create leagues
        league_objects = {}
        for league_def in LEAGUES:
            sport = sport_objects[league_def["sport"]]
            league, created = League.objects.get_or_create(
                slug=league_def["slug"],
                defaults={
                    "sport": sport,
                    "name": league_def["name"],
                    "abbreviation": league_def["abbr"],
                    "is_college": league_def["college"],
                },
            )
            league_objects[league_def["slug"]] = league
            if created:
                created_leagues += 1

        # Create teams
        for league_slug, team_list in TEAMS.items():
            league = league_objects.get(league_slug)
            if not league:
                self.stdout.write(self.style.WARNING(f"League '{league_slug}' not found, skipping"))
                continue

            for location, name, abbr in team_list:
                _, created = Team.objects.get_or_create(
                    league=league,
                    abbreviation=abbr,
                    defaults={
                        "name": name,
                        "location": location,
                    },
                )
                if created:
                    created_teams += 1

        # Summary
        total_sports = Sport.objects.count()
        total_leagues = League.objects.count()
        total_teams = Team.objects.count()

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Created: {created_sports} sports, {created_leagues} leagues, {created_teams} teams"
        ))
        self.stdout.write(f"Totals:  {total_sports} sports, {total_leagues} leagues, {total_teams} teams")
        self.stdout.write("")

        for league in League.objects.select_related("sport").order_by("sport__name", "name"):
            count = league.teams.count()
            tag = "college" if league.is_college else "pro"
            self.stdout.write(f"  {league.abbreviation:8s} ({tag:7s}) — {count:3d} teams  [{league.sport.name}]")
