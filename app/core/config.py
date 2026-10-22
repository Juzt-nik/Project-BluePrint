
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SIH26265 FDR Management Portal"
    environment: str = "development"

    # Runtime connection must use a dedicated, non-owner, non-superuser DB role.
    database_url: str = (
        "postgresql+psycopg://blueprint_app:CHANGE_ME@localhost:5432/sih26265"
    )
    # Use a schema-owner connection only for Alembic migrations; never for API traffic.
    migration_database_url: str | None = None
    database_ssl_required: bool = False
    database_pool_size: int = 5
    database_max_overflow: int = 5
    database_pool_timeout_seconds: int = 30

    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None
    supabase_storage_bucket: str = "fdr-documents-private"
    auth_request_timeout_seconds: float = 5.0

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()

