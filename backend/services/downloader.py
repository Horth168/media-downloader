"""Gets media to the browser. Nothing is stored permanently on the server.

* direct files are streamed straight through in 64 KB chunks
* platform media is fetched by yt-dlp into a private temp folder, streamed,
  and the folder is deleted as soon as the response closes
* MP3 conversion runs ffmpeg in that same temp folder
"""
import logging
import mimetypes
import os
import shutil
import subprocess
import tempfile
import threading
import time
from urllib.parse import quote

from flask import Response, stream_with_context

from config import Config
from services.errors import ApiError
from services.netguard import safe_request

log = logging.getLogger(__name__)
CHUNK = 64 * 1024
TMP_PREFIX = "mdl-"
# Work files go on disk next to the app, not in /tmp: on some hosts /tmp is RAM-backed,
# so a few large videos there would count against the memory limit and crash the server.
WORK_ROOT = os.environ.get("WORK_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".work")
os.makedirs(WORK_ROOT, exist_ok=True)
# Downloads/conversions are memory- and CPU-heavy; on a small server run one at a time.
HEAVY = threading.BoundedSemaphore(int(os.environ.get("MAX_PARALLEL_JOBS", "1")))


class _heavy_slot:
    def __enter__(self):
        if not HEAVY.acquire(timeout=240):
            raise ApiError("busy", "The server is busy with other downloads. Try again in a minute.", 503)

    def __exit__(self, *exc):
        HEAVY.release()
CONTENT_TYPES = {"mp4": "video/mp4", "webm": "video/webm", "mkv": "video/x-matroska", "mov": "video/quicktime",
                 "m4a": "audio/mp4", "mp3": "audio/mpeg", "opus": "audio/ogg", "ogg": "audio/ogg",
                 "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def _ffmpeg_exe():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg  # bundled static binary, works on Render's native Python runtime
    return imageio_ffmpeg.get_ffmpeg_exe()


def cleanup_stale_temp(max_age=3600):
    root = WORK_ROOT
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


def _new_workdir():
    cleanup_stale_temp()
    return tempfile.mkdtemp(prefix=TMP_PREFIX, dir=WORK_ROOT)


def _open_upstream(url, headers=None):
    resp = safe_request(url, stream=True, headers=headers)
    if resp.status_code >= 400:
        resp.close()
        if resp.status_code in (401, 403):
            raise ApiError("forbidden", "The source refused the download (it may be private or expired). "
                                        "Analyze the link again.", 403)
        raise ApiError("upstream_error", f"The source returned an error ({resp.status_code}).", 502)
    length = resp.headers.get("Content-Length")
    if length and length.isdigit() and int(length) > Config.MAX_DOWNLOAD_MB * 1024 * 1024:
        resp.close()
        raise ApiError("too_large", f"That file is larger than the {Config.MAX_DOWNLOAD_MB} MB limit.", 413)
    return resp


def stream_original(url, filename, headers=None):
    resp = _open_upstream(url, headers)
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

    out = {
        "Content-Type": resp.headers.get("Content-Type", "application/octet-stream").split(";")[0],
        "Content-Disposition": _disposition(filename),
        "X-File-Name": quote(filename),
        "Cache-Control": "no-store",
    }
    if resp.headers.get("Content-Length", "").isdigit():
        out["Content-Length"] = resp.headers["Content-Length"]
    return Response(stream_with_context(generate()), headers=out)


def _to_mp3(src, out):
    try:
        proc = subprocess.run(
            [_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
             "-i", src, "-vn", "-map", "a:0?", "-c:a", "libmp3lame", "-q:a", "2", "-threads", "1", out],
            capture_output=True, timeout=240,
        )
    except subprocess.TimeoutExpired:
        raise ApiError("convert_timeout", "Converting to MP3 took too long.", 504)
    if proc.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) == 0:
        log.warning("ffmpeg failed: %s", proc.stderr.decode(errors="ignore")[-500:])
        raise ApiError("no_audio", "This file has no audio track that can be converted to MP3.", 422)


def _probe_codecs(path):
    """Return (video_codec, audio_codec) using ffmpeg's stream info."""
    import re
    proc = subprocess.run([_ffmpeg_exe(), "-hide_banner", "-nostdin", "-i", path],
                          capture_output=True, timeout=60)
    info = proc.stderr.decode(errors="ignore")
    v = re.search(r"Stream #[^\n]*Video: (\w+)", info)
    a = re.search(r"Stream #[^\n]*Audio: (\w+)", info)
    return (v.group(1) if v else None), (a.group(1) if a else None)


def make_phone_friendly(path, workdir):
    """Return an MP4 that iPhone Photos, WhatsApp, Telegram etc. can all play.

    H.264/HEVC video and AAC audio are copied as-is (fast); anything else (VP9, AV1,
    Opus...) is converted. The moov atom goes to the front so playback starts at once.
    """
    v, a = _probe_codecs(path)
    if v is None:
        return path  # audio-only or unreadable: leave it alone
    out = os.path.join(workdir, "final.mp4")
    if v == "h264":
        vargs = ["-c:v", "copy"]
    elif v == "hevc":
        vargs = ["-c:v", "copy", "-tag:v", "hvc1"]  # iOS only plays HEVC tagged hvc1
    else:
        # Few threads + short lookahead keeps memory low on a 512 MB server.
        # Only reached for VP9/AV1 sources (H.264 is preferred when downloading). Capped at 720p,
        # one thread and a short lookahead so it fits in a 512 MB server.
        vargs = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                 "-threads", "1", "-x264-params", "rc-lookahead=8:sync-lookahead=0",
                 "-vf", "scale='if(gt(ih,iw),min(720,iw),-2)':'if(gt(ih,iw),-2,min(720,ih))'"]
    if a is None:
        aargs = []
    elif a == "aac":
        aargs = ["-c:a", "copy"]
    else:
        aargs = ["-c:a", "aac", "-b:a", "160k"]
    cmd = [_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-threads", "1", "-i", path,
           "-map", "0:v:0", "-map", "0:a:0?", *vargs, *aargs, "-movflags", "+faststart", out]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=900)
    except subprocess.TimeoutExpired:
        raise ApiError("convert_timeout", "Converting the video for your phone took too long. "
                                          "Try a lower quality.", 504)
    if proc.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) == 0:
        log.warning("phone-friendly conversion failed (%s/%s): %s", v, a,
                    proc.stderr.decode(errors="ignore")[-400:])
        return path
    log.info("phone-friendly: %s/%s -> %s", v, a, "copied" if v in ("h264", "hevc") else "re-encoded")
    os.remove(path)
    return out


def _stream_file(path, workdir, filename):
    """Stream a finished file, then delete its temp folder."""
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    if ext and not filename.lower().endswith("." + ext):
        filename = os.path.splitext(filename)[0] + "." + ext
    size = os.path.getsize(path)
    ctype = CONTENT_TYPES.get(ext) or mimetypes.guess_type(path)[0] or "application/octet-stream"

    def generate():
        try:
            with open(path, "rb") as f:
                while chunk := f.read(CHUNK):
                    yield chunk
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    return Response(stream_with_context(generate()), headers={
        "Content-Type": ctype,
        "Content-Length": str(size),
        "Content-Disposition": _disposition(filename),
        "X-File-Name": quote(filename),
        "Cache-Control": "no-store",
    })


def stream_mp3(url, filename, headers=None):
    workdir = _new_workdir()
    try:
        with _heavy_slot():
            src = os.path.join(workdir, "source")
            out = os.path.join(workdir, "audio.mp3")
            limit = Config.MAX_CONVERT_MB * 1024 * 1024
            resp = _open_upstream(url, headers)
            try:
                written = 0
                with open(src, "wb") as f:
                    for chunk in resp.iter_content(CHUNK):
                        written += len(chunk)
                        if written > limit:
                            raise ApiError("too_large",
                                           f"MP3 conversion is limited to files under {Config.MAX_CONVERT_MB} MB.",
                                           413)
                        f.write(chunk)
            finally:
                resp.close()
            _to_mp3(src, out)
            os.remove(src)
    except Exception:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    return _stream_file(out, workdir, filename)


def stream_platform(ticket):
    """Download with yt-dlp, optionally convert to MP3, then stream."""
    from services.platforms.ytdlp import download_to  # local import keeps startup light
    workdir = _new_workdir()
    try:
        with _heavy_slot():
            path = download_to(workdir, ticket)
            if ticket["m"] == "mp3" and not path.lower().endswith(".mp3"):
                if os.path.getsize(path) > Config.MAX_CONVERT_MB * 1024 * 1024:
                    raise ApiError("too_large",
                                   f"MP3 conversion is limited to files under {Config.MAX_CONVERT_MB} MB.", 413)
                out = os.path.join(workdir, "audio.mp3")
                _to_mp3(path, out)
                os.remove(path)
                path = out
            elif ticket["m"] == "video":
                path = make_phone_friendly(path, workdir)
    except Exception:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    return _stream_file(path, workdir, ticket["n"])
