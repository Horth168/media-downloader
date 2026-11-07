from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import Config

# In-memory storage is fine for a single free-tier instance.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[Config.RATE_LIMIT_DEFAULT],
    storage_uri="memory://",
    headers_enabled=True,
)
