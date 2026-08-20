# Joshua-HQ

Cloud fleet-management app for Joshua devices — view devices remotely, manage
pairing/authorization, and run fleet operations (telemetry, faults/alarms,
logs, OTA updates, backup/restore, provisioning, factory reset, disable,
location).

Status: **implemented**. See [PLAN.md](PLAN.md), [ARCHITECTURE.md](ARCHITECTURE.md)
and [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

Quick start: `make install && make db-up && make migrate && make seed EMAIL=... && make run`
