# Joshua-HQ — Implementation Plan

Phase-by-phase implementation notes behind the built system. The top-level
`Makefile` and parts of `proto/` and the API reference sections of this file.
Design intent is in `ARCHITECTURE.md`; the roadmap and decisions are in
`PLAN.md`.

## §0. Overview

Joshua-HQ is a FastAPI + Postgres + Vue cloud fleet-management app plus a gRPC
agent-gateway. This plan walks the infrastructure, protocol, data paths, and
fleet-operation verbs as they were built. The validation gate
(`.claude/validate.sh`) enforces the architectural boundary (§2.1/§7 of the
architecture) and a single alembic head.

## §1. Local infrastructure & auth

### §1.1 Services (`infra/docker-compose.yml`, `make db-up`)

| Service    | Port(s) | Purpose                                   |
|------------|---------|-------------------------------------------|
| postgres   | 5432    | primary store (`joshuahq`, `joshuahq_test`) |
| minio      | 9000/9001 | S3-compatible object storage (`joshuahq` bucket) |
| redis      | 6379    | arq background jobs + presence broadcast  |
| keycloak   | 8081    | dev OIDC IdP (realm `joshuahq`)           |

### §1.2 OIDC for humans — the "day-1 default"

Human auth is OIDC. **The day-1 default is a self-hosted Keycloak realm imported
from `infra/keycloak/realm-joshuahq.json`** (dev-only: `sslRequired none`,
`KC_HOSTNAME_STRICT off`). This keeps Phase-1 auth unblocked on a vendor IdP
decision; production should substitute a real IdP.

- Flow: `GET /auth/login` → Keycloak → `POST /auth/callback` → the API issues its
  own **HS256 session JWT** (`JOSHUAHQ_SESSION_SECRET_KEY`) in an httpOnly cookie.
  All `require_role(...)` routers gate on it.
- **Single shared deployment.** The same Keycloak realm also fronts the web app;
  `make seed EMAIL=admin@example.com` pre-invites the seeded admin email in the
  app's Postgres, which is what `app/routers/auth.py` first-login matching needs
  to link the IdP subject to the app user (`User.auth_subject_id`).
- Keycloak's data volume persists its embedded H2 DB so user subject IDs stay
  stable across container recreation.

### §1.3 `make seed` / `make run`

`make seed EMAIL=...` invites an admin; `make run` starts API (8000),
agent-gateway (50051), and Vite web (5173).

## §2. Protocol

### §2.1 The device agent protocol is `joshuahq.agent`

`proto/joshuahq/agent.proto` (proto3) defines its own package
`joshuahq.agent`, generated into `agent-gateway/joshuahq/` as
`agent_pb2.py`/`agent_pb2_grpc.py`/`agent_pb2.pyi`. It is deliberately **not**
shared with `joshua.stream` / `hal.common` (ARCHITECTURE.md §7). The lone RPC is
`AgentLink.Connect(stream AgentFrame) returns (stream ServerFrame)` — one
persistent device session.

Regenerate after editing the proto:

```
.venv/bin/python -m grpc_tools.protoc \
  -I proto --python_out=agent-gateway --grpc_python_out=agent-gateway \
  proto/joshuahq/agent.proto
```

(Do not hand-edit the generated `agent_pb2*.py*`; they are excluded from lint.)

## §3. Telemetry, faults, alarms

### §3.1 Telemetry ingest
Devices stream `TelemetryBatch` samples to the gateway; the API exposes
`POST /devices/{id}/telemetry` (operator), `GET /devices/{id}/telemetry`
(grouped series), `GET /devices/{id}/telemetry/{sample_id}` — backed by the
`telemetry_sample` table. The table name stays `telemetry_sample`.

### §3.2 Faults
The raw fault feed lives in the `fault` table; `GET /devices/{id}/faults`
returns it newest-first.

### §3.3 Fault → alarm is explicit (rule-based alarms)
A fault existing does **not** automatically raise an alarm. `AlarmRule`
(`alarm_rule` table) maps faults/telemetry thresholds to rule-based `Alarm` rows
(`alarm` table). The mapping is explicit because only operator-approved rules
should page anyone.

### §3.4 Device-reported alarms & large payloads
R3 added a separate `alarms` table (`DeviceAlarm`, migration `c1a2b3c4d5e6`)
for device-reported **4-byte alarm codes** (`0x01020304` → major/sub/type/severity,
big-endian), distinct from the rule-based `alarm` table.

**Large payloads stay off the gRPC stream.** A device that wants to upload a log
bundle or backup sends a `LogUploadRequest`; the gateway answers with a
`SignedUploadUrl` (a presigned S3 URL). The device then uploads directly to
object storage, and HQ records the object in `log_bundle` / `backup`. This keeps
multi-MB transfers off the stream and the stream itself fast and simple.

## §4. Fleet operations

### §4.1 Command queue (`pending_command`)
`POST`-triggered verbs (backup take-now, restore, factory reset, apply update)
are queued as `PendingCommand` rows (Phase 4 migration `a40971629062`) so the
gateway can deliver them durably to the target device and the API can report
state even if the device is briefly offline.

### §4.2 Pushed commands & the device-side pairing section

`Command` is the server→device verb in `joshuahq.agent` (oneof: take_backup_now,
restore, factory_reset, apply_update). The gateway delivers queued commands to a
connected device and the device replies with a `CommandAck`.

**Device-side work is coordinated from here but lives in Joshua-Configuration.**
The on-device HQ pairing section — the WebConfig daemon section storing the HQ
address + pairing config and the token, plus the **outbound agent** that dials
`AgentLink.Connect` — belongs to Joshua-Configuration (it owns the RAUC update
path and already aggregates status/logs). HQ owns: the pairing-token issuance
endpoint, the credential model, the gateway's pairing/command protocol, and the
operator UI. The HQ-side scope/contract for that work is
`docs/device-side-hq-scope.md`. OTA artifact storage is new infra HQ owns; the
device's existing `UpdateBackend`/RAUC flow will point at HQ's artifact-repo URL.

## §5. Migrations & the gate

- Alembic migrations live in `migrations/versions/`; the **single head** rule is
  enforced by `./.claude/validate.sh` — add a migration with `down_revision` =
  the current head, never create a fork.
- Head chain: `2e3ef54fdbe4 → a40971629062 → c1a2b3c4d5e6 → d6f0e1a2b3c4`.
- The gate also blocks on-device proto leakage and Joshua-HAL build coupling
  (ARCHITECTURE.md §7).
