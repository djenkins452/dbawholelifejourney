-- =====================================================================
-- WLJ Sports Domain — Complete Data Seed
-- Run in DBeaver against the Railway PostgreSQL database
-- Safe to re-run (uses ON CONFLICT DO NOTHING)
-- =====================================================================

-- ─────────────────────────────────────────────────────────────────────
-- SPORTS (5)
-- ─────────────────────────────────────────────────────────────────────
INSERT INTO sports_sport (name, slug) VALUES
  ('Football', 'football'),
  ('Basketball', 'basketball'),
  ('Baseball', 'baseball'),
  ('Hockey', 'hockey'),
  ('Soccer', 'soccer')
ON CONFLICT (slug) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────
-- LEAGUES (8)
-- ─────────────────────────────────────────────────────────────────────
INSERT INTO sports_league (sport_id, name, slug, abbreviation, is_college) VALUES
  ((SELECT id FROM sports_sport WHERE slug='football'),  'National Football League',       'nfl',    'NFL',    false),
  ((SELECT id FROM sports_sport WHERE slug='basketball'), 'National Basketball Association', 'nba',    'NBA',    false),
  ((SELECT id FROM sports_sport WHERE slug='baseball'),   'Major League Baseball',           'mlb',    'MLB',    false),
  ((SELECT id FROM sports_sport WHERE slug='hockey'),     'National Hockey League',          'nhl',    'NHL',    false),
  ((SELECT id FROM sports_sport WHERE slug='soccer'),     'Major League Soccer',             'mls',    'MLS',    false),
  ((SELECT id FROM sports_sport WHERE slug='football'),  'NCAA Football (FBS)',             'ncaaf',  'NCAAF',  true),
  ((SELECT id FROM sports_sport WHERE slug='basketball'), 'NCAA Men''s Basketball',          'ncaab',  'NCAAB',  true),
  ((SELECT id FROM sports_sport WHERE slug='baseball'),   'NCAA Baseball',                   'ncaabb', 'NCAABB', true)
ON CONFLICT (slug) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────
-- NFL — 32 Teams
-- ─────────────────────────────────────────────────────────────────────
INSERT INTO sports_team (league_id, location, name, abbreviation, external_id, logo_url) VALUES
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Buffalo',       'Bills',       'BUF', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Miami',         'Dolphins',    'MIA', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'New England',   'Patriots',    'NE',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'New York',      'Jets',        'NYJ', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Baltimore',     'Ravens',      'BAL', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Cincinnati',    'Bengals',     'CIN', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Cleveland',     'Browns',      'CLE', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Pittsburgh',    'Steelers',    'PIT', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Houston',       'Texans',      'HOU', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Indianapolis',  'Colts',       'IND', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Jacksonville',  'Jaguars',     'JAX', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Tennessee',     'Titans',      'TEN', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Denver',        'Broncos',     'DEN', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Kansas City',   'Chiefs',      'KC',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Las Vegas',     'Raiders',     'LV',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Los Angeles',   'Chargers',    'LAC', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Dallas',        'Cowboys',     'DAL', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'New York',      'Giants',      'NYG', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Philadelphia',  'Eagles',      'PHI', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Washington',    'Commanders',  'WAS', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Chicago',       'Bears',       'CHI', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Detroit',       'Lions',       'DET', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Green Bay',     'Packers',     'GB',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Minnesota',     'Vikings',     'MIN', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Atlanta',       'Falcons',     'ATL', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Carolina',      'Panthers',    'CAR', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'New Orleans',   'Saints',      'NO',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Tampa Bay',     'Buccaneers',  'TB',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Arizona',       'Cardinals',   'ARI', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Los Angeles',   'Rams',        'LAR', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'San Francisco', '49ers',       'SF',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='nfl'), 'Seattle',       'Seahawks',    'SEA', '', '')
ON CONFLICT (league_id, abbreviation) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────
-- NBA — 30 Teams
-- ─────────────────────────────────────────────────────────────────────
INSERT INTO sports_team (league_id, location, name, abbreviation, external_id, logo_url) VALUES
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Boston',         'Celtics',        'BOS', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Brooklyn',       'Nets',           'BKN', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'New York',       'Knicks',         'NYK', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Philadelphia',   '76ers',          'PHI', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Toronto',        'Raptors',        'TOR', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Chicago',        'Bulls',          'CHI', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Cleveland',      'Cavaliers',      'CLE', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Detroit',        'Pistons',        'DET', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Indiana',        'Pacers',         'IND', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Milwaukee',      'Bucks',          'MIL', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Atlanta',        'Hawks',          'ATL', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Charlotte',      'Hornets',        'CHA', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Miami',          'Heat',           'MIA', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Orlando',        'Magic',          'ORL', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Washington',     'Wizards',        'WAS', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Denver',         'Nuggets',        'DEN', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Minnesota',      'Timberwolves',   'MIN', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Oklahoma City',  'Thunder',        'OKC', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Portland',       'Trail Blazers',  'POR', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Utah',           'Jazz',           'UTA', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Golden State',   'Warriors',       'GSW', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Los Angeles',    'Clippers',       'LAC', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Los Angeles',    'Lakers',         'LAL', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Phoenix',        'Suns',           'PHX', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Sacramento',     'Kings',          'SAC', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Dallas',         'Mavericks',      'DAL', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Houston',        'Rockets',        'HOU', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'Memphis',        'Grizzlies',      'MEM', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'New Orleans',    'Pelicans',       'NOP', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nba'), 'San Antonio',    'Spurs',          'SAS', '', '')
ON CONFLICT (league_id, abbreviation) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────
-- MLB — 30 Teams
-- ─────────────────────────────────────────────────────────────────────
INSERT INTO sports_team (league_id, location, name, abbreviation, external_id, logo_url) VALUES
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'Baltimore',      'Orioles',       'BAL', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'Boston',         'Red Sox',       'BOS', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'New York',       'Yankees',       'NYY', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'Tampa Bay',      'Rays',          'TB',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'Toronto',        'Blue Jays',     'TOR', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'Chicago',        'White Sox',     'CWS', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'Cleveland',      'Guardians',     'CLE', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'Detroit',        'Tigers',        'DET', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'Kansas City',    'Royals',        'KC',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'Minnesota',      'Twins',         'MIN', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'Houston',        'Astros',        'HOU', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'Los Angeles',    'Angels',        'LAA', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'Oakland',        'Athletics',     'OAK', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'Seattle',        'Mariners',      'SEA', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'Texas',          'Rangers',       'TEX', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'Atlanta',        'Braves',        'ATL', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'Miami',          'Marlins',       'MIA', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'New York',       'Mets',          'NYM', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'Philadelphia',   'Phillies',      'PHI', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'Washington',     'Nationals',     'WSH', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'Chicago',        'Cubs',          'CHC', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'Cincinnati',     'Reds',          'CIN', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'Milwaukee',      'Brewers',       'MIL', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'Pittsburgh',     'Pirates',       'PIT', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'St. Louis',      'Cardinals',     'STL', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'Arizona',        'Diamondbacks',  'ARI', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'Colorado',       'Rockies',       'COL', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'Los Angeles',    'Dodgers',       'LAD', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'San Diego',      'Padres',        'SD',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='mlb'), 'San Francisco',  'Giants',        'SFG', '', '')
ON CONFLICT (league_id, abbreviation) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────
-- NHL — 32 Teams
-- ─────────────────────────────────────────────────────────────────────
INSERT INTO sports_team (league_id, location, name, abbreviation, external_id, logo_url) VALUES
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Boston',        'Bruins',         'BOS', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Buffalo',       'Sabres',         'BUF', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Detroit',       'Red Wings',      'DET', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Florida',       'Panthers',       'FLA', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Montreal',      'Canadiens',      'MTL', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Ottawa',        'Senators',       'OTT', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Tampa Bay',     'Lightning',      'TBL', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Toronto',       'Maple Leafs',    'TOR', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Carolina',      'Hurricanes',     'CAR', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Columbus',      'Blue Jackets',   'CBJ', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'New Jersey',    'Devils',         'NJD', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'New York',      'Islanders',      'NYI', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'New York',      'Rangers',        'NYR', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Philadelphia',  'Flyers',         'PHI', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Pittsburgh',    'Penguins',       'PIT', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Washington',    'Capitals',       'WSH', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Arizona',       'Coyotes',        'ARI', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Chicago',       'Blackhawks',     'CHI', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Colorado',      'Avalanche',      'COL', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Dallas',        'Stars',          'DAL', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Minnesota',     'Wild',           'MIN', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Nashville',     'Predators',      'NSH', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'St. Louis',     'Blues',          'STL', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Winnipeg',      'Jets',           'WPG', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Anaheim',       'Ducks',          'ANA', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Calgary',       'Flames',         'CGY', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Edmonton',      'Oilers',         'EDM', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Los Angeles',   'Kings',          'LAK', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'San Jose',      'Sharks',         'SJS', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Seattle',       'Kraken',         'SEA', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Vancouver',     'Canucks',        'VAN', '', ''),
  ((SELECT id FROM sports_league WHERE slug='nhl'), 'Vegas',         'Golden Knights', 'VGK', '', '')
ON CONFLICT (league_id, abbreviation) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────
-- MLS — 29 Teams
-- ─────────────────────────────────────────────────────────────────────
INSERT INTO sports_team (league_id, location, name, abbreviation, external_id, logo_url) VALUES
  ((SELECT id FROM sports_league WHERE slug='mls'), 'Atlanta',           'United FC',      'ATL',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'Charlotte',         'FC',             'CLT',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'Chicago',           'Fire FC',        'CHI',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'Cincinnati',        'FC Cincinnati',  'CIN',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'Columbus',          'Crew',           'CLB',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'D.C.',              'United',         'DC',   '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'Inter Miami',       'CF',             'MIA',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'CF Montreal',       'CF Montreal',    'MTL',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'Nashville',         'SC',             'NSH',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'New England',       'Revolution',     'NE',   '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'New York',          'Red Bulls',      'NYRB', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'New York City',     'FC',             'NYC',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'Orlando City',      'SC',             'ORL',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'Philadelphia',      'Union',          'PHI',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'Toronto',           'FC',             'TOR',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'Austin',            'FC',             'ATX',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'Colorado',          'Rapids',         'COL',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'FC Dallas',         'FC Dallas',      'DAL',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'Houston',           'Dynamo FC',      'HOU',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'LA',                'Galaxy',         'LAG',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'Los Angeles',       'FC',             'LAFC', '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'Minnesota',         'United FC',      'MIN',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'Portland',          'Timbers',        'POR',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'Real Salt Lake',    'Real Salt Lake', 'RSL',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'San Jose',          'Earthquakes',    'SJ',   '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'Seattle',           'Sounders FC',    'SEA',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'Sporting Kansas City', 'Sporting KC', 'SKC',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'St. Louis',         'City SC',        'STL',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='mls'), 'Vancouver',         'Whitecaps FC',   'VAN',  '', '')
ON CONFLICT (league_id, abbreviation) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────
-- NCAA Football (FBS) — 40 Teams
-- ─────────────────────────────────────────────────────────────────────
INSERT INTO sports_team (league_id, location, name, abbreviation, external_id, logo_url) VALUES
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Alabama',          'Crimson Tide',    'ALA',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Arkansas',         'Razorbacks',      'ARK',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Auburn',           'Tigers',          'AUB',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Florida',          'Gators',          'FLA',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Georgia',          'Bulldogs',        'UGA',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Kentucky',         'Wildcats',        'UK',   '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'LSU',              'Tigers',          'LSU',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Mississippi State', 'Bulldogs',       'MSU',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Missouri',         'Tigers',          'MIZ',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Ole Miss',         'Rebels',          'MISS', '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'South Carolina',   'Gamecocks',       'SC',   '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Tennessee',        'Volunteers',      'TENN', '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Texas A&M',        'Aggies',          'TAMU', '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Vanderbilt',       'Commodores',      'VAN',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Oklahoma',         'Sooners',         'OU',   '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Texas',            'Longhorns',       'TEX',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Illinois',         'Fighting Illini', 'ILL',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Indiana',          'Hoosiers',        'IU',   '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Iowa',             'Hawkeyes',        'IOWA', '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Maryland',         'Terrapins',       'MD',   '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Michigan',         'Wolverines',      'MICH', '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Michigan State',   'Spartans',        'MSU2', '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Minnesota',        'Golden Gophers',  'MINN', '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Nebraska',         'Cornhuskers',     'NEB',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Northwestern',     'Wildcats',        'NW',   '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Ohio State',       'Buckeyes',        'OSU',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Oregon',           'Ducks',           'ORE',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Penn State',       'Nittany Lions',   'PSU',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Purdue',           'Boilermakers',    'PUR',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Rutgers',          'Scarlet Knights', 'RUT',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'USC',              'Trojans',         'USC',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'UCLA',             'Bruins',          'UCLA', '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Washington',       'Huskies',         'UW',   '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Wisconsin',        'Badgers',         'WIS',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Clemson',          'Tigers',          'CLEM', '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Florida State',    'Seminoles',       'FSU',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Miami',            'Hurricanes',      'UM',   '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'Notre Dame',       'Fighting Irish',  'ND',   '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'North Carolina',   'Tar Heels',       'UNC',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaaf'), 'NC State',         'Wolfpack',        'NCST', '', '')
ON CONFLICT (league_id, abbreviation) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────
-- NCAA Men's Basketball — 40 Teams
-- ─────────────────────────────────────────────────────────────────────
INSERT INTO sports_team (league_id, location, name, abbreviation, external_id, logo_url) VALUES
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Kansas',            'Jayhawks',       'KU',   '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Duke',             'Blue Devils',     'DUKE', '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'North Carolina',   'Tar Heels',       'UNC',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Kentucky',         'Wildcats',        'UK',   '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Connecticut',      'Huskies',         'UCON', '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Purdue',           'Boilermakers',    'PUR',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Gonzaga',          'Bulldogs',        'GONZ', '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Villanova',        'Wildcats',        'NOVA', '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Houston',          'Cougars',         'HOU',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Alabama',          'Crimson Tide',    'ALA',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Tennessee',        'Volunteers',      'TENN', '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Arizona',          'Wildcats',        'ARIZ', '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Baylor',           'Bears',           'BAY',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Creighton',        'Bluejays',        'CRE',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Indiana',          'Hoosiers',        'IU',   '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Iowa State',       'Cyclones',        'ISU',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Marquette',        'Golden Eagles',   'MARQ', '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Michigan State',   'Spartans',        'MSU',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Auburn',           'Tigers',          'AUB',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Texas',            'Longhorns',       'TEX',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'UCLA',             'Bruins',          'UCLA', '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Virginia',         'Cavaliers',       'UVA',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Michigan',         'Wolverines',      'MICH', '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Florida Atlantic', 'Owls',            'FAU',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'San Diego State',  'Aztecs',          'SDSU', '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Arkansas',         'Razorbacks',      'ARK',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Illinois',         'Fighting Illini', 'ILL',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Miami',            'Hurricanes',      'UM',   '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Ohio State',       'Buckeyes',        'OSU',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Oregon',           'Ducks',           'ORE',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Syracuse',         'Orange',          'SYR',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Louisville',       'Cardinals',       'LOU',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Xavier',           'Musketeers',      'XAV',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Wisconsin',        'Badgers',         'WIS',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Florida',          'Gators',          'FLA',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Memphis',          'Tigers',          'MEM',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'St. John''s',      'Red Storm',       'STJ',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Georgetown',       'Hoyas',           'GTWN', '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'Texas Tech',       'Red Raiders',     'TTU',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaab'), 'NC State',         'Wolfpack',        'NCST', '', '')
ON CONFLICT (league_id, abbreviation) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────
-- NCAA Baseball — 25 Teams
-- ─────────────────────────────────────────────────────────────────────
INSERT INTO sports_team (league_id, location, name, abbreviation, external_id, logo_url) VALUES
  ((SELECT id FROM sports_league WHERE slug='ncaabb'), 'LSU',                'Tigers',        'LSU',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaabb'), 'Florida',            'Gators',        'FLA',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaabb'), 'Vanderbilt',         'Commodores',    'VAN',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaabb'), 'Virginia',           'Cavaliers',     'UVA',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaabb'), 'Mississippi State',  'Bulldogs',      'MSU',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaabb'), 'Oregon State',       'Beavers',       'ORST', '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaabb'), 'Texas',              'Longhorns',     'TEX',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaabb'), 'Stanford',           'Cardinal',      'STAN', '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaabb'), 'Arkansas',           'Razorbacks',    'ARK',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaabb'), 'Arizona State',      'Sun Devils',    'ASU',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaabb'), 'Miami',              'Hurricanes',    'UM',   '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaabb'), 'Florida State',      'Seminoles',     'FSU',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaabb'), 'South Carolina',     'Gamecocks',     'SC',   '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaabb'), 'Texas A&M',          'Aggies',        'TAMU', '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaabb'), 'Cal State Fullerton', 'Titans',       'CSUF', '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaabb'), 'Coastal Carolina',   'Chanticleers',  'CCU',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaabb'), 'Ole Miss',           'Rebels',        'MISS', '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaabb'), 'Tennessee',          'Volunteers',    'TENN', '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaabb'), 'Oklahoma',           'Sooners',       'OU',   '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaabb'), 'Wake Forest',        'Demon Deacons', 'WF',   '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaabb'), 'North Carolina',     'Tar Heels',     'UNC',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaabb'), 'Georgia',            'Bulldogs',      'UGA',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaabb'), 'Auburn',             'Tigers',        'AUB',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaabb'), 'TCU',                'Horned Frogs',  'TCU',  '', ''),
  ((SELECT id FROM sports_league WHERE slug='ncaabb'), 'Rice',               'Owls',          'RICE', '', '')
ON CONFLICT (league_id, abbreviation) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────
-- Verification
-- ─────────────────────────────────────────────────────────────────────
SELECT '=== TOTALS ===' AS info;
SELECT 'Sports: ' || COUNT(*) FROM sports_sport;
SELECT 'Leagues: ' || COUNT(*) FROM sports_league;
SELECT 'Teams: ' || COUNT(*) FROM sports_team;

SELECT l.abbreviation AS league, COUNT(t.id) AS teams
FROM sports_league l
LEFT JOIN sports_team t ON t.league_id = l.id
GROUP BY l.abbreviation
ORDER BY l.abbreviation;
