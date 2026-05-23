MATCH (b:Button)-[:TRANSITIONS_TO]->(s:Screen)
RETURN b.id AS source_id, b.selector AS source_selector, s.id AS target_screen

UNION

MATCH (j:JsFunction)-[:TRANSITIONS_TO]->(s:Screen)
RETURN j.name AS source_id, null AS source_selector, s.id AS target_screen
