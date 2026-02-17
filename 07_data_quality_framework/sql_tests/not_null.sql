-- Fail if any primary keys are NULL
SELECT *
FROM {{ table_name }}
WHERE {{ column_name }} IS NULL;
