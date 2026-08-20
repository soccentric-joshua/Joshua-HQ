# Changelog

Maintained by the Loop Engine. One entry per loop that touched this repo,
newest first, appended on loop close (pass or fail) and committed on the loop's
own feature branch. See the master repo's `Joshua-Loop-Orchestration-Spec-v2.md` §11.1.

Entries written by hand are fine; the engine inserts directly under this header.

## 2026-08-19 — [sync-feature-complete] Close the fleet-operation gaps to feature-complete
- Backend: mounted the previously-implemented-but-unregistered `backups` router (backup/restore was reachable in the UI but 404'd on the API).
- Backend: added `POST /devices/{device_id}/disable` (flips pairing_state to `disabled`, drops `online`) and `POST /devices/{device_id}/factory-reset` (queues a `factory_reset` PendingCommand) — both were already wired in the web UI but unimplemented server-side.
- Backend: added `POST /devices/bulk` bulk provisioning (per-device unique pairing tokens), completing the `BulkProvision*` schemas that were previously schema-only.
- Backend: added the OTA-update surface (`api/app/routers/update.py`) on the pre-existing `update_artifact`/`update_rollout`/`update_rollout_device` tables: artifact CRUD, rollout create (enrolls target set), rollout detail with per-device status, rollout start (enqueues `apply_update` PendingCommands), and device-scoped `GET /devices/{id}/updates`.
- Backend: added location tracking — new `device_location` table (migration `d6f0e1a2b3c4`, single head), `GET /devices/{id}/location` (latest), `GET /devices/{id}/location/history`, `POST /devices/{id}/location` (ingest, device timestamp kept verbatim).
- Web: new `UpdatePanel.vue` (device update history + artifact registration + rollout create/start) and `LocationPanel.vue` (latest fix + history + map link); wired into `DeviceDetailView` as Location and Updates tabs; added matching `api.ts`/`types.ts` surface.
- Tests: added `api/tests/test_ops_features.py` covering disable (incl. RBAC), factory-reset queue, bulk provision, location ingest/latest/history, the artifact→rollout→start flow, and the backups-registration regression.
- Verified: api lint + 45 api tests pass, web type-check/lint/tests pass, alembic single head `d6f0e1a2b3c4` applies cleanly.

## 2026-07-30 — [20260730-app-telemetry-daemon] Telemetry daemon streams configurable key-value metrics and Joshua-HQ can ingest a sample
- Status: SUCCESS (try 1 of 4)- Verdict: auditor: UPHOLD; orchestrator: ACCEPT-WITH-FINDINGS
