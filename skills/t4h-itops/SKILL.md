---
name: t4h-itops
description: GenAI ITOps skill for T4H autonomous operations. Use when handling infrastructure incidents, running diagnostic runbooks, checking system health, or routing operational issues across T4H's 28-business portfolio. Triggers on: "incident", "site down", "create alert", "run runbook", "health check", "triage", "itops", "infrastructure issue".
---

# T4H GenAI ITOps

Autonomous IT operations for the T4H portfolio. All state stored in Supabase. Executed via T4H bridge.

## Invoke Pattern

All actions via bridge:
```json
{"fn": "genai-itops", "action": "<action>", ...params}
```

## Actions

### Incident Management
| Action | Params | Notes |
|--------|--------|-------|
| `create_incident` | title, description, biz_key?, severity? | Auto-triages + runs runbook for critical/high |
| `update_incident` | incident_id, status?, resolution?, notes? | Lifecycle update |
| `get_open_incidents` | domain?, limit? | Filter by autonomy domain |
| `incident_summary` | — | Count by severity/status |

### Runbooks
| Action | Params | Notes |
|--------|--------|-------|
| `execute_runbook` | runbook_id, incident_id | Runs steps, logs to itops_runbook_step_log |
| `find_runbook` | title, severity | Claude-matched best runbook |
| `list_runbooks` | — | All active runbooks |
| `upsert_runbook` | slug, title, trigger_keywords, steps | Steps = JSON array |

### Health
| Action | Params | Notes |
|--------|--------|-------|
| `snapshot_health` | biz_key? | Runs all checks, stores snapshot, raises alerts |
| `health_trend` | biz_key?, hours? | Time series |
| `get_open_alerts` | severity? | Current open alerts |

## Routing Rules
- `database/supabase/lambda` → **dataops**
- `site/network/api/vercel/dns/auth` → **websiteops**
- `payment/billing/stripe` → **financeops**
- default → **taskops**

## Seeded Runbooks
- `site-down-triage` — Vercel/DNS recovery
- `database-error-triage` — pg_stat_activity + connection check
- `payment-failure-triage` — Stripe webhook analysis
- `lambda-error-triage` — Worker failure + HITL log scan
- `rdti-evidence-gap` — RDTI deadline triage (RDTI-eligible)

## CC Page: `itops`
5 CCQs: incident_dashboard | health_trend | runbook_stats | open_alerts | incident_by_domain

## Tables
- `itops_incident` — lifecycle-managed incidents with RLS
- `itops_runbook` — runbook definitions with JSON steps
- `itops_runbook_run` + `itops_runbook_step_log` — execution history
- `itops_health_snapshot` — time-series health scores
- `itops_alert` — deduped alert stream

## Examples

```
"Create an incident: Vercel deployment failing for WFAI"
→ {"fn":"genai-itops","action":"create_incident","title":"Vercel deployment failing","biz_key":"wfai","description":"Deployment returning 500"}

"Run a health check"
→ {"fn":"genai-itops","action":"snapshot_health","biz_key":"t4h"}

"What incidents are open for financeops?"
→ {"fn":"genai-itops","action":"get_open_incidents","domain":"financeops"}
```

## RDTI Flag
`rdti-evidence-gap` runbook is `rdti_eligible=true`. All incident resolution activities supporting research infrastructure are RDTI-traceable via `biz_key` + T4H project codes.
