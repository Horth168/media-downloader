"""Flask entrypoint. Run locally with `python app.py`; in production via gunicorn."""
import logging
import os

from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from extensions import limiter
from routes.api import api_bp
from services.errors import ApiError


def create_app():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024  # request bodies are tiny JSON
    app.config["JSON_SORT_KEYS"] = False

    # Render sits behind one proxy: trust X-Forwarded-For / Proto once.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    CORS(
        app,
        origins=Config.ALLOWED_ORIGINS,
        allow_headers=["Content-Type", "Authorization"],
        expose_headers=["Content-Disposition", "Content-Length", "X-File-Name"],
        max_age=600,
    )
    limiter.init_app(app)

    app.register_blueprint(api_bp, url_prefix="/api")

    @app.get("/")
    def root():
        return jsonify(name="media-downloader-api", status="ok", docs="/api/health")

    @app.errorhandler(ApiError)
    def handle_api_error(err):
        return jsonify(ok=False, error=err.code, message=err.message, **err.extra), err.status

    @app.errorhandler(429)
    def handle_rate_limit(err):
        return jsonify(ok=False, error="rate_limited",
                       message="Too many requests. Please wait a bit and try again."), 429

    @app.errorhandler(404)
    def handle_404(err):
        return jsonify(ok=False, error="not_found", message="Endpoint not found."), 404

    @app.errorhandler(Exception)
    def handle_unexpected(err):
        if hasattr(err, "code") and isinstance(getattr(err, "code"), int):
            return jsonify(ok=False, error="http_error", message=str(err)), err.code
        app.logger.exception("Unhandled error")
        return jsonify(ok=False, error="server_error", message="Something went wrong on the server."), 500

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        return resp

    return app


def _mem():
    """Memory report: this process's peak, ffmpeg's peak, and the container's current/peak usage."""
    import resource
    parts = [f"py_peak={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024}MB",
             f"child_peak={resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss // 1024}MB"]
    for name in ("memory.current", "memory.peak"):
        try:
            parts.append(f"cg_{name.split('.')[1]}={int(open('/sys/fs/cgroup/' + name).read()) // 1048576}MB")
        except (OSError, ValueError):
            pass
    return " ".join(parts)


def _selftest(app):
    """If SELFTEST_URLS is set, analyze those links (and fetch the first file) at startup and log the result."""
    import json
    import threading
    import time

    urls = [u.strip() for u in os.environ.get("SELFTEST_URLS", "").split(",") if u.strip()]
    if not urls:
        return

    def run():
        time.sleep(3)
        log = logging.getLogger("selftest")
        client = app.test_client()
        for url in urls:
            log.warning("SELFTEST start %s | %s", url, _mem())
            r = client.post("/api/analyze", json={"url": url})
            j = r.get_json() or {}
            if not j.get("ok"):
                log.warning("SELFTEST %s -> %s %s: %s", url, r.status_code, j.get("error"), j.get("message"))
                continue
            m = j["media"]
            log.warning("SELFTEST %s -> OK %s, %d items: %s", url, m["kind"], len(m["items"]),
                        json.dumps([[it["type"], [f["id"] for f in it["formats"]]] for it in m["items"]])[:300])
            for it in m["items"][:4]:
                vids = [f for f in it["formats"] if f["id"].startswith("mp4")]
                for f in (vids[-1:] if vids else it["formats"][:1]):  # smallest video quality is enough
                    d = client.get("/api/download?t=" + f["ticket"])
                    codecs = ""
                    if d.status_code == 200 and f["id"].startswith("mp4"):
                        import tempfile
                        from services.downloader import _probe_codecs
                        with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp:
                            tmp.write(d.data)
                            tmp.flush()
                            codecs = "codecs=%s/%s" % _probe_codecs(tmp.name)
                    log.warning("SELFTEST download %s -> %s %s %d bytes %s | %s", f["filename"], d.status_code,
                                d.headers.get("Content-Type"), len(d.data), codecs, _mem())

    threading.Thread(target=run, daemon=True).start()


logging.basicConfig(level=logging.INFO)
app = create_app()
try:  # one-line environment report, helps diagnose memory/disk limits on the host
    import tempfile
    mounts = open("/proc/mounts").read().splitlines()
    tmp_mount = [m for m in mounts if " /tmp " in m] or ["(no separate /tmp mount)"]
    logging.getLogger("env").warning("ENV tmpdir=%s mount=%s cwd=%s", tempfile.gettempdir(), tmp_mount[0], os.getcwd())
except Exception:  # noqa: BLE001
    pass
_selftest(app)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
