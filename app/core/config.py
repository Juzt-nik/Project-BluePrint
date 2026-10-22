from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SIH26265 FDR Management Portal"
    environment: str = "development"
    # Use the Supabase PostgreSQL connection string from Project Settings > Database.
    # Prefer the session pooler for long-running FastAPI services when direct IPv6
    # connectivity is unavailable. Keep the password URL-encoded if it has symbols.
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/sih26265"
    database_ssl_required: bool = False
    database_pool_size: int = 5
    database_max_overflow: int = 5
    database_pool_timeout_seconds: int = 30

    # Used in the next integration step for Supabase Auth and private Storage.
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None
    supabase_storage_bucket: str = "fdr-documents-private"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)


settings = Settings()
