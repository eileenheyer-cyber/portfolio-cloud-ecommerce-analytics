-- ============================================================
-- CREATE SCHEMAS
-- One schema per layer of the data pipeline:
--   raw     : data as it comes from the sources (loaded by Python)
--   staging : cleaned data (built by dbt)
--   mart    : star schema for Power BI (built by dbt)
-- ============================================================

-- CREATE SCHEMA must be the only statement in its batch,
-- so it is run through EXEC inside the IF check

IF SCHEMA_ID('raw') IS NULL
    EXEC('CREATE SCHEMA raw');

IF SCHEMA_ID('staging') IS NULL
    EXEC('CREATE SCHEMA staging');

IF SCHEMA_ID('mart') IS NULL
    EXEC('CREATE SCHEMA mart');

-- Check: all three schemas should be listed
SELECT name AS schema_name
FROM sys.schemas
WHERE name IN ('raw', 'staging', 'mart');
