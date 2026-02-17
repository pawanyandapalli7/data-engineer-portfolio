-- Fail if duplicate primary keys exist
SELECT {{ column_name }}, COUNT(*) AS cnt
FROM {{ table_name }}
GROUP BY {{ column_name }}
HAVING COUNT(*) > 1;
