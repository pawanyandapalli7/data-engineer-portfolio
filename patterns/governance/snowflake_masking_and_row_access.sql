-- PHI protection in Snowflake: policy-based column masking plus row-level
-- access, so the rule lives on the column/table, not in every view.
-- Dynamic masking and row access policies require Enterprise edition or higher.

-- Members' SSNs: only the PHI_FULL role sees the value; analysts see the last 4.
CREATE OR REPLACE MASKING POLICY governance.mask_ssn AS (val STRING) RETURNS STRING ->
  CASE
    WHEN IS_ROLE_IN_SESSION('PHI_FULL') THEN val
    WHEN IS_ROLE_IN_SESSION('PHI_PARTIAL') THEN 'XXX-XX-' || RIGHT(val, 4)
    ELSE '***MASKED***'
  END;

-- Dates of birth: analysts get the year only (full dates are a HIPAA identifier).
CREATE OR REPLACE MASKING POLICY governance.mask_dob AS (val DATE) RETURNS DATE ->
  CASE WHEN IS_ROLE_IN_SESSION('PHI_FULL') THEN val ELSE DATE_FROM_PARTS(YEAR(val), 1, 1) END;

ALTER TABLE curated.members MODIFY COLUMN ssn           SET MASKING POLICY governance.mask_ssn;
ALTER TABLE curated.members MODIFY COLUMN date_of_birth SET MASKING POLICY governance.mask_dob;

-- Row access: users only see the lines of business they're entitled to.
CREATE TABLE IF NOT EXISTS governance.lob_entitlements (role_name STRING, line_of_business STRING);

CREATE OR REPLACE ROW ACCESS POLICY governance.rap_lob AS (lob STRING) RETURNS BOOLEAN ->
  IS_ROLE_IN_SESSION('PHI_FULL')
  OR EXISTS (
      SELECT 1 FROM governance.lob_entitlements e
      WHERE e.line_of_business = lob AND IS_ROLE_IN_SESSION(e.role_name)
  );

ALTER TABLE curated.claims ADD ROW ACCESS POLICY governance.rap_lob ON (line_of_business);

-- Audit: who read PHI columns in the last 7 days (ACCESS_HISTORY: Enterprise edition).
SELECT ah.query_start_time, ah.user_name, obj.value:"objectName"::STRING AS object_name, col.value:"columnName"::STRING AS column_name
FROM snowflake.account_usage.access_history ah,
     LATERAL FLATTEN(ah.base_objects_accessed) obj,
     LATERAL FLATTEN(obj.value:"columns") col
WHERE ah.query_start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP())
  AND col.value:"columnName"::STRING IN ('SSN', 'DATE_OF_BIRTH')
ORDER BY ah.query_start_time DESC;
