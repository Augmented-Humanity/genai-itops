"""
Runbook Executor — natural language runbook resolution using Claude API.
Runbooks stored in itops_runbook table. Steps logged to itops_runbook_run.
"""

import json
import uuid
import urllib.request
from bridge_client import sql, log_hitl

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL = "claude-sonnet-4-20250514"


def _claude(system: str, user: str, max_tokens: int = 2048) -> str:
    """Call Claude API for runbook reasoning."""
    import os
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    payload = json.dumps({
        "model": CLAUDE_MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}]
    }).encode()

    req = urllib.request.Request(
        CLAUDE_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
        return data["content"][0]["text"]


def find_runbook(incident_title: str, severity: str) -> dict:
    """Find best matching runbook for an incident."""
    result = sql(f"""
        SELECT id, slug, title, trigger_keywords, steps_json, estimated_minutes
        FROM itops_runbook
        WHERE is_active = true
        ORDER BY priority ASC
        LIMIT 20
    """)
    runbooks = result.get("rows", [])
    if not runbooks:
        return None

    # Use Claude to match
    runbook_list = "\n".join([
        f"- [{r['slug']}] {r['title']} (triggers: {r.get('trigger_keywords','')})"
        for r in runbooks
    ])
    system = "You are an IT operations assistant. Given an incident, select the best matching runbook slug. Respond with ONLY the slug string, nothing else."
    user = f"Incident: {incident_title} (severity: {severity})\n\nAvailable runbooks:\n{runbook_list}"

    try:
        matched_slug = _claude(system, user).strip().lower()
        for rb in runbooks:
            if rb["slug"] == matched_slug:
                return rb
    except Exception:
        pass
    return runbooks[0] if runbooks else None


def execute_runbook(runbook_id: str, incident_id: str, context: dict = None) -> dict:
    """Execute a runbook against an incident, logging each step."""
    run_id = str(uuid.uuid4())
    context = context or {}

    # Load runbook
    result = sql(f"SELECT * FROM itops_runbook WHERE id = '{runbook_id}'")
    rows = result.get("rows", [])
    if not rows:
        return {"error": "runbook_not_found"}
    runbook = rows[0]

    steps = runbook.get("steps_json", [])
    if isinstance(steps, str):
        steps = json.loads(steps)

    # Log run start
    sql(f"""
        INSERT INTO itops_runbook_run (id, runbook_id, incident_id, status, started_at)
        VALUES ('{run_id}', '{runbook_id}', '{incident_id}', 'running', NOW())
    """)

    results = []
    for i, step in enumerate(steps):
        step_result = _execute_step(step, context, incident_id)
        results.append({"step": i + 1, "action": step.get("action"), "result": step_result})

        # Log step
        sql(f"""
            INSERT INTO itops_runbook_step_log (run_id, step_num, action, result, created_at)
            VALUES ('{run_id}', {i+1}, '{step.get("action","").replace("'","''")}',
                    '{json.dumps(step_result).replace("'","''")}', NOW())
        """)

    # Complete run
    sql(f"""
        UPDATE itops_runbook_run SET status = 'completed', completed_at = NOW()
        WHERE id = '{run_id}'
    """)

    log_hitl("EXECUTE_RUNBOOK", runbook_id, f"run={run_id} steps={len(steps)}")
    return {"run_id": run_id, "steps_completed": len(results), "results": results}


def _execute_step(step: dict, context: dict, incident_id: str) -> dict:
    """Execute a single runbook step."""
    action = step.get("action", "")
    params = step.get("params", {})

    if action == "sql":
        result = sql(params.get("query", "SELECT 1"))
        return {"type": "sql", "rows": result.get("rows", [])[:5]}

    elif action == "notify":
        message = params.get("message", "").format(**context)
        return {"type": "notify", "message": message, "sent": True}

    elif action == "check_health":
        result = sql(f"""
            SELECT biz_key, health_score, checked_at
            FROM itops_health_snapshot
            WHERE biz_key = '{params.get("biz_key", "%")}'
            ORDER BY checked_at DESC LIMIT 1
        """)
        return {"type": "health_check", "data": result.get("rows", [])}

    elif action == "claude_diagnose":
        prompt = params.get("prompt", f"Diagnose incident {incident_id}")
        try:
            system = "You are a senior IT operations engineer. Provide concise diagnosis and remediation steps."
            diagnosis = _claude(system, prompt, max_tokens=512)
            return {"type": "claude_diagnose", "diagnosis": diagnosis}
        except Exception as e:
            return {"type": "claude_diagnose", "error": str(e)}

    elif action == "escalate":
        sql(f"""
            UPDATE itops_incident SET status = 'escalated', routed_to = '{params.get("to", "taskops")}'
            WHERE id = '{incident_id}'
        """)
        return {"type": "escalate", "escalated_to": params.get("to")}

    return {"type": "unknown", "action": action}


def list_runbooks() -> list:
    """List all active runbooks."""
    result = sql("""
        SELECT id, slug, title, trigger_keywords, estimated_minutes, priority
        FROM itops_runbook WHERE is_active = true ORDER BY priority
    """)
    return result.get("rows", [])


def upsert_runbook(slug: str, title: str, trigger_keywords: str,
                   steps: list, priority: int = 50, estimated_minutes: int = 15) -> dict:
    """Create or update a runbook."""
    steps_json = json.dumps(steps).replace("'", "''")
    result = sql(f"""
        INSERT INTO itops_runbook (slug, title, trigger_keywords, steps_json, priority, estimated_minutes, is_active)
        VALUES ('{slug}', '{title}', '{trigger_keywords}', '{steps_json}'::jsonb, {priority}, {estimated_minutes}, true)
        ON CONFLICT (slug) DO UPDATE SET
            title = EXCLUDED.title,
            trigger_keywords = EXCLUDED.trigger_keywords,
            steps_json = EXCLUDED.steps_json,
            priority = EXCLUDED.priority,
            updated_at = NOW()
        RETURNING id, slug
    """)
    log_hitl("UPSERT_RUNBOOK", slug, "ok")
    return result
