"""Direct media links: any public URL that serves a video, audio or image file."""
import posixpath
from urllib.parse import urlsplit, unquote

from services.errors import ApiError
from services.netguard import safe_request
from services.platforms.base import Platform, build_item, kind_from_content_type

EXT_BY_CT = {
    "video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov",
    "audio/mpeg": "mp3", "audio/mp4": "m4a", "audio/aac": "aac", "audio/wav": "wav",
    "audio/x-wav": "wav", "audio/ogg": "ogg", "audio/flac": "flac",
    "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif",
    "image/avif": "avif", "image/heic": "heic",
}


class DirectLink(Platform):
    id = "direct"
    name = "Direct link"
    color = "#8b5cf6"

    def matches(self, url):
        return True

    def status(self):
        return {"available": True, "requires_login": False,
                "reason": "Public links that point straight to a video, audio or image file."}

    def analyze(self, url, session=None):
        resp = safe_request(url, stream=True, headers={"Range": "bytes=0-0"})
        try:
            if resp.status_code in (401, 403):
                raise ApiError("forbidden", "That file is private or needs a login, so it can't be downloaded.", 403)
            if resp.status_code == 404:
                raise ApiError("not_found", "Nothing was found at that link.", 404)
            if resp.status_code >= 400:
                raise ApiError("upstream_error", f"The website returned an error ({resp.status_code}).", 502)

            ct = resp.headers.get("Content-Type", "")
            path = unquote(urlsplit(resp.url).path)
            stem, ext = posixpath.splitext(posixpath.basename(path))
            ext = ext.lstrip(".").lower()
            ext = EXT_BY_CT.get(ct.split(";")[0].strip().lower(), ext)
            kind = kind_from_content_type(ct, ext)
            if kind is None:
                if ct.startswith("text/html"):
                    raise ApiError(
                        "not_media",
                        "That link opens a web page, not a media file. This site isn't a supported "
                        "platform, so only direct links to .mp4, .mp3, .jpg and similar files work.",
                        422,
                    )
                raise ApiError("not_media", "That link doesn't point to a video, audio or image file.", 422)

            size = _total_size(resp)
        finally:
            resp.close()

        title = stem or "media"
        item = build_item(source_url=url, kind=kind, title=title, ext=ext, size=size)
        return {
            "title": title,
            "author": urlsplit(url).hostname,
            "thumbnail": url if kind == "image" else None,
            "kind": kind,
            "items": [item],
        }


def _total_size(resp):
    cr = resp.headers.get("Content-Range", "")
    if "/" in cr:
        total = cr.rsplit("/", 1)[-1]
        if total.isdigit():
            return int(total)
    cl = resp.headers.get("Content-Length")
    if cl and cl.isdigit() and resp.status_code == 200:
        return int(cl)
    return None
