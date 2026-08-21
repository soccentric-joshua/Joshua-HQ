# Joshua-HQ Build and Deployment

## Purpose and scope

Joshua-HQ is the local orchestration entry point for the Python API, Python agent gateway, Vue web frontend, and Docker Compose services. The Makefile manages a `.venv`, Postgres, MinIO, Redis, Keycloak, database migrations, seeded development access, background service processes, tests, lint, and the web production build.

## 1. Prerequisites

- Docker and Docker Compose, Python 3 with `venv`, Node.js/npm, and curl. `make doctor` checks Docker, Python 3, and Node.
- Network/package access for Python editable installs and `web` npm dependencies.
- Ports available for Postgres `5432`, MinIO `9000`/`9001`, Redis `6379`, Keycloak `8081`, API `8000`, web `5173`, and gateway gRPC `50051`.

## 2. Setup

1. Run `make doctor`.
2. Run `make install` to create `.venv`, upgrade pip, install `./api[dev]` and `./agent-gateway[dev]` editable, and run `npm install` in `web`.
3. Run `make db-up` to start Postgres, MinIO, Redis, and Keycloak, wait for readiness, create `joshuahq_test`, and create the `joshuahq` MinIO bucket.
4. Run `make migrate` to apply Alembic migrations.
5. Optionally run `make seed EMAIL=admin@example.com` to pre-invite the development admin.

The Compose file uses development credentials: Postgres `joshuahq/joshuahq`, MinIO root `joshuahq/joshuahq-dev-secret`, and Keycloak admin `admin/admin`. Do not use these outside a trusted local network.

## 3. Build and compile

- `make build` - run `npm run build` in `web` for the production frontend bundle.
- `make run` - start dependencies, migrate, and launch API, gateway, and Vite web processes in the background.

The Makefile does not compile a native binary. Frontend artifacts are under `web/dist` for the Vite build path and any framework-specific output produced by the web package.

## 4. Test and lint

- `make test` - run API pytest, gateway pytest, and `npx vitest run` for the web.
- `make test-api` / `make test-gateway` / `make test-web` - run one suite.
- `make lint` - run ruff for API/gateway and `npm run lint` plus `npx vue-tsc --noEmit` for web.
- `make lint-api`, `make lint-gateway`, `make lint-web` - run one lint group.

API/gateway tests use `JOSHUAHQ_TEST_DATABASE_URL` and the local MinIO endpoint, so start `make db-up` first. Override `DATABASE_URL`, `TEST_DATABASE_URL`, or `S3_ENDPOINT_URL` when using another environment.

## 5. Packaging and artifacts

There is no package/archive target in this Makefile. `make build` creates the web production output; Python services run from the editable virtual environment. Compose images are pulled from the configured registries and are not built by this Makefile.

## 6. Deployment, install, and run

- `make run` launches API on port `8000`, agent gateway on `50051`, and Vite web on `5173`, recording PIDs/logs under `.run` and printing the LAN URL.
- `make logs` tails `.run/api.log`, `.run/gateway.log`, and `.run/web.log`.
- `make stop` stops background services but intentionally leaves Compose dependencies running.
- `make db-down` stops the Compose services while preserving Docker volumes.

The development login is `admin@example.com / devpassword` after the matching seed/invite. Use the printed LAN IP consistently because the Makefile notes that mixing `localhost` and LAN origins splits session cookies. This is a local deployment workflow; no cloud credentials or production hardening are supplied.

## 7. Cleanup

- `make stop` stops application processes.
- `make db-down` stops database/object-store/cache/identity containers; volumes persist.
- `make clean` removes `.venv`, `.run`, `web/node_modules`, `web/dist`, caches, and Python `__pycache__`/egg-info directories.

## 8. Hardware, cloud, and manual verification caveats

HQ has no direct hardware target. It depends on backend services and identity/object storage, so manually verify login, migrations, uploads, gateway connectivity, LAN access, and browser API calls. The bundled Keycloak settings, passwords, HTTP mode, and permissive hostname behavior are development-only and must not be treated as a cloud or production deployment configuration.
