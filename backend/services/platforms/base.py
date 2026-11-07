"""Shared building blocks for platform integrations."""
import re
from urllib.parse import urlsplit, unquote

from services.tokens import make_ticket

VIDEO_EXT = {"mp4", "m4v", "mov", "webm", "mkv"}
AUDIO_EXT = {"mp3", "m4a", "aac", "wav", "ogg", "opus", "flac"}
IMAGE_EXT = {"jpg", "jpeg", "png", "webp", "gif", "heic", "avif"}


def host_of(url):
    return (urlsplit(url).hostname or "").lower().rstrip(".")


def host_matches(url, domains):
    h = host_of(url)
    return any(h == d or h.endswith("." + d) for d in domains)


def safe_filename(name, ext):
    name = re.sub(r"[^\w\-. ]+", "", unquote(name or ""), flags=re.UNICODE).strip(" .")
    name = re.sub(r"\s+", "_", name)[:80] or "media"
    if ext and not name.lower().endswith("." + ext):
        name = f"{name}.{ext}"
    return name


def kind_from_content_type(ct, ext=""):
    ct = (ct or "").split(";")[0].strip().lower()
    if ct.startswith("video/") or ext in VIDEO_EXT:
        return "video"
    if ct.startswith("audio/") or ext in AUDIO_EXT:
        return "audio"
    if ct.startswith("image/") or ext in IMAGE_EXT:
        return "image"
    return None


def build_item(*, source_url, kind, title, ext, size=None, thumbnail=None,
               width=None, height=None, item_id="0"):
    """One downloadable media item with its available formats + signed tickets."""
    base = safe_filename(title, None)
    formats = []
    if kind == "video":
        formats.append(_fmt("mp4", "MP4 Video", "Original", ext or "mp4", size,
                            source_url, base, "original", "video"))
        formats.append(_fmt("mp3", "MP3 Audio", "Extracted audio", "mp3", None,
                            source_url, base, "mp3", "audio"))
    elif kind == "audio":
        if ext == "mp3":
            formats.append(_fmt("mp3", "MP3 Audio", "Original", "mp3", size,
                                source_url, base, "original", "audio"))
        else:
            formats.append(_fmt("original", f"{(ext or 'audio').upper()} Audio", "Original",
                                ext or "audio", size, source_url, base, "original", "audio"))
            formats.append(_fmt("mp3", "MP3 Audio", "Converted", "mp3", None,
                                source_url, base, "mp3", "audio"))
    elif kind == "image":
        formats.append(_fmt("photo", f"{(ext or 'jpg').upper()} Photo", "Original quality",
                            ext or "jpg", size, source_url, base, "original", "image"))
    return {
        "id": str(item_id),
        "type": kind,
        "thumbnail": thumbnail or (source_url if kind == "image" else None),
        "width": width,
        "height": height,
        "formats": formats,
    }


def _fmt(fid, label, quality, ext, size, source_url, base, mode, kind):
    filename = safe_filename(base, ext)
    return {
        "id": fid,
        "label": label,
        "quality": quality,
        "ext": ext,
        "size": size,
        "filename": filename,
        "ticket": make_ticket({"u": source_url, "m": mode, "n": filename, "k": kind}),
    }


class Platform:
    """Base class. Subclasses describe how to recognise and fetch a platform's media."""

    id = "base"
    name = "Base"
    domains = ()
    color = "#888888"

    def matches(self, url):
        return host_matches(url, self.domains)

    def status(self):
        """Whether downloads are possible right now, and why not if not."""
        return {"available": False, "requires_login": False, "reason": "Not implemented."}

    def describe(self):
        return {"id": self.id, "name": self.name, "color": self.color, **self.status()}

    def validate(self, url):
        """Raise ApiError if the URL is not a recognisable media URL for this platform."""

    def analyze(self, url, session=None):
        raise NotImplementedError
