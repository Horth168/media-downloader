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


logging.basicConfig(level=logging.INFO)
app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
