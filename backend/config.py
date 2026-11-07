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

    # Secret used to encrypt session tokens handed to the browser.
    SECRET_KEY = os.environ.get("SECRET_KEY", "")

    # Optional cookies.txt contents for yt-dlp (helps when platforms ask for a login).
    YTDLP_COOKIES = os.environ.get("YTDLP_COOKIES", "")

    # Limits
    MAX_DOWNLOAD_MB = _int("MAX_DOWNLOAD_MB", 200)
    MAX_CONVERT_MB = _int("MAX_CONVERT_MB", 150)
    REQUEST_TIMEOUT = _int("REQUEST_TIMEOUT", 20)
    MAX_REDIRECTS = 4
    RATE_LIMIT_DEFAULT = os.environ.get("RATE_LIMIT_DEFAULT", "120 per hour")
    RATE_LIMIT_DOWNLOAD = os.environ.get("RATE_LIMIT_DOWNLOAD", "30 per hour")

    USER_AGENT = "MediaDownloaderPWA/1.0 (+self-hosted)"
