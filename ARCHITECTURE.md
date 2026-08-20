# Joshua-HQ — Architecture

Cloud fleet-management service for paired Joshua devices. It is the only
cloud-hosted leaf of the Joshua fleet. It lets an operator see every paired
device's status remotely and run operations against it: telemetry, faults and
alarms, logs, OTA updates, backup/restore, provisioning, factory reset,
disable, and location tracking.

This document describes the system as built. See `PLAN.md` for the roadmap and
decision log, and `IMPLEMENTATION_PLAN.md` for the phasing detail behind the
sections referenced here.

---

## 1. Responsibilities

Joshua-HQ owns the **server side** of device fleet management:

- **Pairing & authorization** — issues single-use pairing tokens, redeems them
  for long-lived credentials, and revokes/rotates credentials.
- **Presence** — derives online/offline from the device's persistent
  connection and heartbeat freshness.
- **Fleet operations** — telemetry ingest, faults and alarms, log-bundle
  collection, OTA rollout, backup/restore, provisioning (individual and bulk),
  factory reset, disable, and location history.
- **Tenancy & RBAC** — every device and every user belongs to a tenant; every
  action is scoped to the caller's tenant and gated by role.

The **device side** of the HQ link (address/pairing configuration, token
storage, the outbound agent) lives in the separate `Joshua-Configuration` repo,
coordinated from here — see `PLAN.md` §7.

## 2. Components

| Component      | Tech                                             | Role                                              |
|----------------|--------------------------------------------------|---------------------------------------------------|
| `api/`         | FastAPI + SQLAlchemy async + Pydantic + Alembic  | HTTP API for the browser UI and operators         |
| `web/`         | Vue 3 + TypeScript + Vite                        | Browser dashboard (device list, detail, ops)      |
| `agent-gateway/` | gRPC (Python, generated from `proto/joshuahq/agent.proto`) | Device-facing endpoint (dial-out)            |
| `proto/`       | protobuf 3 (`joshuahq/agent`)                    | Independent wire contract between device & gateway |
| `infra/`       | docker compose                                   | Local Postgres, MinIO (S3), Redis, Keycloak       |

The device link models **Client-to-Server's shape** — the device dials out and
holds a persistent connection — but it is its **own protocol**, `joshuahq.agent`,
with its own pairing-token auth. It does **not** reuse `joshua.stream` or any
HAL protos (§7).

## 3. Device link & presence

The device connects to the agent-gateway over a single persistent, bidirectional
gRPC stream (`AgentLink.Connect`). One call == one device session.

- **First connection** — the device sends a `PairingHandshake` with a single-use
  pairing token. The gateway validates it, authorizes the device, and replies
  with a `PairingResult` carrying a long-lived `credential_token` plus the
  canonical `device_id`.
- **Subsequent connections** — the device sends `Heartbeat` frames carrying its
  `credential_token`. The gateway validates the long-lived credential and echoes
  `HeartbeatAck` with a server timestamp and the next interval.
- **Presence = liveness.** A device is `online` while its stream is open and its
  heartbeats arrive within `heartbeat_interval_s × heartbeat_missed_threshold`
  (`app/config.py`). A stale sweep (`gateway/stale_sweep.py`) flips devices that
  miss their window to `offline`.

Frames are a `oneof` over a single `AgentFrame`/`ServerFrame`: pairing, heartbeat,
telemetry batch (+ optional location), fault event, log-upload request, command
ack, command push, signed upload URL.

## 4. Data model

Alembic migrations (`migrations/versions/`, single head enforced by the gate):

- **Phase 1** (`2e3ef54fdbe4`): `tenant`, `user`, `device`, `device_credential`,
  `telemetry_sample`, `fault`, `alarm_rule`, `alarm`, `backup`, `log_bundle`,
  `audit_log`, `update_artifact`, `update_rollout`, `update_rollout_device`.
- **Phase 4** (`a40971629062`): `pending_command` — server->device verb queue.
- **R3 device alarms** (`c1a2b3c4d5e6`): `alarms` — device-reported 4-byte alarm
  code table (distinct from the rule-based `alarm` table).
- **Location** (`d6f0e1a2b3c4`): `device_location`.

Key models (`api/app/models/`):

- `Tenant` — tenancy root. `User` (`viewer`/`operator`/`admin`), `audit_log`.
- `Device` — fleet device; `pairing_state` in `pending|authorized|disabled|revoked`;
  `DeviceCredential` — pairing vs long-lived tokens.
- `TelemetrySample`, `Fault`, `DeviceAlarm`, `DeviceLocation` — device-reported state.
- `AlarmRule` / `Alarm` — operator-configured rules that turn faults into alarms.
- `UpdateArtifact`, `UpdateRollout`, `UpdateRolloutDevice` — OTA rollout.
- `Backup`, `LogBundle` — large payload metadata (blobs in S3).
- `PendingCommand` — queued fleet verb (`take_backup_now`, `restore`,
  `factory_reset`, `apply_update`) for the gateway to deliver.

## 5. Auth & authorization

Two distinct trust domains:

- **Human operators (the web UI)** authenticate via OIDC (Keycloak in local dev,
  §1.2 of the implementation plan). The API exchanges the authorization code for
  an **API-signed session JWT** held in an httpOnly cookie. Every router dependency
  (`require_role(viewer|operator|admin)`) gates both auth and role.
- **Devices** authenticate to the agent-gateway with pairing/credential tokens —
  not the human OIDC session. Devices are paired under a tenant and scoped to it.

Tenant scoping is enforced on every read/write path (e.g. `get_tenant_device_or_404`
returns 404 — not 403 — for another tenant's device to avoid leaking existence).

## 6. Fleet operations (API surface)

Device-scoped routes (`/devices/{device_id}/...`):

- `telemetry` — GET series, GET one, POST ingest.
- `faults` — GET list (raw feed).
- `alarms` — device-reported 4-byte alarms (GET, POST ingest, `/{id}/clear`).
- `rule-alarms` — rule-based `Alarm` rows (GET list) — the restore of the
  list that was lost when `/devices/{id}/alarms` was repointed to the new table.
- `location` — GET latest, GET history, POST ingest.
- `logs` — GET bundles, GET signed download URL.
- `backups` — GET, POST take-now, POST restore.
- `update-artifacts`, `update-rollouts` — OTA artifact CRUD, rollout create/detail/start.
- `devices` — list/create, `bulk` provisioning, `credential/rotate`, `credential/revoke`,
  `disable`, `factory-reset`.
- `/alarms/{id}/acknowledge`, `/alarms/{id}/resolve` — rule-based alarm lifecycle.

Large payloads (log bundles, backups, OTA artifacts) are never sent over the gRPC
stream: the gateway issues a **presigned S3 URL** and the device uploads/restores
directly from object storage.

## 7. What HQ deliberately does not do

This is the architectural boundary the validation gate enforces:

- **No on-device wire contracts.** HQ does not link Joshua-HAL and does not reuse
  `hal_service.proto` / `client_service.proto` / `joshua.stream`. Its only
  integration point with a device is the pairing link to Joshua-Configuration.
- **No build coupling.** No `add_subdirectory`, no proto reuse, not in the
  on-device image.
- The resemblance between the agent protocol and Client/Server's proto sharing is
  a coincidence of shape, **not** a dependency.

Drift here is the kind that looks like convenient reuse right up until HQ is coupled
to the on-device wire contract and can't be deployed independently.

## 8. Object storage & background work

- **S3-compatible object storage** (MinIO in dev, `joshuahq` bucket) holds OTA
  artifacts, log bundles, and backups. Signed URLs hand off payloads to/from devices.
- **Redis** backs `arq` background jobs and presence/pub-sub state (device status
  broadcast over the web socket `ws.py`).

## 9. Local development & deployment

`infra/docker-compose.yml` brings up Postgres 16, MinIO, Redis, and a dev
Keycloak realm. `make db-up && make migrate && make seed EMAIL=... && make run`
starts the API (8000), agent-gateway (50051), and Vite web (5173). See
`IMPLEMENTATION_PLAN.md` §1 for the single shared dev deployment model.
