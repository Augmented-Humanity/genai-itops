-- GenAI ITOps Schema
-- Wired to T4H Supabase (lzfgigiyqpuuxslsygjt)
-- Execute via T4H bridge: troy-sql-executor

-- ============================================================
-- INCIDENTS
-- ============================================================
CREATE TABLE IF NOT EXISTS itops_incident (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    description     TEXT,
    severity        TEXT NOT NULL CHECK (severity IN ('critical','high','medium','low','info')),
    status          TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open','in_progress','escalated','resolved','closed')),
    routed_to       TEXT,                   -- autonomy domain: websiteops/financeops/dataops/taskops
    source          TEXT DEFAULT 'manual',  -- manual/health_monitor/webhook/autonomy
    biz_key         TEXT,                   -- T4H canonical 28 biz_key
    metadata        JSONB DEFAULT '{}',
    resolution      TEXT,
    notes           TEXT,
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE itops_incident ENABLE ROW LEVEL SECURITY;
CREATE POLICY itops_incident_service ON itops_incident
    USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_itops_incident_status ON itops_incident(status);
CREATE INDEX IF NOT EXISTS idx_itops_incident_severity ON itops_incident(severity);
CREATE INDEX IF NOT EXISTS idx_itops_incident_biz_key ON itops_incident(biz_key);

-- ============================================================
-- RUNBOOKS
-- ============================================================
CREATE TABLE IF NOT EXISTS itops_runbook (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug                TEXT UNIQUE NOT NULL,
    title               TEXT NOT NULL,
    trigger_keywords    TEXT,
    steps_json          JSONB NOT NULL DEFAULT '[]',
    priority            INTEGER DEFAULT 50,
    estimated_minutes   INTEGER DEFAULT 15,
    is_active           BOOLEAN DEFAULT true,
    rdti_eligible       BOOLEAN DEFAULT false,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE itops_runbook ENABLE ROW LEVEL SECURITY;
CREATE POLICY itops_runbook_service ON itops_runbook
    USING (auth.role() = 'service_role');

-- ============================================================
-- RUNBOOK RUNS
-- ============================================================
CREATE TABLE IF NOT EXISTS itops_runbook_run (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    runbook_id  UUID REFERENCES itops_runbook(id),
    incident_id UUID REFERENCES itops_incident(id),
    status      TEXT DEFAULT 'running' CHECK (status IN ('running','completed','failed')),
    started_at  TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

ALTER TABLE itops_runbook_run ENABLE ROW LEVEL SECURITY;
CREATE POLICY itops_runbook_run_service ON itops_runbook_run
    USING (auth.role() = 'service_role');

-- ============================================================
-- RUNBOOK STEP LOG
-- ============================================================
CREATE TABLE IF NOT EXISTS itops_runbook_step_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id      UUID REFERENCES itops_runbook_run(id),
    step_num    INTEGER NOT NULL,
    action      TEXT,
    result      JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE itops_runbook_step_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY itops_step_log_service ON itops_runbook_step_log
    USING (auth.role() = 'service_role');

-- ============================================================
-- HEALTH SNAPSHOTS
-- ============================================================
CREATE TABLE IF NOT EXISTS itops_health_snapshot (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    biz_key     TEXT DEFAULT 't4h',
    health_score INTEGER NOT NULL,
    checks_json JSONB DEFAULT '{}',
    checked_at  TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE itops_health_snapshot ENABLE ROW LEVEL SECURITY;
CREATE POLICY itops_health_service ON itops_health_snapshot
    USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_itops_health_biz ON itops_health_snapshot(biz_key, checked_at DESC);

-- ============================================================
-- ALERTS
-- ============================================================
CREATE TABLE IF NOT EXISTS itops_alert (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title       TEXT NOT NULL,
    description TEXT,
    severity    TEXT NOT NULL CHECK (severity IN ('critical','high','medium','low','info')),
    source      TEXT,
    biz_key     TEXT,
    status      TEXT DEFAULT 'open' CHECK (status IN ('open','acknowledged','resolved')),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

ALTER TABLE itops_alert ENABLE ROW LEVEL SECURITY;
CREATE POLICY itops_alert_service ON itops_alert
    USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_itops_alert_status ON itops_alert(status);

-- ============================================================
-- VIEWS
-- ============================================================

-- Active incident dashboard
CREATE OR REPLACE VIEW v_itops_incident_dashboard AS
SELECT
    i.id,
    i.title,
    i.severity,
    i.status,
    i.routed_to,
    i.biz_key,
    i.source,
    EXTRACT(EPOCH FROM (NOW() - i.created_at))/3600 AS age_hours,
    (SELECT COUNT(*) FROM itops_runbook_run r WHERE r.incident_id = i.id) AS run_count
FROM itops_incident i
WHERE i.status NOT IN ('resolved','closed')
ORDER BY
    CASE i.severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,
    i.created_at ASC;

-- Health trend (last 24h)
CREATE OR REPLACE VIEW v_itops_health_trend_24h AS
SELECT
    biz_key,
    ROUND(AVG(health_score)) AS avg_score,
    MIN(health_score) AS min_score,
    MAX(health_score) AS max_score,
    COUNT(*) AS snapshot_count,
    MAX(checked_at) AS last_checked
FROM itops_health_snapshot
WHERE checked_at > NOW() - INTERVAL '24 hours'
GROUP BY biz_key;

-- Runbook effectiveness
CREATE OR REPLACE VIEW v_itops_runbook_stats AS
SELECT
    rb.slug,
    rb.title,
    COUNT(rr.id) AS total_runs,
    COUNT(rr.id) FILTER (WHERE rr.status = 'completed') AS completed,
    COUNT(rr.id) FILTER (WHERE rr.status = 'failed') AS failed,
    ROUND(AVG(EXTRACT(EPOCH FROM (rr.completed_at - rr.started_at))/60)) AS avg_minutes
FROM itops_runbook rb
LEFT JOIN itops_runbook_run rr ON rr.runbook_id = rb.id
GROUP BY rb.id, rb.slug, rb.title;

-- ============================================================
-- SEED: Core runbooks
-- ============================================================
INSERT INTO itops_runbook (slug, title, trigger_keywords, steps_json, priority, estimated_minutes, rdti_eligible)
VALUES
(
    'site-down-triage',
    'Site Down — Triage and Recovery',
    'site,down,404,502,503,deployment,vercel',
    '[
        {"action":"sql","params":{"query":"SELECT site_url, status FROM infra_sites_registry WHERE status != ''READY'' ORDER BY updated_at DESC LIMIT 10"}},
        {"action":"claude_diagnose","params":{"prompt":"Site is reporting as down. Check recent deployments and DNS. What are the likely causes and immediate remediation steps?"}},
        {"action":"notify","params":{"message":"Site-down triage initiated. Checking Vercel deployments and DNS."}},
        {"action":"check_health","params":{"biz_key":"t4h"}}
    ]'::jsonb,
    10, 20, false
),
(
    'database-error-triage',
    'Database Error — Connection and Query Triage',
    'database,supabase,connection,timeout,query,sql',
    '[
        {"action":"sql","params":{"query":"SELECT COUNT(*) as active FROM pg_stat_activity WHERE state = ''active''"}},
        {"action":"sql","params":{"query":"SELECT query, state, wait_event_type FROM pg_stat_activity WHERE state != ''idle'' LIMIT 10"}},
        {"action":"claude_diagnose","params":{"prompt":"Supabase is experiencing database errors. Connection count and active queries are elevated. What are the remediation steps?"}},
        {"action":"notify","params":{"message":"DB triage complete. Check pg_stat_activity output."}}
    ]'::jsonb,
    20, 15, false
),
(
    'payment-failure-triage',
    'Payment/Stripe Failure — Triage and Recovery',
    'payment,stripe,billing,webhook,checkout',
    '[
        {"action":"sql","params":{"query":"SELECT event_type, COUNT(*) FROM stripe_webhook_events WHERE created_at > NOW() - INTERVAL ''1 hour'' GROUP BY event_type"}},
        {"action":"claude_diagnose","params":{"prompt":"Stripe payment failures detected. Review webhook events and checkout flow. What are the likely causes?"}},
        {"action":"notify","params":{"message":"Payment triage initiated. Reviewing Stripe webhook log."}}
    ]'::jsonb,
    15, 20, false
),
(
    'lambda-error-triage',
    'Lambda Error — Worker Failure Triage',
    'lambda,worker,autonomy,bridge,timeout,error',
    '[
        {"action":"sql","params":{"query":"SELECT action, target, result FROM hitl_log WHERE created_at > NOW() - INTERVAL ''2 hours'' AND result ILIKE ''%error%'' ORDER BY created_at DESC LIMIT 20"}},
        {"action":"sql","params":{"query":"SELECT fn_name, status, COUNT(*) FROM mcp_lambda_registry GROUP BY fn_name, status"}},
        {"action":"claude_diagnose","params":{"prompt":"Lambda worker errors detected. Review HITL log and Lambda registry. What workers are failing and why?"}},
        {"action":"notify","params":{"message":"Lambda triage complete. Check hitl_log for error patterns."}}
    ]'::jsonb,
    25, 15, false
),
(
    'rdti-evidence-gap',
    'RDTI Evidence Gap — Research Documentation Triage',
    'rdti,evidence,research,documentation,deadline',
    '[
        {"action":"sql","params":{"query":"SELECT item_ref, status, note FROM rdti_evidence_register WHERE status != ''LOCATED'' ORDER BY item_ref"}},
        {"action":"sql","params":{"query":"SELECT COUNT(*) as total, COUNT(*) FILTER (WHERE is_rd) as rd_flagged FROM maat_timesheets WHERE EXTRACT(year FROM work_date) = 2025"}},
        {"action":"claude_diagnose","params":{"prompt":"RDTI evidence gaps exist before 30 April deadline. What are the critical missing items and how to resolve them quickly?"}},
        {"action":"notify","params":{"message":"RDTI evidence triage complete. Check rdti_evidence_register for ACTION_REQUIRED items."}}
    ]'::jsonb,
    5, 30, true
)
ON CONFLICT (slug) DO NOTHING;

-- ============================================================
-- COMMAND CENTRE QUERIES registration
-- ============================================================
INSERT INTO command_centre_queries (page_key, query_key, label, sql_text, display_type, sort_order)
VALUES
(
    'itops',
    'itops_incident_dashboard',
    'Open Incidents',
    'SELECT id, title, severity, status, routed_to, biz_key, ROUND(age_hours::numeric,1) AS age_h FROM v_itops_incident_dashboard LIMIT 25',
    'table', 10
),
(
    'itops',
    'itops_health_trend',
    'Health Trend 24h',
    'SELECT * FROM v_itops_health_trend_24h ORDER BY biz_key',
    'table', 20
),
(
    'itops',
    'itops_runbook_stats',
    'Runbook Effectiveness',
    'SELECT * FROM v_itops_runbook_stats ORDER BY total_runs DESC',
    'table', 30
),
(
    'itops',
    'itops_open_alerts',
    'Open Alerts',
    'SELECT title, severity, source, biz_key, created_at FROM itops_alert WHERE status = ''open'' ORDER BY CASE severity WHEN ''critical'' THEN 1 WHEN ''high'' THEN 2 ELSE 3 END, created_at',
    'table', 40
),
(
    'itops',
    'itops_incident_by_domain',
    'Incidents by Domain',
    'SELECT routed_to, COUNT(*) as total, COUNT(*) FILTER (WHERE status = ''open'') as open FROM itops_incident GROUP BY routed_to ORDER BY total DESC',
    'table', 50
)
ON CONFLICT (page_key, query_key) DO NOTHING;
