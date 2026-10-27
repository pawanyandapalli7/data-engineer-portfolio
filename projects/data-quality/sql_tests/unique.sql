-- Fails (returns rows) when a key appears more than once.
-- Params: {{ table_name }}, {{ column_name }}
SELECT {{ column_name }}, COUNT(*) AS occurrences
FROM {{ table_name }}
WHERE {{ column_name }} IS NOT NULL
GROUP BY {{ column_name }}
HAVING COUNT(*) > 1;
