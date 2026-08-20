# Device-side HQ pairing — scope (coordinated from HQ)

The device side of the Joshua-HQ link is implemented in **Joshua-Configuration**
(SoCcentric WebConfig, a Rust daemon), coordinated from this repo. This document
is the HQ-side scope for that work. It is the contract the gateway/API
implement against; it does **not** add code to Joshua-Configuration here.

Design context: `ARCHITECTURE.md` §3 (device link & presence), §6 (fleet
operations), `IMPLEMENTATION_PLAN.md` §4.2. The wire contract is
`proto/joshuahq/agent.proto` (package `joshuahq.agent`).

---

## 1. Objective

Let a WebConfig device dial into HQ, get paired/authorized, hold a persistent
link, and service fleet operations — with zero inbound ports and no coupling to
Joshua-HAL wire contracts.

## 2. In scope — device-side components (in Joshua-Configuration)

### 2.1 HQ pairing section in WebConfig (a new `§4.x` section, or under Security)
A browser-configurable section, schema-driven like the other 9 WebConfig
sections (`schemas/*.schema.json`, rendered by the vanilla-JS frontend):

- **HQ address**: host:port / URL of the agent-gateway (TLS), plus optional
  OIDC-independent client cert/identity if the network requires it.
- **Pairing state & token**: field to paste/auto-accept a one-time pairing token
  from HQ (`POST /devices/{id}/...` operator surface), and the resulting
  long-lived `credential_token` + `device_id` stored securely (WebConfig's ring
  JSON files / TPM trust panel, not plaintext where possible).
- **Status**: paired/authorized/disabled/revoked, last heartbeat, link health.
- **Re-pair / rotate**: trigger a credential rotate against
  `POST /devices/{id}/credential/rotate` and revoke on
  `POST /devices/{id}/credential/revoke`.

### 2.2 Outbound agent (Rust, in `crates/`)

A component (e.g. `crates/hq-agent`) that:

- **Dials out**: opens `AgentLink.Connect` (a persistent, bidirectional gRPC
  stream) to the configured gateway. Reconnects with backoff; no inbound port.
- **Handshake**: on first connection sends `PairingHandshake` with the single-use
  pairing token; on success stores the `credential_token` from `PairingResult`.
  Subsequent connections send `Heartbeat` frames (device_id + credential_token).
- **Presence**: honors `HeartbeatAck.server_time_unix_ms` and
  `next_heartbeat_interval_s`; presence on HQ's side derives from this stream
  (ARCHITECTURE.md §3).
- **Streams state**: `TelemetryBatch` (metrics + optional `Location`), `FaultEvent`
  (raised/cleared), and device-reported 4-byte `alarm_code` (via the API ingest,
  matching the `alarms` table decode — see `api/app/routers/alarms.py`).
- **Uploads large payloads off-stream**: on `LogUploadRequest`/`SignedUploadUrl`
  answers, uploads log bundles / backups directly to the presigned S3 URL.
- **Executes pushed commands** (`Command` oneof) and replies `CommandAck`:
  - `take_backup_now` → WebConfig backup path.
  - `restore` → restore from `backup_download_url`.
  - `factory_reset` → full factory reset (which also wipes the audit log, per
    WebConfig spec §4.6).
  - `apply_update` → RAUC update from `artifact_download_url` with
    `checksum_sha256` verification.

### 2.3 OTA artifact repo points at HQ

WebConfig's existing `UpdateBackend`/RAUC flow (spec §4.4) keeps its artifact
URL source configurable and points at HQ's artifact-repo URL so rollouts created
in HQ (`update-artifacts` / `update-rollouts`) are consumable on-device.

## 3. Out of scope for the device side

- Anything that would link Joshua-HAL or reuse `hal_service.proto` /
  `client_service.proto` / `joshua.stream` (ARCHITECTURE.md §7).
- HQ's own server code (API routers, gateway, UI) — already implemented here.
- Vendor-IdP decisions; the device↔HQ link uses HQ's pairing/credential tokens,
  not the human OIDC session.

## 4. API / protocol contract the device-side consumes

| Purpose | Surface |
|---|---|
| Pairing token issuance | HQ operator flow → device receives a token out-of-band |
| Credential rotate/revoke | `POST /devices/{id}/credential/rotate`, `/revoke` |
| Fleet verbs | `pending_command` queue delivered as `Command` frames |
| Telemetry ingest | `TelemetryBatch` → `POST /devices/{id}/telemetry` |
| Location ingest | `Location` → `POST /devices/{id}/location` |
| Device alarms | 4-byte `alarm_code` → `POST /devices/{id}/alarms` |
| Log bundle upload | `LogUploadRequest` → `SignedUploadUrl` → S3 |
| OTA artifacts | HQ `update-artifacts` URL consumed by RAUC path |

## 5. Acceptance criteria (device side)

1. A device pastes a pairing token → dials out → is `authorized` in HQ and
   appears `online`; credential rotates cleanly.
2. Heartbeat stops → HQ flips the device `offline` within the missed-threshold
   window (gateway stale sweep).
3. Each pushed command is acked and its effect visible in the HQ detail view
   (backup row, rollout status, factory-reset audit).
4. A log bundle / backup uploads via the presigned URL without riding the gRPC
   stream.
5. The HQ validation gate in this repo stays green; the WebConfig gate
   (`make build && make test && make lint`) stays green.

## 6. Coordination notes

- HQ owns: pairing-token endpoints, credential model, gateway pairing/command
  protocol, operator UI, OTA artifact repo. Joshua-Configuration owns: the
  on-device agent, the pairing section, token storage, and RAUC/update wiring.
- Do not add a second alembic head in HQ; the device side never touches HQ's
  migrations.
