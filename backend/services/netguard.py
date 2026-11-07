"""SSRF-safe outbound HTTP.

Every URL the server fetches goes through `safe_request`, which:
  * allows only http/https on ports 80/443, no embedded credentials
  * resolves the hostname and rejects private, loopback, link-local,
    reserved, multicast and other non-public addresses
  * follows redirects manually, re-validating every hop
  * applies connect/read timeouts
"""
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import requests

from config import Config
from services.errors import ApiError

_session = requests.Session()
_session.headers.update({"User-Agent": Config.USER_AGENT})

BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal", "metadata"}


def _is_public_ip(ip_str):
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast and not ip.is_reserved


def validate_public_url(url):
    """Return a normalised URL or raise ApiError if it is not a safe public URL."""
    if not isinstance(url, str) or len(url) > 2048:
        raise ApiError("invalid_url", "That doesn't look like a valid link.")
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise ApiError("invalid_url", "Only http:// and https:// links are supported.")
    if not parts.hostname:
        raise ApiError("invalid_url", "That link is missing a website address.")
    if parts.username or parts.password:
        raise ApiError("invalid_url", "Links with embedded usernames or passwords are not allowed.")
    try:
        port = parts.port
    except ValueError:
        raise ApiError("invalid_url", "That link has an invalid port.")
    if port not in (None, 80, 443):
        raise ApiError("blocked_url", "Only standard web ports (80/443) are allowed.")

    host = parts.hostname.lower().rstrip(".")
    if host in BLOCKED_HOSTNAMES or host.endswith((".local", ".internal", ".localhost")):
        raise ApiError("blocked_url", "Links to private or internal addresses are not allowed.")

    try:
        infos = socket.getaddrinfo(host, port or (443 if parts.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ApiError("unreachable", "Couldn't find that website. Check the link and try again.")
    addresses = {info[4][0] for info in infos}
    if not addresses or not all(_is_public_ip(a) for a in addresses):
        raise ApiError("blocked_url", "Links to private or internal addresses are not allowed.")
    return url


def safe_request(url, method="GET", stream=False, headers=None, params=None, validate=True):
    """Make a request, following redirects safely. Returns the final Response."""
    current = validate_public_url(url) if validate else url
    for _ in range(Config.MAX_REDIRECTS + 1):
        try:
            resp = _session.request(
                method, current, stream=stream, headers=headers, params=params,
                allow_redirects=False, timeout=(8, Config.REQUEST_TIMEOUT),
            )
        except requests.Timeout:
            raise ApiError("timeout", "The website took too long to respond.", 504)
        except requests.RequestException:
            raise ApiError("unreachable", "Couldn't connect to that website.", 502)

        if resp.is_redirect or resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location")
            resp.close()
            if not location:
                raise ApiError("bad_redirect", "The website sent an invalid redirect.", 502)
            current = validate_public_url(urljoin(current, location))
            params = None  # params were part of the first URL only
            if resp.status_code == 303:
                method = "GET"
            continue
        return resp
    raise ApiError("too_many_redirects", "That link redirects too many times.", 502)
