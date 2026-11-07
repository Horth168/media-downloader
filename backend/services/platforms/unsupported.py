"""Platforms whose official APIs do not offer media file downloads.

They are still recognised, validated and — where an official oEmbed endpoint
exists — previewed, but they return a clear `unsupported` response instead of
pretending to download anything.
"""
import re
from urllib.parse import parse_qs, urlsplit

from services.errors import ApiError
from services.netguard import safe_request
from services.platforms.base import Platform


class _PreviewOnly(Platform):
    oembed = None
    reason = ""

    def status(self):
        return {"available": False, "requires_login": False, "reason": self.reason}

    def _preview(self, url):
        if not self.oembed:
            return {}
        try:
            r = safe_request(self.oembed, params={"url": url, "format": "json"})
            if r.status_code == 200:
                d = r.json()
                return {"title": d.get("title"), "author": d.get("author_name"),
                        "thumbnail": d.get("thumbnail_url")}
        except (ApiError, ValueError):
            pass
        return {}

    def analyze(self, url, session=None):
        self.validate(url)
        preview = self._preview(url)
        raise ApiError(
            "platform_unsupported", self.reason, 422,
            platform=self.describe(), preview=preview or None,
        )


class YouTube(_PreviewOnly):
    id = "youtube"
    name = "YouTube"
    color = "#ff0033"
    domains = ("youtube.com", "youtu.be", "youtube-nocookie.com")
    oembed = "https://www.youtube.com/oembed"
    reason = ("YouTube's official API doesn't allow downloading video or audio files — not even for "
              "your own uploads. Use YouTube Studio (your videos) or YouTube Premium offline viewing.")

    def validate(self, url):
        p = urlsplit(url)
        host = (p.hostname or "").lower()
        vid = None
        if host.endswith("youtu.be"):
            vid = p.path.strip("/").split("/")[0]
        else:
            vid = parse_qs(p.query).get("v", [None])[0]
            m = re.match(r"^/(shorts|embed|live|v)/([\w-]{6,})", p.path)
            if m:
                vid = m.group(2)
        if not vid or not re.fullmatch(r"[\w-]{6,20}", vid):
            raise ApiError("invalid_url", "That YouTube link doesn't point to a video.")


class TikTok(_PreviewOnly):
    id = "tiktok"
    name = "TikTok"
    color = "#25f4ee"
    domains = ("tiktok.com",)
    oembed = "https://www.tiktok.com/oembed"
    reason = ("TikTok's official API only shares video details and embeds, not downloadable files. "
              "To save your own videos, use the download option inside the TikTok app.")

    def validate(self, url):
        p = urlsplit(url)
        host = (p.hostname or "").lower()
        if host.startswith(("vm.", "vt.")):
            return  # short share links
        if not re.search(r"/(video|photo)/\d+", p.path):
            raise ApiError("invalid_url", "That TikTok link doesn't point to a video or photo post.")


class Douyin(_PreviewOnly):
    id = "douyin"
    name = "Douyin"
    color = "#fe2c55"
    domains = ("douyin.com", "iesdouyin.com")
    reason = ("Douyin's open platform doesn't offer public video downloads. Use the save option in the "
              "Douyin app for content you're allowed to keep.")

    def validate(self, url):
        p = urlsplit(url)
        host = (p.hostname or "").lower()
        if host.startswith("v."):
            return
        if not re.search(r"/(video|note|share/video)/\d+", p.path) and "modal_id" not in p.query:
            raise ApiError("invalid_url", "That Douyin link doesn't point to a video.")
