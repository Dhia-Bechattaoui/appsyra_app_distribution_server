import os

from app_distribution_server.logger import logger
from typing import Optional

# Storage configuration
# For local development: "osfs://./uploads"
# For S3: "s3://bucket-name" (requires AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION)
# For Cloudflare R2: "s3://bucket-name" (requires AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_ENDPOINT_URL)
STORAGE_URL = os.getenv("STORAGE_URL", "osfs://./uploads")

# R2/S3 Configuration
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL")
AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "auto")

# Database URL (provided by Render automatically)
DATABASE_URL = os.getenv("DATABASE_URL")

UPLOADS_SECRET_AUTH_TOKEN = os.getenv("UPLOADS_SECRET_AUTH_TOKEN")

if not UPLOADS_SECRET_AUTH_TOKEN:
    UPLOADS_SECRET_AUTH_TOKEN = "mysecretpassword"  # noqa: S105
    logger.warn(
        "SECURITY WARNING: Using default auth token!"
        " For security reasons override it with the 'UPLOADS_SECRET_AUTH_TOKEN' env var.",
    )

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")
APP_VERSION = os.getenv("APP_VERSION") or "0.0.1-development"
APP_TITLE = "Appsyra"

# Log the current configuration for debugging
logger.info(f"APP_BASE_URL: {APP_BASE_URL}")
logger.info(f"APP_VERSION: {APP_VERSION}")

_raw_logo_url = os.getenv("LOGO_URL", "/static/logo.png")
LOGO_URL: Optional[str] = None if _raw_logo_url.lower() in ["", "0", "false"] else _raw_logo_url

COMPANY_NAME = "Appsyra"


def get_absolute_url(path: str) -> str:
    if not path.startswith("/"):
        path = f"/{path}"

    return f"{APP_BASE_URL}{path}"
