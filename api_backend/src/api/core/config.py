import os
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class AppConfig:
    """Application configuration resolved from environment variables.

    This object is created once at the API boundary and passed down into flows.
    """

    cors_origins: List[str]
    scrape_timeout_seconds: float
    scrape_user_agent: str

    postgres_url: Optional[str]
    postgres_user: Optional[str]
    postgres_password: Optional[str]
    postgres_db: Optional[str]
    postgres_port: Optional[str]


def _split_csv(value: str) -> List[str]:
    parts = [p.strip() for p in value.split(",")]
    return [p for p in parts if p]


# PUBLIC_INTERFACE
def load_config() -> AppConfig:
    """Load configuration from environment variables.

    Contract:
      - Inputs: environment variables (documented in api_backend/.env.example)
      - Outputs: AppConfig with normalized values
      - Errors: raises ValueError for invalid numeric values
      - Side effects: none

    Notes:
      - Database variables are expected to be injected by the postgres_db container
        (see db_env_vars in the work item).
    """
    cors_raw = os.getenv("API_CORS_ORIGINS", "*").strip()
    cors_origins = ["*"] if cors_raw == "*" else _split_csv(cors_raw)

    timeout_raw = os.getenv("SCRAPE_TIMEOUT_SECONDS", "12").strip()
    try:
        scrape_timeout_seconds = float(timeout_raw)
    except ValueError as exc:
        raise ValueError("SCRAPE_TIMEOUT_SECONDS must be a number") from exc

    scrape_user_agent = os.getenv(
        "SCRAPE_USER_AGENT", "PriceCompareBot/1.0 (+https://example.com)"
    ).strip()

    return AppConfig(
        cors_origins=cors_origins,
        scrape_timeout_seconds=scrape_timeout_seconds,
        scrape_user_agent=scrape_user_agent,
        postgres_url=os.getenv("POSTGRES_URL"),
        postgres_user=os.getenv("POSTGRES_USER"),
        postgres_password=os.getenv("POSTGRES_PASSWORD"),
        postgres_db=os.getenv("POSTGRES_DB"),
        postgres_port=os.getenv("POSTGRES_PORT"),
    )
