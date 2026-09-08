-- plainto_tsquery ANDs every lexeme; this variant ORs them so ts_rank_cd can rank partial matches.
CREATE OR REPLACE FUNCTION _codeplumb_or_query(q text) RETURNS tsquery
LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT CASE WHEN plainto_tsquery('english', q)::text = '' THEN NULL::tsquery
              ELSE replace(plainto_tsquery('english', q)::text, ' & ', ' | ')::tsquery END
$$;
