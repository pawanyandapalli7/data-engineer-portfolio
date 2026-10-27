-- Fails (returns rows) when a column holds a value outside the allowed set.
-- NULLs are reported too: `x NOT IN (...)` is NULL for a NULL x, so it would
-- silently pass them. Use a separate not_null test if NULL is allowed.
-- Params: {{ table_name }}, {{ column_name }}, {{ accepted_values }}  e.g. 'APPROVED','DENIED','PENDING'
SELECT {{ column_name }} AS bad_value, COUNT(*) AS rows_affected
FROM {{ table_name }}
WHERE {{ column_name }} IS NULL
   OR {{ column_name }} NOT IN ({{ accepted_values }})
GROUP BY {{ column_name }};
