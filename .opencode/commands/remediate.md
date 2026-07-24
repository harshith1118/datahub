# /remediate — Auto-Remediate Broken SQL Files

## Description

Fix broken SQL files by renaming outdated column references, create a GitHub PR,
and write a remediation status tag back to DataHub.

## Usage

```
/remediate <sql-path> [--pr-title "<title>"] [--dry-run]
```

## Workflow

1. Read the SQL file at `<sql-path>`.
2. Analyze the schema breaking change from `mock_data/schema_event.json` (or a
   real DataHub query if `DATAHUB_GMS_URL` is set).
3. Rename all occurrences of the old column to the new column name.
4. Write the fixed file back.
5. (If not `--dry-run`): Create a git branch, commit, and open a PR via GitHub.
6. (If not `--dry-run`): Write `STATUS: FIX_PENDING_PR_<id>` tag back to DataHub.

## Example

```
/remediate mock_data/broken_dbt_model.sql --pr-title "Fix user_id -> account_id rename"
```