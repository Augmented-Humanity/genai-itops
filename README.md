# GenAI ITOps

> AI-powered IT Operations automation for the T4H 28-business autonomous stack

## Overview

GenAI ITOps provides intelligent automation for IT service management, incident response, and infrastructure optimization. Wired to the T4H bridge (AWS API Gateway → Lambda → Supabase).

## Features

- 🤖 **Automated incident triage and routing** — severity classification + domain routing (websiteops/financeops/dataops/taskops)
- 📊 **Predictive health analytics** — time-series snapshots across T4H infrastructure checks
- 🔧 **Self-healing runbook execution** — Claude-matched runbooks with SQL + LLM + notify steps
- 📝 **Natural language runbook authoring** — JSON step definitions with `sql`, `claude_diagnose`, `notify`, `escalate`, `check_health` actions
- 🔗 **T4H bridge native** — all execution via `troy-sql-executor`, zero direct DB connections

## Architecture

```
T4H Bridge
    └── genai-itops Lambda
            ├── src/incident_manager.py    → itops_incident
            ├── src/runbook_executor.py    → itops_runbook + itops_runbook_run
            ├── src/health_monitor.py      → itops_health_snapshot + itops_alert
            └── src/bridge_client.py       → troy-sql-executor (bridge + Supabase fallback)
```

## Schema (5 tables + 3 views)

| Table | Purpose |
|-------|---------|
| `itops_incident` | Incident lifecycle with severity/status/routing |
| `itops_runbook` | Runbook definitions with JSON step arrays |
| `itops_runbook_run` | Execution history per incident |
| `itops_runbook_step_log` | Per-step output log |
| `itops_health_snapshot` | Time-series health scores per biz_key |
| `itops_alert` | Deduped alert stream |

## Deploy

### 1. Schema
```bash
# Via bridge
curl -X POST https://m5oqj21chd.execute-api.ap-southeast-2.amazonaws.com/lambda/invoke \
  -H "x-api-key: $BRIDGE_KEY" \
  -d '{"fn":"troy-sql-executor","route":"sql","sql":"<contents of schema/001_itops_schema.sql>"}'
```

### 2. Lambda
```bash
# Zip and deploy
zip -r genai-itops.zip lambda_handler.py src/
aws s3 cp genai-itops.zip s3://troylatter-sydney-downloads/lambda-deployments/genai-itops/
# Deploy via troy-cfn-deployer or troy-lambda-deployer
```

### 3. Register in mcp_lambda_registry
```sql
INSERT INTO mcp_lambda_registry (fn_name, description, status, biz_key)
VALUES ('genai-itops', 'AI-powered ITOps: incident triage, runbook execution, health monitoring', 'ACTIVE', 't4h')
ON CONFLICT (fn_name) DO NOTHING;
```

### 4. Command Centre Page
CC page key: `itops` — 5 CCQs pre-registered in schema.

## Usage

```json
// Create incident (auto-triages + auto-runs runbook for critical/high)
{"fn": "genai-itops", "action": "create_incident", "title": "Vercel deploy failing", "biz_key": "wfai"}

// Health snapshot
{"fn": "genai-itops", "action": "snapshot_health", "biz_key": "t4h"}

// List open incidents for a domain
{"fn": "genai-itops", "action": "get_open_incidents", "domain": "websiteops"}

// Execute specific runbook
{"fn": "genai-itops", "action": "execute_runbook", "runbook_id": "...", "incident_id": "..."}
```

## Seeded Runbooks

| Slug | Triggers | RDTI |
|------|---------|------|
| `site-down-triage` | site, down, vercel, deployment | ❌ |
| `database-error-triage` | database, supabase, connection | ❌ |
| `payment-failure-triage` | payment, stripe, billing | ❌ |
| `lambda-error-triage` | lambda, worker, bridge | ❌ |
| `rdti-evidence-gap` | rdti, evidence, deadline | ✅ |

## Part of Tech 4 Humanity

Built by [Tech 4 Humanity](https://tech4humanity.com.au) | [Troy Latter](https://github.com/TML-4PM)

*Transforming IT operations through ethical AI*
