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
    # NCAA Baseball D1 — All conferences
    # ───────────────────────────────────────────────────────────────────
    "ncaabb": [
        # === SEC (16 teams) ===
        ("Alabama", "Crimson Tide", "ALA"),
        ("Arkansas", "Razorbacks", "ARK"),
        ("Auburn", "Tigers", "AUB"),
        ("Florida", "Gators", "FLA"),
        ("Georgia", "Bulldogs", "UGA"),
        ("Kentucky", "Wildcats", "UK"),
        ("LSU", "Tigers", "LSU"),
        ("Mississippi State", "Bulldogs", "MSU"),
        ("Missouri", "Tigers", "MIZ"),
        ("Oklahoma", "Sooners", "OU"),
        ("Ole Miss", "Rebels", "MISS"),
        ("South Carolina", "Gamecocks", "SC"),
        ("Tennessee", "Volunteers", "TENN"),
        ("Texas", "Longhorns", "TEX"),
        ("Texas A&M", "Aggies", "TAMU"),
        ("Vanderbilt", "Commodores", "VAN"),
        # === ACC (17 teams) ===
        ("Boston College", "Eagles", "BC"),
        ("California", "Golden Bears", "CAL"),
        ("Clemson", "Tigers", "CLEM"),
        ("Duke", "Blue Devils", "DUKE"),
        ("Florida State", "Seminoles", "FSU"),
        ("Georgia Tech", "Yellow Jackets", "GT"),
        ("Louisville", "Cardinals", "LOU"),
        ("Miami", "Hurricanes", "UM"),
        ("North Carolina", "Tar Heels", "UNC"),
        ("NC State", "Wolfpack", "NCST"),
        ("Notre Dame", "Fighting Irish", "ND"),
        ("Pittsburgh", "Panthers", "PITT"),
        ("SMU", "Mustangs", "SMU"),
        ("Stanford", "Cardinal", "STAN"),
        ("Syracuse", "Orange", "SYR"),
        ("Virginia", "Cavaliers", "UVA"),
        ("Virginia Tech", "Hokies", "VT"),
        ("Wake Forest", "Demon Deacons", "WF"),
        # === Big 12 (16 teams) ===
        ("Arizona", "Wildcats", "ARIZ"),
        ("Arizona State", "Sun Devils", "ASU"),
        ("Baylor", "Bears", "BAY"),
        ("BYU", "Cougars", "BYU"),
        ("Cincinnati", "Bearcats", "CIN"),
        ("Colorado", "Buffaloes", "COL"),
        ("Houston", "Cougars", "HOU"),
        ("Iowa State", "Cyclones", "ISU"),
        ("Kansas", "Jayhawks", "KU"),
        ("Kansas State", "Wildcats", "KST"),
        ("Oklahoma State", "Cowboys", "OKST"),
        ("TCU", "Horned Frogs", "TCU"),
        ("Texas Tech", "Red Raiders", "TTU"),
        ("UCF", "Knights", "UCF"),
        ("Utah", "Utes", "UTAH"),
        ("West Virginia", "Mountaineers", "WVU"),
        # === Big Ten (15 teams — no football-only schools) ===
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
        ("Oregon State", "Beavers", "ORST"),
        ("Penn State", "Nittany Lions", "PSU"),
        ("Purdue", "Boilermakers", "PUR"),
        ("Rutgers", "Scarlet Knights", "RUT"),
        ("Washington", "Huskies", "UW"),
        # === American Athletic (14 teams) ===
        ("Charlotte", "49ers", "CLT"),
        ("East Carolina", "Pirates", "ECU"),
        ("Florida Atlantic", "Owls", "FAU"),
        ("Memphis", "Tigers", "MEM"),
        ("Navy", "Midshipmen", "NAVY"),
        ("North Texas", "Mean Green", "UNT"),
        ("Rice", "Owls", "RICE"),
        ("South Florida", "Bulls", "USF"),
        ("Temple", "Owls", "TEM"),
        ("Tulane", "Green Wave", "TUL"),
        ("Tulsa", "Golden Hurricane", "TLSA"),
        ("UAB", "Blazers", "UAB"),
        ("UTSA", "Roadrunners", "UTSA"),
        ("Wichita State", "Shockers", "WICH"),
        # === Sun Belt (14 teams) ===
        ("Appalachian State", "Mountaineers", "APP"),
        ("Arkansas State", "Red Wolves", "ARST"),
        ("Coastal Carolina", "Chanticleers", "CCU"),
        ("Georgia Southern", "Eagles", "GASO"),
        ("Georgia State", "Panthers", "GAST"),
        ("James Madison", "Dukes", "JMU"),
        ("Louisiana", "Ragin' Cajuns", "ULL"),
        ("Louisiana-Monroe", "Warhawks", "ULM"),
        ("Marshall", "Thundering Herd", "MRSH"),
        ("Old Dominion", "Monarchs", "ODU"),
        ("South Alabama", "Jaguars", "USA"),
        ("Southern Miss", "Golden Eagles", "USM"),
        ("Texas State", "Bobcats", "TXST"),
        ("Troy", "Trojans", "TROY"),
        # === Conference USA (10 teams) ===
        ("FIU", "Panthers", "FIU"),
        ("Jacksonville State", "Gamecocks", "JVST"),
        ("Kennesaw State", "Owls", "KSU"),
        ("Liberty", "Flames", "LIB"),
        ("Louisiana Tech", "Bulldogs", "LT"),
        ("Middle Tennessee", "Blue Raiders", "MTSU"),
        ("New Mexico State", "Aggies", "NMSU"),
        ("Sam Houston", "Bearkats", "SHSU"),
        ("UT Arlington", "Mavericks", "UTA"),
        ("Western Kentucky", "Hilltoppers", "WKU"),
        # === Mountain West (8 teams) ===
        ("Air Force", "Falcons", "AF"),
        ("Fresno State", "Bulldogs", "FRES"),
        ("Nevada", "Wolf Pack", "NEV"),
        ("New Mexico", "Lobos", "UNM"),
        ("San Diego State", "Aztecs", "SDSU"),
        ("San Jose State", "Spartans", "SJSU"),
        ("UNLV", "Rebels", "UNLV"),
        ("Utah State", "Aggies", "USU"),
        # === West Coast (8 teams) ===
        ("Gonzaga", "Bulldogs", "GONZ"),
        ("Loyola Marymount", "Lions", "LMU"),
        ("Pacific", "Tigers", "PAC"),
        ("Pepperdine", "Waves", "PEP"),
        ("Portland", "Pilots", "PORT"),
        ("Saint Mary's", "Gaels", "SMC"),
        ("San Francisco", "Dons", "SFU"),
        ("Santa Clara", "Broncos", "SCU"),
        # === Missouri Valley (10 teams) ===
        ("Dallas Baptist", "Patriots", "DBU"),
        ("Evansville", "Purple Aces", "EVAN"),
        ("Illinois State", "Redbirds", "ILST"),
        ("Indiana State", "Sycamores", "INST"),
        ("Missouri State", "Bears", "MOST"),
        ("Southern Illinois", "Salukis", "SIU"),
        ("UIC", "Flames", "UIC"),
        ("Valparaiso", "Beacons", "VAL"),
        ("Belmont", "Bruins", "BELM"),
        ("Murray State", "Racers", "MURR"),
        # === Colonial Athletic (10 teams) ===
        ("College of Charleston", "Cougars", "COFC"),
        ("Delaware", "Blue Hens", "DEL"),
        ("Drexel", "Dragons", "DREX"),
        ("Elon", "Phoenix", "ELON"),
        ("Hofstra", "Pride", "HOF"),
        ("Monmouth", "Hawks", "MON"),
        ("Northeastern", "Huskies", "NEU"),
        ("Stony Brook", "Seawolves", "SBU"),
        ("Towson", "Tigers", "TOW"),
        ("UNC Wilmington", "Seahawks", "UNCW"),
        ("William & Mary", "Tribe", "WM"),
        # === Big East (10 teams) ===
        ("Butler", "Bulldogs", "BUT"),
        ("Connecticut", "Huskies", "UCON"),
        ("Creighton", "Bluejays", "CRE"),
        ("Georgetown", "Hoyas", "GTWN"),
        ("Providence", "Friars", "PROV"),
        ("Seton Hall", "Pirates", "SH"),
        ("St. John's", "Red Storm", "STJ"),
        ("Villanova", "Wildcats", "NOVA"),
        ("Xavier", "Musketeers", "XAV"),
        # === Atlantic 10 (13 teams) ===
        ("Dayton", "Flyers", "DAY"),
        ("Davidson", "Wildcats", "DVSN"),
        ("Fordham", "Rams", "FOR"),
        ("George Mason", "Patriots", "GMU"),
        ("George Washington", "Revolutionaries", "GWU"),
        ("La Salle", "Explorers", "LAS"),
        ("Massachusetts", "Minutemen", "UMASS"),
        ("Rhode Island", "Rams", "URI"),
        ("Richmond", "Spiders", "RICH"),
        ("Saint Louis", "Billikens", "SLU"),
        ("St. Bonaventure", "Bonnies", "SBN"),
        ("St. Joseph's", "Hawks", "STJO"),
        ("VCU", "Rams", "VCU"),
        # === Southeastern (ASUN) (12 teams) ===
        ("Bellarmine", "Knights", "BELL"),
        ("Central Arkansas", "Bears", "UCA"),
        ("Eastern Kentucky", "Colonels", "EKU"),
        ("Florida Gulf Coast", "Eagles", "FGCU"),
        ("Jacksonville", "Dolphins", "JU"),
        ("Lipscomb", "Bisons", "LIP"),
        ("North Alabama", "Lions", "UNA"),
        ("North Florida", "Ospreys", "UNF"),
        ("Queens", "Royals", "QU"),
        ("Stetson", "Hatters", "STET"),
        # === Southern (12 teams) ===
        ("The Citadel", "Bulldogs", "CIT"),
        ("East Tennessee State", "Buccaneers", "ETSU"),
        ("Furman", "Paladins", "FUR"),
        ("Mercer", "Bears", "MER"),
        ("Samford", "Bulldogs", "SAM"),
        ("UNC Greensboro", "Spartans", "UNCG"),
        ("VMI", "Keydets", "VMI"),
        ("Western Carolina", "Catamounts", "WCU"),
        ("Wofford", "Terriers", "WOF"),
        ("Chattanooga", "Mocs", "UTC"),
        # === Big West (9 teams) ===
        ("Cal Poly", "Mustangs", "CP"),
        ("Cal State Bakersfield", "Roadrunners", "CSUB"),
        ("Cal State Fullerton", "Titans", "CSUF"),
        ("Cal State Northridge", "Matadors", "CSUN"),
        ("Hawaii", "Rainbow Warriors", "HAW"),
        ("Long Beach State", "Beach", "LBSU"),
        ("UC Davis", "Aggies", "UCD"),
        ("UC Irvine", "Anteaters", "UCI"),
        ("UC Riverside", "Highlanders", "UCR"),
        ("UC San Diego", "Tritons", "UCSD"),
        ("UC Santa Barbara", "Gauchos", "UCSB"),
        # === Patriot League (7 teams) ===
        ("Army", "Black Knights", "ARMY"),
        ("Bucknell", "Bison", "BUCK"),
        ("Holy Cross", "Crusaders", "HC"),
        ("Lafayette", "Leopards", "LAF"),
        ("Lehigh", "Mountain Hawks", "LEH"),
        ("Navy", "Midshipmen", "NAVY2"),
        # === Ivy League (8 teams) ===
        ("Columbia", "Lions", "CLMB"),
        ("Cornell", "Big Red", "COR"),
        ("Dartmouth", "Big Green", "DART"),
        ("Harvard", "Crimson", "HARV"),
        ("Penn", "Quakers", "PENN"),
        ("Princeton", "Tigers", "PRIN"),
        ("Yale", "Bulldogs", "YALE"),
        ("Brown", "Bears", "BRWN"),
        # === Horizon League (8 teams) ===
        ("Cleveland State", "Vikings", "CLST"),
        ("Illinois-Chicago", "Flames", "UIC2"),
        ("IUPUI", "Jaguars", "IUPU"),
        ("Milwaukee", "Panthers", "MILW"),
        ("Northern Kentucky", "Norse", "NKU"),
        ("Oakland", "Golden Grizzlies", "OAK"),
        ("Wright State", "Raiders", "WRST"),
        ("Youngstown State", "Penguins", "YSU"),
        # === Ohio Valley (9 teams) ===
        ("Morehead State", "Eagles", "MORE"),
        ("Southeast Missouri", "Redhawks", "SEMO"),
        ("SIU Edwardsville", "Cougars", "SIUE"),
        ("Tennessee State", "Tigers", "TSU"),
        ("Tennessee Tech", "Golden Eagles", "TTN"),
        ("UT Martin", "Skyhawks", "UTM"),
        ("Little Rock", "Trojans", "LR"),
        ("Southern Indiana", "Screaming Eagles", "USI"),
        ("Lindenwood", "Lions", "LIND"),
        # === Southland (9 teams) ===
        ("Houston Christian", "Huskies", "HCU"),
        ("Incarnate Word", "Cardinals", "IW"),
        ("Lamar", "Cardinals", "LAM"),
        ("McNeese", "Cowboys", "MCN"),
        ("New Orleans", "Privateers", "UNO"),
        ("Nicholls", "Colonels", "NICH"),
        ("Northwestern State", "Demons", "NWST"),
        ("Southeastern Louisiana", "Lions", "SELA"),
        ("Texas A&M-Corpus Christi", "Islanders", "AMCC"),
        # === Northeast (12 teams) ===
        ("Bryant", "Bulldogs", "BRY"),
        ("Central Connecticut", "Blue Devils", "CCSU"),
        ("Fairleigh Dickinson", "Knights", "FDU"),
        ("Le Moyne", "Dolphins", "LEM"),
        ("LIU", "Sharks", "LIU"),
        ("Maine", "Black Bears", "ME"),
        ("Mercyhurst", "Lakers", "MERC"),
        ("Mount St. Mary's", "Mountaineers", "MSM"),
        ("Sacred Heart", "Pioneers", "SHU"),
        ("St. Francis (PA)", "Red Flash", "SFP"),
        ("Stonehill", "Skyhawks", "STHL"),
        ("Wagner", "Seahawks", "WAG"),
        # === MEAC (8 teams) ===
        ("Bethune-Cookman", "Wildcats", "BCU"),
        ("Coppin State", "Eagles", "COPP"),
        ("Delaware State", "Hornets", "DSU"),
        ("Howard", "Bison", "HOW"),
        ("Maryland-Eastern Shore", "Hawks", "UMES"),
        ("Norfolk State", "Spartans", "NSU"),
        ("North Carolina A&T", "Aggies", "NCAT"),
        ("South Carolina State", "Bulldogs", "SCST"),
        # === SWAC (10 teams) ===
        ("Alabama A&M", "Bulldogs", "AAMU"),
        ("Alabama State", "Hornets", "ALST"),
        ("Alcorn State", "Braves", "ALCN"),
        ("Grambling State", "Tigers", "GRAM"),
        ("Jackson State", "Tigers", "JKST"),
        ("Mississippi Valley State", "Delta Devils", "MVSU"),
        ("Prairie View A&M", "Panthers", "PVAM"),
        ("Southern", "Jaguars", "SOU"),
        ("Texas Southern", "Tigers", "TXSO"),
        ("Arkansas-Pine Bluff", "Golden Lions", "UAPB"),
        # === Summit League (6 teams) ===
        ("North Dakota State", "Bison", "NDSU"),
        ("Omaha", "Mavericks", "OMA"),
        ("Oral Roberts", "Golden Eagles", "ORU"),
        ("South Dakota State", "Jackrabbits", "SDST"),
        ("St. Thomas (MN)", "Tommies", "STMN"),
        ("Western Illinois", "Leathernecks", "WIU"),
        # === WAC (7 teams) ===
        ("Abilene Christian", "Wildcats", "ACU"),
        ("Grand Canyon", "Antelopes", "GCU"),
        ("Seattle U", "Redhawks", "SEA"),
        ("Southern Utah", "Thunderbirds", "SUU"),
        ("Stephen F. Austin", "Lumberjacks", "SFA"),
        ("Tarleton State", "Texans", "TARL"),
        ("Utah Valley", "Wolverines", "UVU"),
        # === America East (8 teams) ===
        ("Albany", "Great Danes", "ALB"),
        ("Binghamton", "Bearcats", "BING"),
        ("Hartford", "Hawks", "HART"),
        ("New Hampshire", "Wildcats", "UNH"),
        ("NJIT", "Highlanders", "NJIT"),
        ("UMass Lowell", "River Hawks", "UML"),
        ("Vermont", "Catamounts", "UVM"),
        # === MAAC (9 teams) ===
        ("Canisius", "Golden Griffins", "CAN"),
        ("Fairfield", "Stags", "FAIR"),
        ("Iona", "Gaels", "IONA"),
        ("Manhattan", "Jaspers", "MAN"),
        ("Marist", "Red Foxes", "MRSJ"),
        ("Niagara", "Purple Eagles", "NIAG"),
        ("Quinnipiac", "Bobcats", "QUIN"),
        ("Rider", "Broncs", "RID"),
        ("Saint Peter's", "Peacocks", "SPU"),
        ("Siena", "Saints", "SIEN"),
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
