# DataHub-Sentinel — Agent Guide

## Project Overview

DataHub-Sentinel is an autonomous AI agent that monitors DataHub for schema diffs,
analyzes downstream lineage, uses OpenCode to write SQL fix PRs, and writes resolution
status back to the DataHub metadata graph.

Hackathon track: [Agents That Do Real Work](https://datahub.devpost.com/)

## Architecture

```
+-----------------+      1. Fetch Schema & Lineage       +----------------------+
|   DataHub GMS   | ----------------------------------->  |  Sentinel Agent Core |
| (MCP / GraphQL) | <-----------------------------------  |   (Python / Typer)   |
+-----------------+      4. Write-Back Status Tag        +----------+-----------+
                                                                      |
                                                                      | 2. Prompt Code
                                                                      |    Refactor
                                                                      v
+-----------------+      3. Push Branch & Create PR      +----------------------+
|  GitHub Repo    | <-----------------------------------  |    OpenCode CLI      |
|  (Target Code)  |                                       | (Automated Refactor) |
+-----------------+                                       +----------------------+
```

## Workflow (Agent Execution Steps)

1. **DataHub Context Ingestion** — Query DataHub GMS for schema drift events and
   downstream dbt/Airflow dependencies via `src/datahub_client.py`.
2. **Code Refactoring** — Pass broken SQL files and schema diffs to OpenCode CLI to
   automatically fix broken column references.
3. **GitHub PR Automation** — Create a branch, commit fixes, and open a PR via
   `src/github_client.py` (PyGithub).
4. **DataHub Write-Back** — Tag the affected dataset in DataHub with
   `STATUS: FIX_PENDING_PR_#<id>` and attach an incident link.

## Directory Conventions

| Path | Purpose |
|------|---------|
| `src/main.py` | Typer CLI entrypoint — commands: `remediate`, `pr`, `status` |
| `src/datahub_client.py` | DataHub GMS/MCP SDK wrapper (read lineage + write tags) |
| `src/github_client.py` | PyGithub wrapper for branching, committing, and PR creation |
| `mock_data/` | Sample broken dbt models and schema events for testing |
| `examples/` | Pre-generated PR diffs and DataHub write-back payloads for judges |
| `.opencode/commands/remediate.md` | Custom OpenCode slash-command for auto-remediation |
| `.opencode.json` | OpenCode MCP server configuration |

## Guidelines for AI Agents

- **Style**: Follow existing patterns in `src/` — use Typer for CLI, Pydantic for models.
- **Dependencies**: Only use packages listed in `requirements.txt`.
- **Environment Variables**: `DATAHUB_GMS_URL`, `DATAHUB_TOKEN`, `GITHUB_TOKEN`,
  `GITHUB_REPO` — read from `os.environ` with sensible defaults for local dev.
- **Testing**: Run against `mock_data/` first; never require a real DataHub instance
  for basic validation.
- **PRs**: Branch naming convention: `fix/datahub-schema-remediation`.
- **DataHub Tags**: Use `STATUS: FIX_PENDING_PR_<pr_number>` format for write-back.