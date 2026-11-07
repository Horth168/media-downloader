"""Meta (Facebook Login) OAuth flow.

The long-lived Meta user token never reaches the browser in readable form:
it is encrypted with SECRET_KEY and handed to the frontend as an opaque
session string, which the frontend sends back as `Authorization: Bearer ...`.
"""
import json
import time
from urllib.parse import urlencode

from flask import Blueprint, jsonify, redirect, request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from config import Config
from services.errors import ApiError
from services.netguard import safe_request
from services.platforms.meta import SCOPES, graph, managed_pages, user_token_from_session
from services.tokens import _secret, encrypt_session

auth_bp = Blueprint("auth", __name__)
_state = URLSafeTimedSerializer(_secret, salt="meta-oauth-state")


def _redirect_uri():
    return f"{Config.BACKEND_URL}/auth/meta/callback"


def _back_to_app(**fragment):
    return redirect(f"{Config.FRONTEND_URL}/#/settings?{urlencode(fragment)}")


@auth_bp.get("/meta/login")
def meta_login():
    if not Config.meta_enabled():
        raise ApiError("platform_unavailable", "Meta login isn't configured on the server yet.", 503)
    state = _state.dumps({"t": time.time()})
    params = {
        "client_id": Config.META_APP_ID,
        "redirect_uri": _redirect_uri(),
        "state": state,
        "scope": SCOPES,
        "response_type": "code",
    }
    return redirect(f"https://www.facebook.com/{Config.META_GRAPH_VERSION}/dialog/oauth?{urlencode(params)}")


@auth_bp.get("/meta/callback")
def meta_callback():
    if request.args.get("error"):
        return _back_to_app(meta_error=request.args.get("error_description", "Login was cancelled."))
    try:
        _state.loads(request.args.get("state", ""), max_age=600)
    except BadSignature:
        return _back_to_app(meta_error="Login expired or was tampered with. Please try again.")
    code = request.args.get("code")
    if not code:
        return _back_to_app(meta_error="Meta didn't return a login code.")

    base = f"https://graph.facebook.com/{Config.META_GRAPH_VERSION}/oauth/access_token"
    try:
        short = safe_request(base, params={
            "client_id": Config.META_APP_ID, "client_secret": Config.META_APP_SECRET,
            "redirect_uri": _redirect_uri(), "code": code}, validate=False).json()
        if "access_token" not in short:
            raise ApiError("meta_error", short.get("error", {}).get("message", "Token exchange failed."))
        long = safe_request(base, params={
            "grant_type": "fb_exchange_token", "client_id": Config.META_APP_ID,
            "client_secret": Config.META_APP_SECRET, "fb_exchange_token": short["access_token"]},
            validate=False).json()
    except (ApiError, ValueError) as e:
        return _back_to_app(meta_error=getattr(e, "message", "Couldn't complete Meta login."))

    token = long.get("access_token") or short["access_token"]
    expires_in = long.get("expires_in") or short.get("expires_in") or 3600
    session = encrypt_session(json.dumps({"t": token, "exp": time.time() + int(expires_in)}))
    return _back_to_app(meta_session=session)


@auth_bp.get("/meta/me")
def meta_me():
    auth = request.headers.get("Authorization", "")
    token = user_token_from_session(auth[7:].strip() if auth.lower().startswith("bearer ") else None)
    me = graph("me", token, fields="id,name")
    pages = managed_pages(token)
    return jsonify(ok=True, name=me.get("name"), pages=[
        {"id": p["id"], "name": p["name"],
         "instagram": (p.get("instagram_business_account") or {}).get("username")}
        for p in pages
    ])


@auth_bp.post("/meta/logout")
def meta_logout():
    """Revoke the app's permissions on Meta's side. The browser forgets the session itself."""
    auth = request.headers.get("Authorization", "")
    try:
        token = user_token_from_session(auth[7:].strip() if auth.lower().startswith("bearer ") else None)
        safe_request(f"https://graph.facebook.com/{Config.META_GRAPH_VERSION}/me/permissions",
                     method="DELETE", params={"access_token": token}, validate=False).close()
    except ApiError:
        pass
    return jsonify(ok=True)
