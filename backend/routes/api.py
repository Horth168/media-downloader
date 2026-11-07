from flask import Blueprint, jsonify, request

from config import Config
from extensions import limiter
from services import downloader
from services.errors import ApiError
from services.netguard import validate_public_url
from services.platforms import all_platforms, detect
from services.tokens import read_ticket

api_bp = Blueprint("api", __name__)



@api_bp.get("/health")
@limiter.exempt
def health():
    import yt_dlp.version
    return jsonify(ok=True, status="healthy", engine=f"yt-dlp {yt_dlp.version.__version__}",
                   cookies=bool(Config.YTDLP_COOKIES),
                   limits={"max_download_mb": Config.MAX_DOWNLOAD_MB,
                           "max_convert_mb": Config.MAX_CONVERT_MB})


@api_bp.get("/platforms")
def platforms():
    return jsonify(ok=True, platforms=all_platforms())


@api_bp.post("/detect")
def detect_platform():
    url = (request.get_json(silent=True) or {}).get("url", "")
    if not isinstance(url, str) or not url.strip().lower().startswith(("http://", "https://")):
        raise ApiError("invalid_url", "Paste a full link starting with https://")
    p = detect(url.strip())
    return jsonify(ok=True, platform=p.describe())


@api_bp.post("/analyze")
def analyze():
    body = request.get_json(silent=True) or {}
    url = body.get("url", "")
    if not isinstance(url, str) or not url.strip():
        raise ApiError("invalid_url", "Paste a link first.")
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    platform = detect(url)
    platform.validate(url)          # cheap, platform-specific format checks first
    validate_public_url(url)        # scheme, host, port and SSRF checks
    media = platform.analyze(url)
    return jsonify(ok=True, platform=platform.describe(), media=media)


@api_bp.get("/download")
@limiter.limit(Config.RATE_LIMIT_DOWNLOAD)
def download():
    ticket = read_ticket(request.args.get("t", ""))
    if "y" in ticket:  # platform media fetched with yt-dlp
        return downloader.stream_platform(ticket)
    url, mode, filename, headers = ticket["u"], ticket["m"], ticket["n"], ticket.get("h")
    if mode == "mp3":
        return downloader.stream_mp3(url, filename, headers)
    return downloader.stream_original(url, filename, headers)
