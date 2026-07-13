# AimiliVPN Backend API v1

This document freezes the backend contract used by the Web UI and Console. All
paths below are relative to the instance's protected Web path. JSON is UTF-8 and
responses use `Cache-Control: no-store`.

## Authentication and authorization

All `/api/*` reads and mutations require either a valid `session` cookie or the
trusted local Console token. `POST /api/login` is the only unauthenticated API
mutation. Login, logout, configuration updates, region mutations, quality
checks, connection actions, and proxy checks are audited without request body,
credential, or secret-path values.

Every mutation validates `Content-Length` before routing and rejects bodies over
256 KiB with HTTP 413 and `error_code=request_too_large`. Individual endpoints
may enforce a smaller limit.

## Common response and error model

Successful resource responses contain `ok: true` where noted. Stable errors use:

```json
{
  "ok": false,
  "error": "safe user-facing message",
  "error_code": "stable_machine_identifier"
}
```

Internal exception messages are never returned. HTTP status retains its normal
meaning: 400 invalid input, 401 authentication required, 404 missing resource,
409 operation conflict, 413 body too large, and 500/502 server or provider
failure.

## List parameters

The nodes, regions, quality-results, logs, and operations collections share:

- `limit`: integer from 1 through 500;
- `offset`: non-negative integer;
- `sort`: endpoint-specific documented field;
- `order`: `asc` or `desc`.

Unknown, repeated, malformed, or unbounded parameters return
`error_code=invalid_query`. Collection responses include:

```json
{"pagination":{"limit":100,"offset":0,"returned":100,"total":240}}
```

## Resources

### Contract discovery

`GET /api/v1` returns the version, resource paths, pagination bounds,
idempotency header, and common error fields.

### Status

`GET /api/v1/status` returns `services[]`. Each service has `name`, `status`,
`details`, and `error`. Status is `running` or `stopped`. The legacy path is
`GET /api/gateway_status`.

### Nodes

`GET /api/v1/nodes` returns `nodes[]`, `state`, and `pagination`. Filters are
`region`, `country`, `status`, and `ip_type`; sort fields are `id`, `country`,
`latency`, `quality`, and `score`. Node fields used by clients are `id`,
`country`, `country_short`, `ip`, `remote_host`, `remote_port`, `proto`,
`latency_ms`, `probe_status`, `probe_message`, `ip_type`, `quality`,
`quality_score`, `quality_label`, `quality_reasons`, `active`, and `fetched_at`.
`config_text` is never public. The legacy path is `GET /api/nodes`.

### Regions

`GET /api/v1/regions` returns `regions[]` and `pagination`; it accepts the
`enabled` filter and `id`/`name` sorting. `GET /api/v1/regions/{id}` returns one
region. Region fields are `id`, `name`, `country_codes`, `include_keywords`,
`exclude_keywords`, `min_quality_score`, `max_risk_score`, and `enabled`.

`POST /api/v1/regions`, `PUT /api/v1/regions/{id}`, and
`DELETE /api/v1/regions/{id}` create, replace, and delete. Preview uses
`POST /api/v1/regions/{id}/preview` and returns match totals, IDs, and exclusion
reason counts. Equivalent `/api/regions...` paths remain compatible.

### Quality

`GET /api/v1/quality-results` returns normalized `qualities[]` and pagination.
Filters are `node_id`, `provider`, and `label`; sort fields are `checked_at`,
`score`, `risk_score`, and `node_id`. Public fields are `node_id`, `exit_ip`,
probe timings/status, normalized risk fields, `checked_at`, `score`, `label`,
and `reasons`. Provider raw responses are never public.

`GET /api/v1/quality-providers` reports local and optional provider capability.
Checks use `POST /api/v1/quality-checks/nodes`, `/node`, `/ip`, or `/region`.
Legacy `/api/quality...`, `/api/test_node`, and `/api/test_nodes` paths remain.

### Settings

`GET /api/v1/settings` returns only non-secret routing and port settings.
`PUT /api/v1/settings`, `/routing`, and `/credentials` update their respective
resource. Password hashes, provider keys, proxy credentials, and secret values
are never returned. Legacy `/api/update_settings`, `/api/update_routing`, and
`/api/update_credentials` paths remain.

### Logs

`GET /api/v1/logs` returns `logs[]` and pagination. Filters are `level` and
`module`; sort fields are `timestamp`, `level`, and `module`. The default limit
is 200 and the maximum is 500. Messages pass server-side redaction. The legacy
path is `GET /api/logs`.

### Operations and service actions

Refresh, detection, connect, and disconnect are asynchronous in the production
runtime:

- `POST /api/v1/operations/refresh-nodes`
- `POST /api/v1/operations/check-nodes`
- `POST /api/v1/operations/connect` with `{ "id": "node-id" }`
- `POST /api/v1/operations/disconnect`

Quality checks also return operations when the runtime registry is available.
HTTP 202 contains `operation_id`, `operation`, and `deduplicated`. Operation
status is `queued`, `running`, `succeeded`, or `failed`; failures expose only a
stable `error_code`. Poll with `GET /api/v1/operations/{id}` or list with
`GET /api/v1/operations` using `status`/`kind` filters.

Clients should send an `X-Idempotency-Key` of at most 128 characters. Retrying
the same action with the same key returns the original operation, including
after completion. Without the header, identical in-flight actions are still
coalesced, but a later completed action may be submitted again. Thus retries
cannot create an unbounded set of concurrent jobs.

The registry retains at most 500 operations. If all slots are occupied by
active work, new operations receive HTTP 503 with
`error_code=operation_capacity` until capacity becomes available.

`POST /api/v1/proxy-checks` is explicitly synchronous and returns the current
normalized proxy check result. Instance lifecycle and systemd actions are
separate authenticated Console APIs documented in `docs/installation.md`; they
are not accepted through a single-instance backend.

## Compatibility and deprecation

Legacy endpoints remain supported throughout the v1 lifecycle. New clients
must use `/api/v1`. Legacy paths will first receive deprecation response headers
in a later release and will not be removed before a documented v2 migration
window. No current endpoint is removed by P5.
