# Joshua-HQ — Plan

Roadmap, phases, and decision log for the Joshua-HQ cloud fleet-management app.

**Status: implemented.** The service is feature-complete for the phase set below
(see `CHANGELOG.md`). This document records how it got here and what is still
open. Design detail is in `ARCHITECTURE.md`; per-phase implementation notes are
in `IMPLEMENTATION_PLAN.md`.

---

## 1. Vision

Give an operator a single cloud pane for every paired Joshua device: watch it
remotely (presence, telemetry, location), diagnose it (faults, alarms, logs),
and act on it (provision, update, back up/restore, factory reset, disable).

## 2. Guiding decisions

| Decision | Rationale |
|---|---|
| Cloud-hosted, the only hosted leaf | HQ owns the fleet pane; devices dial out so no inbound port is required |
| Own device protocol (`joshuahq.agent`), pairing-token auth | independent wire contract, no coupling to on-device HAL (ARCHITECTURE.md §7) |
| Persistent dial-out connection, presence = liveness | mirrors Client-to-Server shape; no NAT/broadcast gymnastics |
| OIDC for humans + API-signed session cookie | standard IdP delegation, then a stable httpOnly session |
| S3 + presigned URLs for large payloads | keep multi-MB bundles/artifacts off the gRPC stream |
| Redis/arq for background work + presence broadcast | simple, testable |

## 3. Roadmap / phases

1. **Phase 1 — tenants, users, devices, foundations** (`2e3ef54fdbe4`)
   Multi-tenant device/user model, device credential lifecycle, telemetry
   ingest, faults, rule-based alarms, audit log, OIDC auth + RBAC, OTA
   artifact/rollout tables, backup/log-bundle tables, object storage.
2. **Phase 4 — command queue** (`a40971629062`) — `pending_command` table so the
   gateway can deliver server->device verbs durably.
3. **R3 — device-reported alarms** (`c1a2b3c4d5e6`) — new `alarms` table and the
   4-byte alarm-code decode path; distinct from the rule-based `alarm` table.
4. **Location** (`d6f0e1a2b3c4`) — `device_location` table, latest/history/ingest.
5. **Feature-complete pass** (`9496a1e`) — wired the previously-unregistered
   routers and filled the remaining fleet-operation gaps: backups, disable,
   factory-reset, bulk provisioning, OTA artifact/rollout/start, location, and
   restored the rule-based `rule-alarms` list (this work). Validation is green
   (api + gateway + web).

## 4. Known open items

- **Rule-alarm list restore** — implemented here as `GET /devices/{id}/rule-alarms`
  plus the UI panel section (Acknowledge/Resolve). Confirmed closed.
- **Device-side pairing section** — the on-device HQ agent (address config, token
  storage, outbound agent) belongs in **Joshua-Configuration**, coordinated from
  here. The HQ-side scope/contract is `docs/device-side-hq-scope.md`; the
  implementation is tracked in Joshua-Configuration's own plan.
- **Real IdP** — local dev uses self-hosted Keycloak; production should select a
  vendor OIDC IdP (`IMPLEMENTATION_PLAN.md` §1.2).
- **Real deployments** — S3 bucket policy/quotas, gateway scaling, and key rotation
  are outside the local dev stack.

## 5. Rollout & tenant scope

All device and user access is tenant-scoped; cross-tenant device access returns
404 (no existence leak). Users are `viewer`/`operator`/`admin`.

## 6. Maintenance

- **Single alembic head** is enforced by the gate — never add a second head.
- Device-side work is coordinated from HQ but implemented in Joshua-Configuration;
  HQ does not link HAL and does not reuse on-device protos (ARCHITECTURE.md §7).
- All three suites (api, gateway, web) must pass before a loop closes.

## 7. Device-side work (scoped from HQ)

The HQ pairing section on the device — the on-device WebConfig daemon section
that stores HQ address/pairing config and the token, plus the outbound agent —
belongs in **Joshua-Configuration** (see `IMPLEMENTATION_PLAN.md` §4.2). HQ owns:
the pairing-token issuance endpoint, the credential model, the gateway's pairing
protocol, and the operator UI. The device-side consumer is the co-owned scope.
