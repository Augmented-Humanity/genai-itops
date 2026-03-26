---
name: t4h-bridge
description: T4H autonomous execution bridge skill. Use when executing SQL, invoking Lambda functions, deploying infrastructure, or interacting with the T4H stack (Supabase, AWS, Vercel, GitHub). Triggers on: "run SQL", "invoke lambda", "bridge call", "execute against Supabase", "T4H bridge", "exec_sql", "push to GitHub", "deploy CFN".
---

# T4H Bridge

Single execution engine for the T4H 28-business autonomous stack.

## Bridge Endpoint
```
POST https://m5oqj21chd.execute-api.ap-southeast-2.amazonaws.com/lambda/invoke
x-api-key: <from cap_secrets.T4H_BRIDGE_API_KEY>
Content-Type: application/json
```

## SQL Execution (troy-sql-executor)
```json
{"fn": "troy-sql-executor", "route": "sql", "sql": "SELECT ..."}
```
- No trailing semicolons (silent rows:[])
- DDL-safe: CREATE/DROP/ALTER all work
- Supabase pooler handles Lambda connections

## Lambda Invocation
```json
{"fn": "<lambda-name>", "action": "...", ...params}
```

## Active Lambda Registry (mcp_lambda_registry)
Query: `SELECT fn_name, description, status FROM mcp_lambda_registry WHERE status = 'ACTIVE'`

Key lambdas:
- `troy-sql-executor` — SQL on Supabase S1 (lzfgigiyqpuuxslsygjt)
- `troy-sql-executor-s2` — SQL on Supabase S2 (pflisxkcxbzboxwidywf)
- `genai-itops` — ITOps incident/runbook/health
- `autonomy-controller` — T4H autonomous OS
- `troy-ses-sender` — Email via AWS SES
- `troy-s3-manager` — S3 file operations
- `troy-stripe-executor` — Stripe operations
- `troy-cfn-deployer` — CloudFormation stacks
- `troy-code-pusher` — GitHub deploys

## Fallback: Supabase REST
```
POST https://lzfgigiyqpuuxslsygjt.supabase.co/rest/v1/rpc/exec_sql
Authorization: Bearer <service_key>
{"query": "SELECT ..."}
```

## Autonomy Tiers
- **AUTONOMOUS**: SELECT, views, functions, cap_secrets reads, schema inspection
- **LOG-ONLY**: INSERTs/UPDATEs to ops tables, env updates, email sends
- **GATED**: DELETE/DROP, RLS changes, code deploys, CFN — dry-run first
- **BLOCKED**: Payment flows, IAM, DNS, cred rotation — always confirm

## HITL Logging
All LOG-ONLY and GATED actions log to `hitl_log`:
```
[LOG] action|target|result|utc
```
Manual query: `SELECT * FROM hitl_log ORDER BY created_at DESC LIMIT 20`

## Examples

```
"Run SELECT COUNT(*) FROM itops_incident WHERE status = 'open'"
→ {"fn":"troy-sql-executor","route":"sql","sql":"SELECT COUNT(*) FROM itops_incident WHERE status = 'open'"}

"Send an email to Troy"
→ {"fn":"troy-ses-sender","to":"troy@tech4humanity.com.au","subject":"...","body":"..."}

"Deploy a CFN stack"
→ {"fn":"troy-cfn-deployer","action":"deploy","stack_name":"...","template_body":"..."}
```
