from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Transaction Ledger API"
    database_url: str = "mysql+pymysql://ledger:ledger@127.0.0.1:3308/ledger"
    sql_echo: bool = False


settings = Settings()
