# Joshua-HQ

## Project Summary

Joshua-HQ is the cloud fleet-management service for Joshua devices. The repository contains a Python
API, an agent gateway, database models and migrations, and web-facing configuration for operating a
fleet remotely. Its documented scope includes device inventory, pairing and authorization,
telemetry, faults and alarms, log bundles, OTA updates, backup and restore, provisioning, factory
reset, disable, and location. The API test tree covers alarms, devices, OIDC, pairing tokens,
phase-three flows, RBAC, telemetry, and tenant isolation; the gateway test tree covers frames,
pairing, and stale-peer cleanup.

The `api/app/auth` and middleware packages establish authentication, sessions, OIDC, and request
context, while `api/app/models` defines devices, alarms, faults, credentials, backups, pending
commands, and audit logs. The separate `agent-gateway` package handles the device-facing message
boundary and pairing lifecycle. Database configuration, migrations, and development commands are
wired through the Makefile and documented quick start: install dependencies, start the database,
migrate, seed an account, and run the services. The code and tests support implemented status for
the major product surface, but deployment, external identity-provider behavior, real device
connectivity, and long-running OTA or backup operations require environment-specific validation.

## Feature Inventory

| # | Name / Description | Implemented? | Test Coverage? | Manual Test |
| --- | --- | --- | --- | --- |
|   1 | Python API service and configuration         | Implemented  | Partial API suite                          | [ ] Manual verification required |
|   2 | Device inventory and routes                  | Implemented  | `api/tests/test_devices.py`                | [ ] Manual verification required |
|   3 | Sessions and OIDC                            | Implemented  | `api/tests/test_oidc.py`                   | [ ] Manual verification required |
|   4 | RBAC and tenant isolation                    | Implemented  | `test_rbac.py`, `test_tenant_isolation.py` | [ ] Manual verification required |
|   5 | Pairing and authorization tokens             | Implemented  | API and gateway pairing tests              | [ ] Manual verification required |
|   6 | Agent gateway frames and stale sweep         | Implemented  | `test_frames.py`, `test_stale_sweep.py`    | [ ] Manual verification required |
|   7 | Telemetry ingestion/querying                 | Implemented  | `test_telemetry_router.py`                 | [ ] Manual verification required |
|   8 | Alarms and faults                            | Implemented  | `test_alarms_router.py`                    | [ ] Manual verification required |
|   9 | Backups, logs, and pending commands          | Implemented  | Partial model/API coverage                 | [ ] Manual verification required |
|  10 | OTA and provisioning workflows               | Implemented  | Partial phase-three coverage               | [ ] Manual verification required |
|  11 | Database migrations and seed workflow        | Implemented  | Partial; deployed DB needed                | [ ] Manual verification required |
|  12 | Development install/database/run commands    | Implemented  | Unknown                                    | [ ] Manual verification required |
|  13 | Production deployment and external IdP setup | Partial      | Unknown                                    | [ ] Manual verification required |

## Quick Start and Tests

````bash
make install && make db-up && make migrate
make seed EMAIL=... && make run
pytest api/tests agent-gateway/tests
```

Quick start: `make install && make db-up && make migrate && make seed EMAIL=... && make run`
