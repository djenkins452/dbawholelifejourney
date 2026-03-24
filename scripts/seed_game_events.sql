-- GameEvent seed data — generated from local DB
-- Run after seed_sports_data.sql

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-22 23:09:00+0000', 'final', 68, 63, 'State Farm Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'PUR' AND a.league_id = hl.id
WHERE h.abbreviation = 'HOU' AND hl.slug = 'ncaab'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-22 23:09:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-22 23:09:00+0000', 'final', 78, 65, 'State Farm Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'ALA' AND a.league_id = hl.id
WHERE h.abbreviation = 'DUKE' AND hl.slug = 'ncaab'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-22 23:09:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-23 01:00:00+0000', 'final', 5, 3, 'Rogers Place', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'CGY' AND a.league_id = hl.id
WHERE h.abbreviation = 'EDM' AND hl.slug = 'nhl'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-23 01:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-23 01:30:00+0000', 'final', 115, 109, 'American Airlines Center', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'PHX' AND a.league_id = hl.id
WHERE h.abbreviation = 'DAL' AND hl.slug = 'nba'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-23 01:30:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-23 01:49:00+0000', 'final', 75, 72, 'State Farm Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'MARQ' AND a.league_id = hl.id
WHERE h.abbreviation = 'TENN' AND hl.slug = 'ncaab'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-23 01:49:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-23 01:49:00+0000', 'final', 82, 71, 'State Farm Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'MICH' AND a.league_id = hl.id
WHERE h.abbreviation = 'AUB' AND hl.slug = 'ncaab'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-23 01:49:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-23 19:20:00+0000', 'final', 3, 5, 'Wrigley Field', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'MIL' AND a.league_id = hl.id
WHERE h.abbreviation = 'CHC' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-23 19:20:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-23 22:00:00+0000', 'final', 7, 4, 'Lindsey Nelson Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'SC' AND a.league_id = hl.id
WHERE h.abbreviation = 'TENN' AND hl.slug = 'ncaabb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-23 22:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-23 22:00:00+0000', 'final', 9, 2, 'Florida Ballpark', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'UGA' AND a.league_id = hl.id
WHERE h.abbreviation = 'FLA' AND hl.slug = 'ncaabb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-23 22:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-23 23:00:00+0000', 'final', 8, 5, 'Hawkins Field', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'ALA' AND a.league_id = hl.id
WHERE h.abbreviation = 'VAN' AND hl.slug = 'ncaabb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-23 23:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-23 23:00:00+0000', 'final', 4, 2, 'Amerant Bank Arena', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'TBL' AND a.league_id = hl.id
WHERE h.abbreviation = 'FLA' AND hl.slug = 'nhl'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-23 23:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-23 23:05:00+0000', 'final', 4, 6, 'Yankee Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'TOR' AND a.league_id = hl.id
WHERE h.abbreviation = 'NYY' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-23 23:05:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-23 23:10:00+0000', 'final', 5, 3, 'Truist Park', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'NYM' AND a.league_id = hl.id
WHERE h.abbreviation = 'ATL' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-23 23:10:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-23 23:10:00+0000', 'final', 6, 4, 'Fenway Park', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'BAL' AND a.league_id = hl.id
WHERE h.abbreviation = 'BOS' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-23 23:10:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-23 23:30:00+0000', 'final', 112, 98, 'TD Garden', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'MIA' AND a.league_id = hl.id
WHERE h.abbreviation = 'BOS' AND hl.slug = 'nba'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-23 23:30:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-23 23:30:00+0000', 'final', 105, 118, 'State Farm Arena', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'MIL' AND a.league_id = hl.id
WHERE h.abbreviation = 'ATL' AND hl.slug = 'nba'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-23 23:30:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-23 23:30:00+0000', 'final', 4, 7, 'Plainsman Park', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'ARK' AND a.league_id = hl.id
WHERE h.abbreviation = 'AUB' AND hl.slug = 'ncaabb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-23 23:30:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-23 23:30:00+0000', 'final', 6, 3, 'Alex Box Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'MISS' AND a.league_id = hl.id
WHERE h.abbreviation = 'LSU' AND hl.slug = 'ncaabb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-23 23:30:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-24 00:10:00+0000', 'final', 8, 1, 'Minute Maid Park', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'SEA' AND a.league_id = hl.id
WHERE h.abbreviation = 'HOU' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-24 00:10:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-24 01:00:00+0000', 'final', 3, 1, 'American Airlines Center', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'MIN' AND a.league_id = hl.id
WHERE h.abbreviation = 'DAL' AND hl.slug = 'nhl'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-24 01:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-24 01:00:00+0000', 'final', 108, 104, 'Paycom Center', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'LAL' AND a.league_id = hl.id
WHERE h.abbreviation = 'OKC' AND hl.slug = 'nba'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-24 01:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-24 02:10:00+0000', 'final', 7, 2, 'Dodger Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'SFG' AND a.league_id = hl.id
WHERE h.abbreviation = 'LAD' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-24 02:10:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-24 22:00:00+0000', 'scheduled', NULL, NULL, 'Florida Ballpark', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'TENN' AND a.league_id = hl.id
WHERE h.abbreviation = 'FLA' AND hl.slug = 'ncaabb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-24 22:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-24 22:40:00+0000', 'scheduled', NULL, NULL, 'Comerica Park', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'CLE' AND a.league_id = hl.id
WHERE h.abbreviation = 'DET' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-24 22:40:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-24 23:00:00+0000', 'scheduled', NULL, NULL, 'Amerant Bank Arena', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'BOS' AND a.league_id = hl.id
WHERE h.abbreviation = 'FLA' AND hl.slug = 'nhl'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-24 23:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-24 23:00:00+0000', 'scheduled', NULL, NULL, 'Hawkins Field', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'LSU' AND a.league_id = hl.id
WHERE h.abbreviation = 'VAN' AND hl.slug = 'ncaabb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-24 23:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-24 23:00:00+0000', 'scheduled', NULL, NULL, 'Sewell-Thomas Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'UK' AND a.league_id = hl.id
WHERE h.abbreviation = 'ALA' AND hl.slug = 'ncaabb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-24 23:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-24 23:05:00+0000', 'scheduled', NULL, NULL, 'Yankee Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'BOS' AND a.league_id = hl.id
WHERE h.abbreviation = 'NYY' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-24 23:05:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-24 23:09:00+0000', 'scheduled', NULL, NULL, 'State Farm Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'HOU' AND a.league_id = hl.id
WHERE h.abbreviation = 'DUKE' AND hl.slug = 'ncaab'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-24 23:09:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-24 23:10:00+0000', 'scheduled', NULL, NULL, 'Truist Park', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'LAD' AND a.league_id = hl.id
WHERE h.abbreviation = 'ATL' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-24 23:10:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-24 23:30:00+0000', 'scheduled', NULL, NULL, 'TD Garden', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'CLE' AND a.league_id = hl.id
WHERE h.abbreviation = 'BOS' AND hl.slug = 'nba'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-24 23:30:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-24 23:30:00+0000', 'scheduled', NULL, NULL, 'Mercedes-Benz Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'MIA' AND a.league_id = hl.id
WHERE h.abbreviation = 'ATL' AND hl.slug = 'mls'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-24 23:30:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-24 23:30:00+0000', 'scheduled', NULL, NULL, 'Plainsman Park', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'MSU' AND a.league_id = hl.id
WHERE h.abbreviation = 'AUB' AND hl.slug = 'ncaabb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-24 23:30:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-24 23:30:00+0000', 'scheduled', NULL, NULL, 'Swayze Field', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'ARK' AND a.league_id = hl.id
WHERE h.abbreviation = 'MISS' AND hl.slug = 'ncaabb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-24 23:30:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-24 23:30:00+0000', 'scheduled', NULL, NULL, 'UFCU Disch-Falk Field', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'OU' AND a.league_id = hl.id
WHERE h.abbreviation = 'TEX' AND hl.slug = 'ncaabb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-24 23:30:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-24 23:40:00+0000', 'scheduled', NULL, NULL, 'American Family Field', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'CIN' AND a.league_id = hl.id
WHERE h.abbreviation = 'MIL' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-24 23:40:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-25 00:10:00+0000', 'scheduled', NULL, NULL, 'Minute Maid Park', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'TEX' AND a.league_id = hl.id
WHERE h.abbreviation = 'HOU' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-25 00:10:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-25 00:15:00+0000', 'scheduled', NULL, NULL, 'Wrigley Field', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'STL' AND a.league_id = hl.id
WHERE h.abbreviation = 'CHC' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-25 00:15:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-25 01:30:00+0000', 'scheduled', NULL, NULL, 'Paycom Center', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'DAL' AND a.league_id = hl.id
WHERE h.abbreviation = 'OKC' AND hl.slug = 'nba'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-25 01:30:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-25 01:45:00+0000', 'scheduled', NULL, NULL, 'Oracle Park', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'SD' AND a.league_id = hl.id
WHERE h.abbreviation = 'SFG' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-25 01:45:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-25 01:49:00+0000', 'scheduled', NULL, NULL, 'State Farm Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'TENN' AND a.league_id = hl.id
WHERE h.abbreviation = 'AUB' AND hl.slug = 'ncaab'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-25 01:49:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-25 02:00:00+0000', 'scheduled', NULL, NULL, 'Rogers Place', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'VAN' AND a.league_id = hl.id
WHERE h.abbreviation = 'EDM' AND hl.slug = 'nhl'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-25 02:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-25 02:00:00+0000', 'scheduled', NULL, NULL, 'BMO Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'LAG' AND a.league_id = hl.id
WHERE h.abbreviation = 'LAFC' AND hl.slug = 'mls'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-25 02:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-25 02:00:00+0000', 'scheduled', NULL, NULL, 'Crypto.com Arena', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'DEN' AND a.league_id = hl.id
WHERE h.abbreviation = 'LAL' AND hl.slug = 'nba'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-25 02:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-25 02:10:00+0000', 'scheduled', NULL, NULL, 'T-Mobile Park', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'LAA' AND a.league_id = hl.id
WHERE h.abbreviation = 'SEA' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-25 02:10:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-25 02:30:00+0000', 'scheduled', NULL, NULL, 'American Airlines Center', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'COL' AND a.league_id = hl.id
WHERE h.abbreviation = 'DAL' AND hl.slug = 'nhl'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-25 02:30:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-25 18:00:00+0000', 'scheduled', NULL, NULL, 'Lindsey Nelson Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'FLA' AND a.league_id = hl.id
WHERE h.abbreviation = 'TENN' AND hl.slug = 'ncaabb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-25 18:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-25 19:00:00+0000', 'scheduled', NULL, NULL, 'Alex Box Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'VAN' AND a.league_id = hl.id
WHERE h.abbreviation = 'LSU' AND hl.slug = 'ncaabb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-25 19:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-25 21:00:00+0000', 'scheduled', NULL, NULL, 'Yankee Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'NYRB' AND a.league_id = hl.id
WHERE h.abbreviation = 'NYC' AND hl.slug = 'mls'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-25 21:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-25 22:00:00+0000', 'scheduled', NULL, NULL, 'Founders Park', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'UGA' AND a.league_id = hl.id
WHERE h.abbreviation = 'SC' AND hl.slug = 'ncaabb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-25 22:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-25 22:09:00+0000', 'scheduled', NULL, NULL, 'Chase Center', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'GONZ' AND a.league_id = hl.id
WHERE h.abbreviation = 'KU' AND hl.slug = 'ncaab'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-25 22:09:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-25 22:40:00+0000', 'scheduled', NULL, NULL, 'Tropicana Field', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'TOR' AND a.league_id = hl.id
WHERE h.abbreviation = 'TB' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-25 22:40:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-25 23:05:00+0000', 'scheduled', NULL, NULL, 'Citizens Bank Park', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'NYM' AND a.league_id = hl.id
WHERE h.abbreviation = 'PHI' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-25 23:05:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-25 23:10:00+0000', 'scheduled', NULL, NULL, 'Fenway Park', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'NYY' AND a.league_id = hl.id
WHERE h.abbreviation = 'BOS' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-25 23:10:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-25 23:30:00+0000', 'scheduled', NULL, NULL, 'State Farm Arena', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'CHI' AND a.league_id = hl.id
WHERE h.abbreviation = 'ATL' AND hl.slug = 'nba'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-25 23:30:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-25 23:30:00+0000', 'scheduled', NULL, NULL, 'Blue Bell Park', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'MIZ' AND a.league_id = hl.id
WHERE h.abbreviation = 'TAMU' AND hl.slug = 'ncaabb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-25 23:30:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-25 23:30:00+0000', 'scheduled', NULL, NULL, 'Madison Square Garden', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'CAR' AND a.league_id = hl.id
WHERE h.abbreviation = 'NYR' AND hl.slug = 'nhl'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-25 23:30:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-26 00:00:00+0000', 'scheduled', NULL, NULL, 'Fiserv Forum', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'IND' AND a.league_id = hl.id
WHERE h.abbreviation = 'MIL' AND hl.slug = 'nba'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-26 00:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-26 00:10:00+0000', 'scheduled', NULL, NULL, 'Target Field', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'KC' AND a.league_id = hl.id
WHERE h.abbreviation = 'MIN' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-26 00:10:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-26 00:15:00+0000', 'scheduled', NULL, NULL, 'Busch Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'CHC' AND a.league_id = hl.id
WHERE h.abbreviation = 'STL' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-26 00:15:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-26 00:49:00+0000', 'scheduled', NULL, NULL, 'Chase Center', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'MARQ' AND a.league_id = hl.id
WHERE h.abbreviation = 'FLA' AND hl.slug = 'ncaab'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-26 00:49:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-26 01:00:00+0000', 'scheduled', NULL, NULL, 'Canada Life Centre', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'NSH' AND a.league_id = hl.id
WHERE h.abbreviation = 'WPG' AND hl.slug = 'nhl'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-26 01:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-26 01:40:00+0000', 'scheduled', NULL, NULL, 'Coors Field', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'ARI' AND a.league_id = hl.id
WHERE h.abbreviation = 'COL' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-26 01:40:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-26 02:00:00+0000', 'scheduled', NULL, NULL, 'Footprint Center', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'MIN' AND a.league_id = hl.id
WHERE h.abbreviation = 'PHX' AND hl.slug = 'nba'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-26 02:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-26 02:10:00+0000', 'scheduled', NULL, NULL, 'Dodger Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'ATL' AND a.league_id = hl.id
WHERE h.abbreviation = 'LAD' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-26 02:10:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-26 02:30:00+0000', 'scheduled', NULL, NULL, 'Lumen Field', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'POR' AND a.league_id = hl.id
WHERE h.abbreviation = 'SEA' AND hl.slug = 'mls'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-26 02:30:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-26 17:00:00+0000', 'scheduled', NULL, NULL, 'Florida Ballpark', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'TENN' AND a.league_id = hl.id
WHERE h.abbreviation = 'FLA' AND hl.slug = 'ncaabb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-26 17:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-26 17:05:00+0000', 'scheduled', NULL, NULL, 'Yankee Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'BOS' AND a.league_id = hl.id
WHERE h.abbreviation = 'NYY' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-26 17:05:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-26 17:20:00+0000', 'scheduled', NULL, NULL, 'Truist Park', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'LAD' AND a.league_id = hl.id
WHERE h.abbreviation = 'ATL' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-26 17:20:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-26 18:00:00+0000', 'scheduled', NULL, NULL, 'Hawkins Field', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'LSU' AND a.league_id = hl.id
WHERE h.abbreviation = 'VAN' AND hl.slug = 'ncaabb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-26 18:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-26 19:00:00+0000', 'scheduled', NULL, NULL, 'Dudy Noble Field', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'AUB' AND a.league_id = hl.id
WHERE h.abbreviation = 'MSU' AND hl.slug = 'ncaabb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-26 19:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-26 19:00:00+0000', 'scheduled', NULL, NULL, 'Baum-Walker Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'MISS' AND a.league_id = hl.id
WHERE h.abbreviation = 'ARK' AND hl.slug = 'ncaabb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-26 19:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-26 23:00:00+0000', 'scheduled', NULL, NULL, 'TD Garden', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'FLA' AND a.league_id = hl.id
WHERE h.abbreviation = 'BOS' AND hl.slug = 'nhl'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-26 23:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-26 23:05:00+0000', 'scheduled', NULL, NULL, 'Camden Yards', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'WSH' AND a.league_id = hl.id
WHERE h.abbreviation = 'BAL' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-26 23:05:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-26 23:30:00+0000', 'scheduled', NULL, NULL, 'Lower.com Field', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'CIN' AND a.league_id = hl.id
WHERE h.abbreviation = 'CLB' AND hl.slug = 'mls'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-26 23:30:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-27 00:00:00+0000', 'scheduled', NULL, NULL, 'Rocket Mortgage FieldHouse', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'BOS' AND a.league_id = hl.id
WHERE h.abbreviation = 'CLE' AND hl.slug = 'nba'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-27 00:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-27 00:05:00+0000', 'scheduled', NULL, NULL, 'Globe Life Field', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'HOU' AND a.league_id = hl.id
WHERE h.abbreviation = 'TEX' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-27 00:05:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-27 01:00:00+0000', 'scheduled', NULL, NULL, 'Toyota Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'HOU' AND a.league_id = hl.id
WHERE h.abbreviation = 'DAL' AND hl.slug = 'mls'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-27 01:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-27 01:30:00+0000', 'scheduled', NULL, NULL, 'American Airlines Center', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'OKC' AND a.league_id = hl.id
WHERE h.abbreviation = 'DAL' AND hl.slug = 'nba'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-27 01:30:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-27 01:40:00+0000', 'scheduled', NULL, NULL, 'Oakland Coliseum', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'SFG' AND a.league_id = hl.id
WHERE h.abbreviation = 'OAK' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-27 01:40:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-27 02:00:00+0000', 'scheduled', NULL, NULL, 'Ball Arena', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'LAL' AND a.league_id = hl.id
WHERE h.abbreviation = 'DEN' AND hl.slug = 'nba'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-27 02:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-27 02:00:00+0000', 'scheduled', NULL, NULL, 'Ball Arena', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'DAL' AND a.league_id = hl.id
WHERE h.abbreviation = 'COL' AND hl.slug = 'nhl'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-27 02:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-27 02:00:00+0000', 'scheduled', NULL, NULL, 'Rogers Arena', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'EDM' AND a.league_id = hl.id
WHERE h.abbreviation = 'VAN' AND hl.slug = 'nhl'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-27 02:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-27 19:20:00+0000', 'scheduled', NULL, NULL, 'Wrigley Field', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'MIL' AND a.league_id = hl.id
WHERE h.abbreviation = 'CHC' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-27 19:20:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-27 22:00:00+0000', 'scheduled', NULL, NULL, 'Foley Field', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'SC' AND a.league_id = hl.id
WHERE h.abbreviation = 'UGA' AND hl.slug = 'ncaabb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-27 22:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-27 22:00:00+0000', 'scheduled', NULL, NULL, 'Boshamer Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'DUKE' AND a.league_id = hl.id
WHERE h.abbreviation = 'UNC' AND hl.slug = 'ncaabb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-27 22:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-27 22:00:00+0000', 'scheduled', NULL, NULL, 'Dick Howser Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'CLEM' AND a.league_id = hl.id
WHERE h.abbreviation = 'FSU' AND hl.slug = 'ncaabb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-27 22:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-27 22:09:00+0000', 'scheduled', NULL, NULL, 'Alamodome', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'AUB' AND a.league_id = hl.id
WHERE h.abbreviation = 'DUKE' AND hl.slug = 'ncaab'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-27 22:09:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-27 23:00:00+0000', 'scheduled', NULL, NULL, 'PNC Arena', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'NYR' AND a.league_id = hl.id
WHERE h.abbreviation = 'CAR' AND hl.slug = 'nhl'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-27 23:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-27 23:10:00+0000', 'scheduled', NULL, NULL, 'Fenway Park', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'TB' AND a.league_id = hl.id
WHERE h.abbreviation = 'BOS' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-27 23:10:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-27 23:20:00+0000', 'scheduled', NULL, NULL, 'Truist Park', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'PHI' AND a.league_id = hl.id
WHERE h.abbreviation = 'ATL' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-27 23:20:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-27 23:30:00+0000', 'scheduled', NULL, NULL, 'Taylor Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'TAMU' AND a.league_id = hl.id
WHERE h.abbreviation = 'MIZ' AND hl.slug = 'ncaabb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-27 23:30:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-27 23:30:00+0000', 'scheduled', NULL, NULL, 'Mercedes-Benz Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'CLT' AND a.league_id = hl.id
WHERE h.abbreviation = 'ATL' AND hl.slug = 'mls'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-27 23:30:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-27 23:30:00+0000', 'scheduled', NULL, NULL, 'Madison Square Garden', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'PHI' AND a.league_id = hl.id
WHERE h.abbreviation = 'NYK' AND hl.slug = 'nba'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-27 23:30:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-28 00:49:00+0000', 'scheduled', NULL, NULL, 'Alamodome', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'FLA' AND a.league_id = hl.id
WHERE h.abbreviation = 'KU' AND hl.slug = 'ncaab'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-28 00:49:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-28 01:00:00+0000', 'scheduled', NULL, NULL, 'Allianz Field', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'CHI' AND a.league_id = hl.id
WHERE h.abbreviation = 'MIN' AND hl.slug = 'mls'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-28 01:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-28 01:00:00+0000', 'scheduled', NULL, NULL, 'Bridgestone Arena', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'WPG' AND a.league_id = hl.id
WHERE h.abbreviation = 'NSH' AND hl.slug = 'nhl'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-28 01:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-28 02:00:00+0000', 'scheduled', NULL, NULL, 'Chase Center', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'LAC' AND a.league_id = hl.id
WHERE h.abbreviation = 'GSW' AND hl.slug = 'nba'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-28 02:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-28 02:10:00+0000', 'scheduled', NULL, NULL, 'Dodger Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'SFG' AND a.league_id = hl.id
WHERE h.abbreviation = 'LAD' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-28 02:10:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-28 22:00:00+0000', 'scheduled', NULL, NULL, 'Lindsey Nelson Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'VAN' AND a.league_id = hl.id
WHERE h.abbreviation = 'TENN' AND hl.slug = 'ncaabb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-28 22:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-28 23:05:00+0000', 'scheduled', NULL, NULL, 'Yankee Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'BAL' AND a.league_id = hl.id
WHERE h.abbreviation = 'NYY' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-28 23:05:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-28 23:10:00+0000', 'scheduled', NULL, NULL, 'Citi Field', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'ATL' AND a.league_id = hl.id
WHERE h.abbreviation = 'NYM' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-28 23:10:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-28 23:30:00+0000', 'scheduled', NULL, NULL, 'Alex Box Stadium', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'ALA' AND a.league_id = hl.id
WHERE h.abbreviation = 'LSU' AND hl.slug = 'ncaabb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-28 23:30:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-28 23:30:00+0000', 'scheduled', NULL, NULL, 'Subaru Park', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'DC' AND a.league_id = hl.id
WHERE h.abbreviation = 'PHI' AND hl.slug = 'mls'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-28 23:30:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-28 23:30:00+0000', 'scheduled', NULL, NULL, 'Amerant Bank Arena', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'BOS' AND a.league_id = hl.id
WHERE h.abbreviation = 'FLA' AND hl.slug = 'nhl'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-28 23:30:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-28 23:30:00+0000', 'scheduled', NULL, NULL, 'UFCU Disch-Falk Field', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'TAMU' AND a.league_id = hl.id
WHERE h.abbreviation = 'TEX' AND hl.slug = 'ncaabb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-28 23:30:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-29 00:00:00+0000', 'scheduled', NULL, NULL, 'TD Garden', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'CLE' AND a.league_id = hl.id
WHERE h.abbreviation = 'BOS' AND hl.slug = 'nba'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-29 00:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-29 01:30:00+0000', 'scheduled', NULL, NULL, 'Crypto.com Arena', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'DEN' AND a.league_id = hl.id
WHERE h.abbreviation = 'LAL' AND hl.slug = 'nba'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-29 01:30:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-29 02:00:00+0000', 'scheduled', NULL, NULL, 'Dick''s Sporting Goods Park', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'RSL' AND a.league_id = hl.id
WHERE h.abbreviation = 'COL' AND hl.slug = 'mls'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-29 02:00:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-29 02:10:00+0000', 'scheduled', NULL, NULL, 'Petco Park', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'LAD' AND a.league_id = hl.id
WHERE h.abbreviation = 'SD' AND hl.slug = 'mlb'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-29 02:10:00+0000'
);

INSERT INTO sports_gameevent (home_team_id, away_team_id, start_time, status, home_score, away_score, venue, external_id)
SELECT h.id, a.id, '2026-03-29 02:30:00+0000', 'scheduled', NULL, NULL, 'American Airlines Center', ''
FROM sports_team h
JOIN sports_league hl ON h.league_id = hl.id
JOIN sports_team a ON a.abbreviation = 'COL' AND a.league_id = hl.id
WHERE h.abbreviation = 'DAL' AND hl.slug = 'nhl'
AND NOT EXISTS (
  SELECT 1 FROM sports_gameevent ge
  WHERE ge.home_team_id = h.id AND ge.away_team_id = a.id AND ge.start_time = '2026-03-29 02:30:00+0000'
);

