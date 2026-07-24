# DataHub-Sentinel

An autonomous AI agent that monitors **DataHub** for schema drift events, analyzes downstream lineage, uses **OpenCode** to auto-fix broken SQL column references, creates **GitHub Pull Requests**, and writes remediation status back to the DataHub metadata graph — all without human intervention.

[![License](https://img.shields.io/badge/License-Apache%202.0-green)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12+-yellow?logo=python)](https://python.org)

---

## Problem

When a production database renames or drops a column, downstream dbt models and Airflow DAGs break *silently*. Engineers waste hours tracking down the root cause, fixing SQL, and updating incident trackers. **DataHub-Sentinel** closes the loop automatically.

## Solution

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

### How it works

| Step | Action | Component |
|------|--------|-----------|
| 1 | Queries DataHub GMS for schema drift events & downstream dbt/Airflow dependencies | `src/datahub_client.py` |
| 2 | Passes broken SQL and schema diffs to OpenCode CLI to fix column references | `.opencode/commands/remediate.md` |
| 3 | Creates a git branch, commits fixes, and opens a Pull Request | `src/github_client.py` |
| 4 | Tags the affected dataset with `STATUS: FIX_PENDING_PR_<id>` and attaches an incident link | `src/datahub_client.py` |

---

## Quick Start

### Prerequisites

- Python 3.12+
- A local or remote DataHub GMS instance (or use `mock_data/` for testing)

### Setup

```bash
# Clone the repository
git clone <repo-url>
cd datahub-sentinel

# Create virtual environment and install dependencies
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt

# Configure environment variables (optional — mock_data works without these)
set DATAHUB_GMS_URL=http://localhost:8080
set DATAHUB_TOKEN=your-token
set GITHUB_TOKEN=your-github-token
set GITHUB_REPO=owner/repo-name
```

### Run the full pipeline (dry-run)

```bash
python src/main.py remediate --dry-run
```

This runs the complete remediation workflow against the bundled mock data — no external services required.

### Available commands

```bash
# Full remediation pipeline
python src/main.py remediate \
    --sql-path mock_data/broken_dbt_model.sql \
    --event-path mock_data/schema_event.json

# Preview only (no API calls)
python src/main.py remediate --dry-run

# Submit a pre-fixed SQL file as a PR
python src/main.py pr path/to/fixed/file.sql --pr-title "fix: rename user_id to account_id"

# Inspect a dataset's schema and lineage via DataHub
python src/main.py status "urn:li:dataset:(urn:li:dataPlatform:postgres,raw.users,PROD)"

# View all options
python src/main.py remediate --help
python src/main.py pr --help
python src/main.py status --help
```

---

## Project Structure

```
datahub-sentinel/
├── .opencode/
│   ├── commands/
│   │   └── remediate.md           # OpenCode custom slash-command
│   └── .opencode.json             # MCP server configuration
├── src/
│   ├── datahub_client.py          # DataHub GMS SDK wrapper (GraphQL + REST)
│   ├── github_client.py           # PyGithub PR automation
│   └── main.py                    # Typer CLI (remediate / pr / status)
├── mock_data/
│   ├── broken_dbt_model.sql       # dbt model with outdated column reference
│   └── schema_event.json          # Simulated schema drift event payload
├── examples/                      # Pre-generated artifacts for judges
│   ├── sample_pr_diff.patch
│   └── datahub_writeback.json
├── AGENTS.md                      # AI agent architecture & workflow guide
├── LICENSE                        # Apache 2.0
├── README.md                      # This file
└── requirements.txt
```

---

## Judge Submission Artifacts

The `examples/` directory contains pre-generated outputs so judges can inspect the agent's work without a live environment:

| File | What it shows |
|------|--------------|
| `examples/sample_pr_diff.patch` | Unified git diff of the automated SQL fix — `user_id` → `account_id` across 2 column references in `broken_dbt_model.sql` |
| `examples/datahub_writeback.json` | Complete JSON payloads sent to DataHub GMS: the `addTag` GraphQL mutation for `STATUS: FIX_PENDING_PR_42` and the `institutionalMemory` REST payload linking to the fix PR |

### Submission Checklist

- [x] **Apache 2.0 License** — `LICENSE` at repo root
- [x] **Examples Folder** — PR diff + DataHub write-back JSON in `examples/`
- [ ] **Demo Video** — <3 min YouTube walkthrough: schema change → `remediate` → PR created → DataHub tag updated

---

## Environment Variables

| Variable | Default | Required for | Description |
|----------|---------|-------------|-------------|
| `DATAHUB_GMS_URL` | `http://localhost:8080` | Live DataHub | DataHub GMS endpoint |
| `DATAHUB_TOKEN` | `""` | Live DataHub | DataHub API token |
| `GITHUB_TOKEN` | `""` | Live PR creation | GitHub personal access token |
| `GITHUB_REPO` | `""` | Live PR creation | Target GitHub repo (`owner/repo`) |

> All commands support `--dry-run` mode — you can test the full pipeline against the bundled `mock_data/` without setting any environment variables.