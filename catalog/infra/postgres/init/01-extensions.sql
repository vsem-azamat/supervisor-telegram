-- Extensions the schema depends on. Created here rather than in a migration so
-- that a fresh database is usable before Alembic has ever run.
--
--   pg_trgm     fuzzy matching on subject and institution names: a student
--               typing "matan" or "prijimacky" must still find them
--   unaccent    strips Czech diacritics so "prijimacky" matches "přijímačky"
--   btree_gist  lets the availability exclusion constraint combine an equality
--               test on helper_id with an overlap test on a time range
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS btree_gist;
--   vector      one embedding per passage of a subject, so a query can reach a
--               subject by meaning when neither the synonyms nor the trigram
--               can — see docs/data-model.md
CREATE EXTENSION IF NOT EXISTS vector;

-- unaccent() is STABLE, which bars it from expression indexes. This wrapper is
-- the standard workaround: same behaviour, marked IMMUTABLE, and the dictionary
-- is pinned so the promise actually holds.
CREATE OR REPLACE FUNCTION immutable_unaccent(text)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
STRICT
AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$;
