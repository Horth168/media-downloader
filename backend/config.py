"""Central configuration. Everything sensitive comes from environment variables."""
import os


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


class Config:
    # Comma-separated list of frontend origins allowed to call the API.
    ALLOWED_ORIGINS = [
        o.strip().rstrip("/")
        for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
        if o.strip()
    ]

    # Public URL of the frontend (used to send users back after Meta login).
    FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    # Public URL of this backend (used to build the OAuth redirect URI).
    BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:5000").rstrip("/")

    # Secret used to encrypt session tokens handed to the browser.
    SECRET_KEY = os.environ.get("SECRET_KEY", "")

    # Meta (Instagram / Facebook) app credentials — optional.
    META_APP_ID = os.environ.get("META_APP_ID", "")
    META_APP_SECRET = os.environ.get("META_APP_SECRET", "")
    META_GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "v21.0")

    # Limits
    MAX_DOWNLOAD_MB = _int("MAX_DOWNLOAD_MB", 200)
    MAX_CONVERT_MB = _int("MAX_CONVERT_MB", 150)
    REQUEST_TIMEOUT = _int("REQUEST_TIMEOUT", 20)
    MAX_REDIRECTS = 4
    RATE_LIMIT_DEFAULT = os.environ.get("RATE_LIMIT_DEFAULT", "120 per hour")
    RATE_LIMIT_DOWNLOAD = os.environ.get("RATE_LIMIT_DOWNLOAD", "30 per hour")

    USER_AGENT = "MediaDownloaderPWA/1.0 (+self-hosted)"

    @classmethod
    def meta_enabled(cls):
        return bool(cls.META_APP_ID and cls.META_APP_SECRET and cls.SECRET_KEY)
