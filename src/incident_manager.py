"""
Incident Manager — triage, routing, and lifecycle management.
All state persisted to itops_incident table in Supabase.
"""

import json
import uuid
import datetime
from bridge_client import sql, log_hitl

SEVERITY_MAP = {
    "critical": 1, "high": 2, "medium": 3, "low": 4, "info": 5
}

ROUTING_RULES = {
    "database": "dataops",
    "network": "websiteops",
    "auth": "websiteops",
    "payment": "financeops",
    "billing": "financeops",
    "lambda": "dataops",
    "api": "websiteops",
    "site": "websiteops",
    "certificate": "websiteops",
    "dns": "websiteops",
    "stripe": "financeops",
    "supabase": "dataops",
    "vercel": "websiteops",
    "aws": "dataops",
    "deploy": "dataops",
}


def classify_severity(title: str, description: str) -> str:
    """Classify incident severity from content."""
    text = (title + " " + description).lower()
    if any(w in text for w in ["down", "outage", "breach", "data loss", "critical", "production"]):
        return "critical"
    if any(w in text for w in ["error", "failing", "degraded", "slow", "high"]):
        return "high"
    if any(w in text for w in ["warning", "intermittent", "partial"]):
        return "medium"
    return "low"


def route_incident(title: str, description: str) -> str:
    """Determine which worker domain owns this incident."""
    text = (title + " " + description).lower()
    for keyword, domain in ROUTING_RULES.items():
        if keyword in text:
            return domain
    return "taskops"  # default


def create_incident(title: str, description: str, source: str = "manual",
                    biz_key: str = None, metadata: dict = None) -> dict:
    """Create and triage a new incident."""
    incident_id = str(uuid.uuid4())
    severity = classify_severity(title, description)
    routed_to = route_incident(title, description)
    now = datetime.datetime.utcnow().isoformat() + "Z"
    meta_json = json.dumps(metadata or {}).replace("'", "''")

    result = sql(f"""
        INSERT INTO itops_incident (
            id, title, description, severity, status,
            routed_to, source, biz_key, metadata, created_at, updated_at
        ) VALUES (
            '{incident_id}',
            '{title.replace("'", "''")}',
            '{description.replace("'", "''")}',
            '{severity}',
            'open',
            '{routed_to}',
            '{source}',
            {f"'{biz_key}'" if biz_key else 'NULL'},
            '{meta_json}'::jsonb,
            NOW(), NOW()
        ) RETURNING id, severity, routed_to
    """)

    log_hitl("CREATE_INCIDENT", incident_id, f"{severity}/{routed_to}")
    return {
        "incident_id": incident_id,
        "severity": severity,
        "routed_to": routed_to,
        "status": "open",
        "result": result
    }


def update_incident(incident_id: str, status: str = None, resolution: str = None,
                    notes: str = None) -> dict:
    """Update incident status/resolution."""
    parts = ["updated_at = NOW()"]
    if status:
        parts.append(f"status = '{status}'")
    if resolution:
        parts.append(f"resolution = '{resolution.replace(chr(39), chr(39)*2)}'")
    if notes:
        parts.append(f"notes = '{notes.replace(chr(39), chr(39)*2)}'")
    if status == "resolved":
        parts.append("resolved_at = NOW()")

    sql_str = f"UPDATE itops_incident SET {', '.join(parts)} WHERE id = '{incident_id}' RETURNING id, status"
    result = sql(sql_str)
    log_hitl("UPDATE_INCIDENT", incident_id, status or "notes_added")
    return result


def get_open_incidents(domain: str = None, limit: int = 20) -> list:
    """Fetch open incidents, optionally filtered by domain."""
    where = "WHERE status = 'open'"
    if domain:
        where += f" AND routed_to = '{domain}'"
    result = sql(f"""
        SELECT id, title, severity, routed_to, source, biz_key, created_at
        FROM itops_incident
        {where}
        ORDER BY severity ASC, created_at ASC
        LIMIT {limit}
    """)
    return result.get("rows", [])


def get_incident_summary() -> dict:
    """Dashboard summary of incident counts by severity/status."""
    result = sql("""
        SELECT
            status,
            severity,
            COUNT(*) as count
        FROM itops_incident
        GROUP BY status, severity
        ORDER BY status, severity
    """)
    return result.get("rows", [])
