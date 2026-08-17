CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS artists (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  sort_name TEXT,
  country TEXT,
  area TEXT,
  is_cpop BOOLEAN NOT NULL DEFAULT FALSE,
  mbid UUID,
  wikidata_qid TEXT,
  discogs_id TEXT,
  tags TEXT[] NOT NULL DEFAULT '{}',
  aliases TEXT[] NOT NULL DEFAULT '{}',
  source_urls TEXT[] NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS releases (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  artist_id TEXT REFERENCES artists(id),
  release_date DATE,
  release_type TEXT,
  mbid UUID,
  discogs_id TEXT,
  source_urls TEXT[] NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS recordings (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  artist_id TEXT REFERENCES artists(id),
  release_id TEXT REFERENCES releases(id),
  year INTEGER,
  language TEXT,
  is_cpop BOOLEAN NOT NULL DEFAULT FALSE,
  tags TEXT[] NOT NULL DEFAULT '{}',
  moods TEXT[] NOT NULL DEFAULT '{}',
  mbid UUID,
  wikidata_qid TEXT,
  listenbrainz_msid TEXT,
  embedding vector(384),
  source_urls TEXT[] NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS relations (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  target_id TEXT NOT NULL,
  relation_type TEXT NOT NULL,
  evidence_url TEXT,
  source_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_picks (
  pick_date DATE NOT NULL,
  user_id TEXT NOT NULL DEFAULT 'anonymous',
  recording_id TEXT NOT NULL REFERENCES recordings(id),
  score NUMERIC NOT NULL,
  reasons JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (pick_date, user_id)
);
