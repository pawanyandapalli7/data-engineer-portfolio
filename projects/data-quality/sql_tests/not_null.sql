-- Fails (returns a row) when the column has NULLs.
-- Params: {{ table_name }}, {{ column_name }}
SELECT COUNT(*) AS null_rows
FROM {{ table_name }}
WHERE {{ column_name }} IS NULL
HAVING COUNT(*) > 0;
