"""Signed download tickets and encrypted Meta session tokens."""
import base64
import hashlib
import logging
import secrets

from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from config import Config
from services.errors import ApiError

log = logging.getLogger(__name__)

_secret = Config.SECRET_KEY
if not _secret:
    # Fine for local dev; in production SECRET_KEY must be set so tokens
    # survive restarts and Meta sessions can be decrypted.
    _secret = secrets.token_urlsafe(48)
    log.warning("SECRET_KEY not set — using a temporary random key.")

_ticket_signer = URLSafeTimedSerializer(_secret, salt="download-ticket-v1")
_fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(("meta:" + _secret).encode()).digest()))

TICKET_MAX_AGE = 60 * 60  # 1 hour


def make_ticket(payload):
    return _ticket_signer.dumps(payload)


def read_ticket(ticket):
    try:
        return _ticket_signer.loads(ticket, max_age=TICKET_MAX_AGE)
    except SignatureExpired:
        raise ApiError("ticket_expired", "This download link expired. Analyze the link again.", 410)
    except BadSignature:
        raise ApiError("bad_ticket", "Invalid download link.", 400)


def encrypt_session(data: str) -> str:
    return _fernet.encrypt(data.encode()).decode()


def decrypt_session(token: str) -> str:
    try:
        return _fernet.decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        raise ApiError("session_invalid", "Your Meta session is invalid or expired. Please reconnect.", 401)
