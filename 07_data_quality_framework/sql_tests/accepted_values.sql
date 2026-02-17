-- Fail if column contains unexpected values
SELECT *
FROM {{ table_name }}
WHERE {{ column_name }} NOT IN ('A', 'B', 'C');
