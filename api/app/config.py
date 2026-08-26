from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Development-only default credentials baked into this file. They are safe ONLY
# when `env == dev` on a disposable local stack. Any of these values reaching a
# non-dev environment is refused at startup.
_DEV_SECRET_DEFAULTS = {
    "database_url": "postgresql+asyncpg://joshuahq:joshuahq@localhost:5432/joshuahq",
    "oidc_client_secret": "dev-secret-change-me",
    "session_secret_key": "dev-only-change-me-in-every-real-deployment",
    "s3_access_key": "joshuahq",
    "s3_secret_key": "joshuahq-dev-secret",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JOSHUAHQ_", env_file=".env", extra="ignore")

    env: str = "dev"

    database_url: str = "postgresql+asyncpg://joshuahq:joshuahq@localhost:5432/joshuahq"

    # OIDC (human auth). Dev default points at the self-hosted Keycloak
    # brought up by infra/docker-compose.yml -- see IMPLEMENTATION_PLAN §1.2:
    # "if no IdP is chosen yet, use a self-hosted option... so Phase 1 isn't
    # blocked on an external vendor decision."
    oidc_issuer: str = "http://localhost:8081/realms/joshuahq"
    oidc_client_id: str = "joshuahq-api"
    oidc_client_secret: str = "dev-secret-change-me"
    # No static oidc_redirect_uri: it's derived per-request from the
    # browser's actual origin (X-Forwarded-Host, forwarded by Vite's dev
    # proxy) in app/routers/auth.py -- a fixed value breaks the moment the
    # app is reachable at more than one hostname (localhost, LAN IP, mDNS
    # name), which is exactly what the LAN-access setup needs.
    oidc_redirect_fallback_host: str = "localhost:5173"

    # Session JWT issued by the API after OIDC login, stored in an httpOnly cookie.
    session_secret_key: str = "dev-only-change-me-in-every-real-deployment"
    session_algorithm: str = "HS256"
    session_ttl_seconds: int = 60 * 60 * 8

    # Object storage (S3-compatible; MinIO in local dev).
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "joshuahq"
    s3_secret_key: str = "joshuahq-dev-secret"
    s3_bucket: str = "joshuahq"
    s3_region: str = "us-east-1"

    # Redis (arq background jobs).
    redis_url: str = "redis://localhost:6379/0"

    # Presence / heartbeat.
    heartbeat_interval_s: int = 30
    heartbeat_missed_threshold: int = 2  # offline after N missed intervals

    # Pairing tokens.
    pairing_token_ttl_seconds: int = 15 * 60

    cors_allow_origins: list[str] = ["http://localhost:5173"]

    @model_validator(mode="after")
    def _refuse_dev_default_secrets_outside_dev(self) -> "Settings":
        """Fail fast if a development-only secret default is left in place in a
        non-development environment.

        Every credential in `_SECRET_DEFAULTS` is a dev-only value. A production/
        staging deployment must override them via env vars / a generated secret
        file; starting up with the defaults would expose the stack.
        """
        if self.env in ("dev", "development"):
            return self
        offenders = [
            name
            for name, default in _DEV_SECRET_DEFAULTS.items()
            if getattr(self, name, None) == default
        ]
        if offenders:
            raise ValueError(
                "refusing to start: non-dev environment with development-only "
                f"credentials ({', '.join(sorted(offenders))}). Override them via "
                "JOSHUAHQ_* env vars or a generated local secret file."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
