"""Streams media to the browser. Nothing is stored permanently on the server.

* original files are streamed straight through in 64 KB chunks
* MP3 extraction downloads into a private temp folder, converts with ffmpeg,
  streams the result, and deletes the folder as soon as the response closes
"""
import logging
import os
import shutil
import subprocess
import tempfile
import time
from urllib.parse import quote

from flask import Response, stream_with_context

from config import Config
from services.errors import ApiError
from services.netguard import safe_request

log = logging.getLogger(__name__)
CHUNK = 64 * 1024
TMP_PREFIX = "mdl-"


def _ffmpeg_exe():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg  # bundled static binary, works on Render's native Python runtime
    return imageio_ffmpeg.get_ffmpeg_exe()


def cleanup_stale_temp(max_age=3600):
    root = tempfile.gettempdir()
    now = time.time()
    for name in os.listdir(root):
        if name.startswith(TMP_PREFIX):
            path = os.path.join(root, name)
            try:
                if now - os.path.getmtime(path) > max_age:
                    shutil.rmtree(path, ignore_errors=True)
            except OSError:
                pass


def _disposition(filename):
    ascii_name = filename.encode("ascii", "ignore").decode() or "download"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def _open_upstream(url):
    resp = safe_request(url, stream=True)
    if resp.status_code >= 400:
        resp.close()
        if resp.status_code in (401, 403):
            raise ApiError("forbidden", "The source refused the download (it may be private or expired).", 403)
        raise ApiError("upstream_error", f"The source returned an error ({resp.status_code}).", 502)
    length = resp.headers.get("Content-Length")
    if length and length.isdigit() and int(length) > Config.MAX_DOWNLOAD_MB * 1024 * 1024:
        resp.close()
        raise ApiError("too_large", f"That file is larger than the {Config.MAX_DOWNLOAD_MB} MB limit.", 413)
    return resp


def stream_original(url, filename):
    resp = _open_upstream(url)
    limit = Config.MAX_DOWNLOAD_MB * 1024 * 1024

    def generate():
        sent = 0
        try:
            for chunk in resp.iter_content(CHUNK):
                sent += len(chunk)
                if sent > limit:
                    log.warning("Stopped stream at size limit for %s", filename)
                    break
                yield chunk
        finally:
            resp.close()

    headers = {
        "Content-Type": resp.headers.get("Content-Type", "application/octet-stream").split(";")[0],
        "Content-Disposition": _disposition(filename),
        "X-File-Name": quote(filename),
        "Cache-Control": "no-store",
    }
    if resp.headers.get("Content-Length", "").isdigit():
        headers["Content-Length"] = resp.headers["Content-Length"]
    return Response(stream_with_context(generate()), headers=headers)


def stream_mp3(url, filename):
    cleanup_stale_temp()
    workdir = tempfile.mkdtemp(prefix=TMP_PREFIX)
    try:
        src = os.path.join(workdir, "source")
        out = os.path.join(workdir, "audio.mp3")
        limit = Config.MAX_CONVERT_MB * 1024 * 1024
        resp = _open_upstream(url)
        try:
            written = 0
            with open(src, "wb") as f:
                for chunk in resp.iter_content(CHUNK):
                    written += len(chunk)
                    if written > limit:
                        raise ApiError("too_large",
                                       f"MP3 conversion is limited to files under {Config.MAX_CONVERT_MB} MB.", 413)
                    f.write(chunk)
        finally:
            resp.close()

        try:
            proc = subprocess.run(
                [_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                 "-i", src, "-vn", "-map", "a:0?", "-c:a", "libmp3lame", "-q:a", "2", out],
                capture_output=True, timeout=180,
            )
        except subprocess.TimeoutExpired:
            raise ApiError("convert_timeout", "Converting to MP3 took too long.", 504)
        if proc.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) == 0:
            log.warning("ffmpeg failed: %s", proc.stderr.decode(errors="ignore")[-500:])
            raise ApiError("no_audio", "This file has no audio track that can be converted to MP3.", 422)
        os.remove(src)
        size = os.path.getsize(out)
    except Exception:
        shutil.rmtree(workdir, ignore_errors=True)
        raise

    def generate():
        try:
            with open(out, "rb") as f:
                while chunk := f.read(CHUNK):
                    yield chunk
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    return Response(stream_with_context(generate()), headers={
        "Content-Type": "audio/mpeg",
        "Content-Length": str(size),
        "Content-Disposition": _disposition(filename),
        "X-File-Name": quote(filename),
        "Cache-Control": "no-store",
    })
