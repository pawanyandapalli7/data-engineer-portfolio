-- The same controls on Databricks Unity Catalog: SQL UDFs attached as a column
-- mask and a row filter. Group membership replaces Snowflake roles.

CREATE OR REPLACE FUNCTION governance.mask_ssn(ssn STRING)
  RETURNS STRING
  RETURN CASE
    WHEN is_account_group_member('phi_full') THEN ssn
    WHEN is_account_group_member('phi_partial') THEN concat('XXX-XX-', right(ssn, 4))
    ELSE '***MASKED***'
  END;

ALTER TABLE curated.members ALTER COLUMN ssn SET MASK governance.mask_ssn;

CREATE OR REPLACE FUNCTION governance.lob_filter(lob STRING)
  RETURNS BOOLEAN
  RETURN is_account_group_member('phi_full') OR is_account_group_member(concat('lob_', lower(lob)));

ALTER TABLE curated.claims SET ROW FILTER governance.lob_filter ON (line_of_business);
