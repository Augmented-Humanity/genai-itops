"""
GenAI ITOps — Lambda Handler
Routes: incident | runbook | health | alert

Invoke via T4H bridge:
  {"fn": "genai-itops", "action": "create_incident", "title": "...", "description": "..."}
  {"fn": "genai-itops", "action": "snapshot_health", "biz_key": "t4h"}
  {"fn": "genai-itops", "action": "execute_runbook", "runbook_id": "...", "incident_id": "..."}
  {"fn": "genai-itops", "action": "get_open_incidents"}
  {"fn": "genai-itops", "action": "get_open_alerts"}
"""

import json
import os
import sys
sys.path.insert(0, os.path.dirname(__file__) + "/src")

from incident_manager import (
    create_incident, update_incident, get_open_incidents, get_incident_summary
)
from runbook_executor import (
    execute_runbook, find_runbook, list_runbooks, upsert_runbook
)
from health_monitor import (
    snapshot_health, get_health_trend, get_open_alerts
)
from bridge_client import log_hitl


def lambda_handler(event, context):
    action = event.get("action", "")

    try:
        # ── INCIDENTS ──────────────────────────────────────
        if action == "create_incident":
            result = create_incident(
                title=event.get("title", "Untitled Incident"),
                description=event.get("description", ""),
                source=event.get("source", "manual"),
                biz_key=event.get("biz_key"),
                metadata=event.get("metadata", {})
            )

            # Auto-find and execute runbook if critical/high
            if result.get("severity") in ("critical", "high"):
                rb = find_runbook(event.get("title", ""), result["severity"])
                if rb:
                    rb_result = execute_runbook(rb["id"], result["incident_id"])
                    result["auto_runbook"] = rb_result

            return {"statusCode": 200, "body": result}

        elif action == "update_incident":
            result = update_incident(
                incident_id=event.get("incident_id"),
                status=event.get("status"),
                resolution=event.get("resolution"),
                notes=event.get("notes")
            )
            return {"statusCode": 200, "body": result}

        elif action == "get_open_incidents":
            rows = get_open_incidents(
                domain=event.get("domain"),
                limit=event.get("limit", 20)
            )
            return {"statusCode": 200, "body": rows}

        elif action == "incident_summary":
            return {"statusCode": 200, "body": get_incident_summary()}

        # ── RUNBOOKS ───────────────────────────────────────
        elif action == "execute_runbook":
            result = execute_runbook(
                runbook_id=event.get("runbook_id"),
                incident_id=event.get("incident_id"),
                context=event.get("context", {})
            )
            return {"statusCode": 200, "body": result}

        elif action == "find_runbook":
            rb = find_runbook(
                incident_title=event.get("title", ""),
                severity=event.get("severity", "medium")
            )
            return {"statusCode": 200, "body": rb}

        elif action == "list_runbooks":
            return {"statusCode": 200, "body": list_runbooks()}

        elif action == "upsert_runbook":
            result = upsert_runbook(
                slug=event.get("slug"),
                title=event.get("title"),
                trigger_keywords=event.get("trigger_keywords", ""),
                steps=event.get("steps", []),
                priority=event.get("priority", 50),
                estimated_minutes=event.get("estimated_minutes", 15)
            )
            return {"statusCode": 200, "body": result}

        # ── HEALTH ─────────────────────────────────────────
        elif action == "snapshot_health":
            result = snapshot_health(biz_key=event.get("biz_key", "t4h"))
            return {"statusCode": 200, "body": result}

        elif action == "health_trend":
            rows = get_health_trend(
                biz_key=event.get("biz_key", "t4h"),
                hours=event.get("hours", 24)
            )
            return {"statusCode": 200, "body": rows}

        elif action == "get_open_alerts":
            rows = get_open_alerts(severity=event.get("severity"))
            return {"statusCode": 200, "body": rows}

        else:
            return {
                "statusCode": 400,
                "body": {
                    "error": f"Unknown action: {action}",
                    "valid_actions": [
                        "create_incident", "update_incident", "get_open_incidents", "incident_summary",
                        "execute_runbook", "find_runbook", "list_runbooks", "upsert_runbook",
                        "snapshot_health", "health_trend", "get_open_alerts"
                    ]
                }
            }

    except Exception as e:
        log_hitl("ERROR", action, str(e))
        return {"statusCode": 500, "body": {"error": str(e), "action": action}}
