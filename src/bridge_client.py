"""
T4H Bridge Client for GenAI ITOps
Wraps the T4H bridge (AWS API Gateway → Lambda → Supabase) for ITOps operations.
"""

import os
import json
import urllib.request
import urllib.error
from typing import Any, Optional

BRIDGE_URL = os.environ.get(
    "T4H_BRIDGE_URL",
    "https://m5oqj21chd.execute-api.ap-southeast-2.amazonaws.com/lambda/invoke"
)
BRIDGE_API_KEY = os.environ.get("T4H_BRIDGE_API_KEY", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://lzfgigiyqpuuxslsygjt.supabase.co")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")


def bridge_sql(sql: str, return_type: str = "rows") -> dict:
    """Execute SQL via T4H bridge (troy-sql-executor)."""
    payload = json.dumps({
        "fn": "troy-sql-executor",
        "route": "sql",
        "sql": sql,
        "return_type": return_type
    }).encode()

    req = urllib.request.Request(
        BRIDGE_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": BRIDGE_API_KEY
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"success": False, "error": str(e), "body": e.read().decode()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def supabase_sql(sql: str) -> dict:
    """Fallback: Supabase REST exec_sql RPC."""
    payload = json.dumps({"query": sql}).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/rpc/exec_sql",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "apikey": SUPABASE_SERVICE_KEY
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return {"success": True, "rows": json.loads(resp.read())}
    except Exception as e:
        return {"success": False, "error": str(e)}


def sql(query: str, return_type: str = "rows") -> dict:
    """Execute SQL via bridge with Supabase fallback."""
    result = bridge_sql(query, return_type)
    if not result.get("success"):
        result = supabase_sql(query)
    return result


def log_hitl(action: str, target: str, result: str) -> None:
    """Log action to T4H HITL log."""
    import datetime
    utc = datetime.datetime.utcnow().isoformat() + "Z"
    print(f"[LOG] {action}|{target}|{result}|{utc}")
    sql(f"""
        INSERT INTO hitl_log (action, target, result, created_at)
        VALUES ('{action}', '{target}', '{result}', NOW())
        ON CONFLICT DO NOTHING
    """)
