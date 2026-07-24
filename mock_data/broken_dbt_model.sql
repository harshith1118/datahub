-- broken_dbt_model.sql
-- Simulates a dbt model that references an outdated column name.
-- The column `user_id` was renamed to `account_id` in the source schema.

WITH source AS (
    SELECT
        id,
        user_id,  -- BUG: column renamed to account_id
        email,
        created_at
    FROM raw.users
),

transformed AS (
    SELECT
        id,
        user_id AS customer_id,  -- BUG: column renamed to account_id
        email,
        created_at
    FROM source
)

SELECT * FROM transformed