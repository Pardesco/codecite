-- project renamed codeplumb -> codecite; same OR-query helper under the new name
CREATE OR REPLACE FUNCTION _codecite_or_query(q text) RETURNS tsquery
LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT CASE WHEN plainto_tsquery('english', q)::text = '' THEN NULL::tsquery
              ELSE replace(plainto_tsquery('english', q)::text, ' & ', ' | ')::tsquery END
$$;
DROP FUNCTION IF EXISTS _codeplumb_or_query(text);
