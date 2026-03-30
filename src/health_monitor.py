"""
Health Monitor — predictive infrastructure health analytics.
Snapshots stored in itops_health_snapshot. Alerts to itops_alert.
"""

import json
import datetime
import urllib.request
from bridge_client import sql, log_hitl


HEALTH_CHECKS = {
    "supabase": {
        "query": "SELECT COUNT(*) as c FROM pg_stat_activity WHERE state = 'active'",
        "threshold": 80,
        "metric": "active_connections"
    },
    "lambda_errors": {
        "query": """
            SELECT COUNT(*) as c FROM autonomy_hitl_queue
            WHERE resolved = false
            AND surfaced_at > NOW() - INTERVAL '1 hour'
        """,
        "threshold": 10,
        "metric": "unresolved_hitl_1h"
    },
    "autonomy_runs": {
        "query": """
            SELECT COUNT(*) as c FROM autonomy_execution_runs
            WHERE run_started_at > NOW() - INTERVAL '24 hours'
            AND evidence_class IS NOT NULL
        """,
        "threshold": 1,
        "metric": "evidenced_runs_24h",
        "check_type": "min"
    },
    "incident_open": {
        "query": """
            SELECT COUNT(*) as c FROM itops_incident
            WHERE status = 'open' AND severity IN ('critical', 'high')
        """,
        "threshold": 5,
        "metric": "critical_open"
    },
    "sites_down": {
        "query": """
            SELECT COUNT(*) as c FROM autonomy_signal_registry
            WHERE signal_type_key ILIKE '%SITE%DOWN%'
            OR (signal_type_key ILIKE '%SITE%' AND signal_status = 'open')
        """,
        "threshold": 0,
        "metric": "sites_down"
    }
}


def run_health_check(check_name: str, check_config: dict) -> dict:
    """Run a single health check and return score."""
    result = sql(check_config["query"])
    rows = result.get("rows", [])
    value = rows[0].get("c", 0) if rows else 0

    threshold = check_config["threshold"]
    check_type = check_config.get("check_type", "max")

    if check_type == "max":
        healthy = value <= threshold
        score = max(0, 100 - int((value / max(threshold, 1)) * 100))
    else:  # min — alert if below
        healthy = value >= threshold
        score = min(100, int((value / max(threshold, 1)) * 100))

    return {
        "check": check_name,
        "metric": check_config["metric"],
        "value": value,
        "threshold": threshold,
        "healthy": healthy,
        "score": score
    }


def snapshot_health(biz_key: str = "t4h") -> dict:
    """Run all health checks and store snapshot."""
    results = {}
    total_score = 0

    for name, config in HEALTH_CHECKS.items():
        try:
            check_result = run_health_check(name, config)
            results[name] = check_result
            total_score += check_result["score"]
        except Exception as e:
            results[name] = {"check": name, "error": str(e), "score": 0}

    overall_score = total_score // len(HEALTH_CHECKS)
    health_json = json.dumps(results).replace("'", "''")

    sql(f"""
        INSERT INTO itops_health_snapshot (biz_key, health_score, checks_json, checked_at)
        VALUES ('{biz_key}', {overall_score}, '{health_json}'::jsonb, NOW())
    """)

    # Raise alerts for unhealthy checks
    unhealthy = [r for r in results.values() if not r.get("healthy", True) and "error" not in r]
    for check in unhealthy:
        _raise_alert(
            title=f"Health check failed: {check['check']}",
            description=f"{check['metric']}={check['value']} (threshold={check['threshold']})",
            severity="high" if check["score"] < 30 else "medium",
            source="health_monitor",
            biz_key=biz_key
        )

    log_hitl("HEALTH_SNAPSHOT", biz_key, f"score={overall_score} unhealthy={len(unhealthy)}")
    return {
        "biz_key": biz_key,
        "overall_score": overall_score,
        "checks": results,
        "alerts_raised": len(unhealthy)
    }


def _raise_alert(title: str, description: str, severity: str,
                  source: str, biz_key: str) -> None:
    """Insert alert record (deduped by title + open status)."""
    sql(f"""
        INSERT INTO itops_alert (title, description, severity, source, biz_key, status, created_at)
        SELECT '{title.replace("'","''")}', '{description.replace("'","''")}',
               '{severity}', '{source}', '{biz_key}', 'open', NOW()
        WHERE NOT EXISTS (
            SELECT 1 FROM itops_alert
            WHERE title = '{title.replace("'","''")}' AND status = 'open'
        )
    """)


def get_health_trend(biz_key: str = "t4h", hours: int = 24) -> list:
    """Get health score trend over time."""
    result = sql(f"""
        SELECT health_score, checked_at
        FROM itops_health_snapshot
        WHERE biz_key = '{biz_key}'
        AND checked_at > NOW() - INTERVAL '{hours} hours'
        ORDER BY checked_at ASC
    """)
    return result.get("rows", [])


def get_open_alerts(severity: str = None) -> list:
    """Get open alerts."""
    where = "WHERE status = 'open'"
    if severity:
        where += f" AND severity = '{severity}'"
    result = sql(f"""
        SELECT id, title, severity, source, biz_key, created_at
        FROM itops_alert {where}
        ORDER BY
            CASE severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,
            created_at ASC
    """)
    return result.get("rows", [])
