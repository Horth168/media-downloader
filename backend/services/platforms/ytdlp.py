"""TikTok, Douyin, YouTube, Instagram and Facebook via yt-dlp + small page readers.

yt-dlp reads the platforms' public web pages. Platforms change often and block
datacenter servers, so failures are expected from time to time — errors are
translated into plain messages, and yt-dlp is upgraded on every deploy.

Only the named platform extractors are enabled (no generic extractor), so yt-dlp
can't be pointed at arbitrary or internal URLs.
"""
import json
import logging
import os
import re
import shutil
import tempfile
from urllib.parse import urlsplit

import yt_dlp
from yt_dlp.utils import DownloadError, ExtractorError

from config import Config
from services.errors import ApiError
from services.netguard import safe_request
from services.platforms.base import Platform, build_item, safe_filename
from services.tokens import make_ticket

log = logging.getLogger(__name__)

MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")
DESKTOP_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
QUALITIES = (1080, 720, 480, 360)
MAX_ITEMS = 20

_ffmpeg_dir = None
_cookie_file = None


def ffmpeg_dir():
    """yt-dlp wants a folder containing a binary called `ffmpeg`."""
    global _ffmpeg_dir
    if _ffmpeg_dir:
        return _ffmpeg_dir
    exe = shutil.which("ffmpeg")
    if exe:
        _ffmpeg_dir = os.path.dirname(exe)
        return _ffmpeg_dir
    import imageio_ffmpeg
    folder = os.path.join(tempfile.gettempdir(), "fetchly-ffbin")
    os.makedirs(folder, exist_ok=True)
    link = os.path.join(folder, "ffmpeg")
    if not os.path.exists(link):
        os.symlink(imageio_ffmpeg.get_ffmpeg_exe(), link)
    _ffmpeg_dir = folder
    return folder


def cookie_file():
    """Optional cookies (Netscape cookies.txt text) from the YTDLP_COOKIES env var."""
    global _cookie_file
    if not Config.YTDLP_COOKIES:
        return None
    if _cookie_file and os.path.exists(_cookie_file):
        return _cookie_file
    from services.downloader import WORK_ROOT
    fd, path = tempfile.mkstemp(prefix="fetchly-cookies-", suffix=".txt", dir=WORK_ROOT)
    with os.fdopen(fd, "w") as f:
        f.write(Config.YTDLP_COOKIES.replace("\\n", "\n"))
    _cookie_file = path
    return path


def ydl_opts(extractors, **extra):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "socket_timeout": 20,
        "retries": 2,
        "allowed_extractors": list(extractors),
        "js_runtimes": {"deno": {}, "node": {}},
        "http_headers": {"Accept-Language": "en-US,en;q=0.9"},
        "buffersize": 64 * 1024,
        "http_chunk_size": 10 * 1024 * 1024,
    }
    cf = cookie_file()
    if cf:
        opts["cookiefile"] = cf
    opts.update(extra)
    return opts


def friendly_error(platform_name, err):
    msg = str(err)
    low = msg.lower()
    log.warning("yt-dlp error (%s): %s", platform_name, msg[:400])
    if "not a bot" in low or "sign in to confirm" in low:
        return ApiError("blocked_by_platform",
                        f"{platform_name} is blocking our server right now (it asked for a sign-in to prove we're "
                        "not a bot). Try again later, or add cookies on the server — see the README.", 503)
    if "private" in low:
        return ApiError("private", "That post is private, so it can't be downloaded.", 403)
    if any(k in low for k in ("login", "log in", "cookies", "rate-limit", "rate limit", "authentication")):
        return ApiError("login_required_platform",
                        f"{platform_name} wants a login before showing this post to our server. Try again later, "
                        "or add cookies on the server — see the README.", 403)
    if "unsupported url" in low:
        return ApiError("invalid_url", f"That doesn't look like a {platform_name} post link.", 400)
    if any(k in low for k in ("unavailable", "removed", "not found", "404", "does not exist")):
        return ApiError("not_found", "That post was removed or isn't available.", 404)
    if "geo" in low or "country" in low:
        return ApiError("geo_blocked", "That post isn't available in the server's region.", 451)
    if "requested format" in low:
        return ApiError("format_unavailable", "That quality isn't available for this post. Pick another.", 422)
    if "drm" in low:
        return ApiError("drm", "That video is copy-protected (DRM) and can't be downloaded.", 422)
    return ApiError("extract_failed", f"Couldn't read that {platform_name} post. Try again in a moment.", 502)


H264 = "[vcodec~='^(avc|h264)']"


def _height_selector(h, platform=None):
    """Pick a format at or below height h, always with sound.

    * separate video + audio tracks are merged (bv*+ba) whenever an audio track exists,
      so posts that keep sound in its own track don't come out silent
    * H.264 is preferred (plays in iPhone Photos without converting); others get converted
    * Facebook's ready-made hd/sd files come first: no merging or converting needed
    """
    parts = []
    if platform == "facebook":
        parts.append("b[format_id^=hd]" if h >= 720 else "b[format_id^=sd]/b[format_id^=hd]")
    parts += [f"bv*[height<={h}]{H264}+ba", f"bv*[height<={h}]+ba",
              f"b[height<={h}]{H264}", f"b[height<={h}]", "b"]
    return "/".join(parts)


def _estimate_size(formats, h):
    vids = [f for f in formats if f.get("vcodec") not in (None, "none") and (f.get("height") or 0) <= h]
    if not vids:
        return None
    best = max(vids, key=lambda f: ((f.get("height") or 0), f.get("tbr") or 0))
    size = best.get("filesize") or best.get("filesize_approx")
    if size and best.get("acodec") in (None, "none"):
        auds = [f for f in formats if f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")]
        if auds:
            a = max(auds, key=lambda f: f.get("tbr") or 0)
            size += a.get("filesize") or a.get("filesize_approx") or 0
    return int(size) if size else None


def _audio_size(formats):
    auds = [f for f in formats if f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")]
    if not auds:
        return None
    a = max(auds, key=lambda f: f.get("tbr") or 0)
    s = a.get("filesize") or a.get("filesize_approx")
    return int(s) if s else None


def _log_formats(name, info):
    """One compact line per post: which formats the platform offered (id:vcodec/acodec@height)."""
    try:
        node = (info.get("entries") or [info])[0] or {}
        fm = [f"{f.get('format_id')}:{(f.get('vcodec') or '?')[:6]}/{(f.get('acodec') or '?')[:6]}@{f.get('height')}"
              for f in (node.get("formats") or [])][-14:]
        log.info("%s formats: %s", name, " ".join(fm))
    except Exception:  # noqa: BLE001 — logging only
        pass


class YtdlpPlatform(Platform):
    extractors = ()
    page_headers = {}

    def status(self):
        return {"available": True, "requires_login": False,
                "reason": "Public posts. The platform may block some requests."}

    def validate(self, url):
        pass

    # --- helpers -----------------------------------------------------------
    def resolve(self, url):
        """Follow short-link redirects (vm.tiktok.com, v.douyin.com, fb share links)."""
        try:
            r = safe_request(url, headers={"User-Agent": MOBILE_UA})
            final = r.url
            r.close()
            return final
        except ApiError:
            return url

    def extract(self, url):
        try:
            with yt_dlp.YoutubeDL(ydl_opts(self.extractors, skip_download=True)) as ydl:
                info = ydl.sanitize_info(ydl.extract_info(url, download=False))
        except (DownloadError, ExtractorError) as e:
            raise friendly_error(self.name, e)
        _log_formats(self.name, info)
        return info

    def media_from_info(self, info, page_url):
        entries = info.get("entries")
        nodes = list(entries)[:MAX_ITEMS] if entries else [info]
        nodes = [n for n in nodes if n]
        if not nodes:
            raise ApiError("not_found", "Nothing downloadable was found in that post.", 404)
        title = (info.get("title") or info.get("description") or nodes[0].get("title") or self.name)
        title = title.splitlines()[0][:70]
        items = []
        for i, n in enumerate(nodes):
            items.append(self._video_item(n, page_url, title if len(nodes) == 1 else f"{title}_{i + 1}",
                                          index=(i + 1) if entries else None))
        return {
            "title": title,
            "author": info.get("uploader") or info.get("channel") or nodes[0].get("uploader"),
            "thumbnail": info.get("thumbnail") or nodes[0].get("thumbnail"),
            "kind": "carousel" if len(items) > 1 else "video",
            "items": items,
        }

    def _video_item(self, n, page_url, title, index=None):
        formats = n.get("formats") or [n]
        heights = sorted({f.get("height") for f in formats
                          if f.get("height") and f.get("vcodec") not in (None, "none")}, reverse=True)
        top = heights[0] if heights else None
        base = safe_filename(title, None)
        target = n.get("webpage_url") or page_url
        out = []
        has_video = bool(heights) or any(f.get("vcodec") not in (None, "none") for f in formats)
        if has_video:
            levels = [q for q in QUALITIES if top and q <= top][:3] or [None]
            if top and top not in QUALITIES and top < 1080 and top not in levels:
                levels = [top] + levels[:2]
            for h in levels:
                sel = _height_selector(h, self.id) if h else f"bv*{H264}+ba/bv*+ba/b"
                label_q = f"{h}p" if h else "Best available"
                out.append(self._fmt(f"mp4-{h or 'best'}", "MP4 Video", label_q, "mp4",
                                     _estimate_size(formats, h) if h else None,
                                     target, sel, "video", base, index))
        out.append(self._fmt("mp3", "MP3 Audio", "Audio only", "mp3", _audio_size(formats),
                             target, "ba/b", "mp3", base, index))
        return {
            "id": str(n.get("id") or index or 0),
            "type": "video" if has_video else "audio",
            "thumbnail": n.get("thumbnail"),
            "width": n.get("width"),
            "height": n.get("height"),
            "duration": n.get("duration"),
            "formats": out,
        }

    def _fmt(self, fid, label, quality, ext, size, url, selector, mode, base, index):
        is_sized = fid.startswith("mp4-") and fid != "mp4-best"
        filename = safe_filename(f"{base}_{quality}" if is_sized else base, ext)
        return {
            "id": fid, "label": label, "quality": quality, "ext": ext, "size": size, "filename": filename,
            "ticket": make_ticket({"y": url, "x": self.id, "f": selector, "m": mode, "n": filename, "i": index}),
        }

    def analyze(self, url, session=None):
        return self.media_from_info(self.extract(url), url)


def _image_items(urls, title, headers, item_prefix="img"):
    items = []
    for i, u in enumerate(urls[:MAX_ITEMS]):
        it = build_item(source_url=u, kind="image", title=f"{title}_{i + 1}" if len(urls) > 1 else title,
                        ext="jpg", thumbnail=u, item_id=f"{item_prefix}{i}")
        for f in it["formats"]:
            # Re-sign with the headers the CDN expects.
            f["ticket"] = make_ticket({"u": u, "m": "original", "n": f["filename"], "k": "image", "h": headers})
        items.append(it)
    return items


def _audio_direct_item(url, title, headers):
    base = safe_filename(title, None)
    fn = safe_filename(base, "mp3")
    return {
        "id": "audio", "type": "audio", "thumbnail": None, "width": None, "height": None,
        "formats": [{"id": "mp3", "label": "MP3 Audio", "quality": "Post soundtrack", "ext": "mp3", "size": None,
                     "filename": fn,
                     "ticket": make_ticket({"u": url, "m": "mp3", "n": fn, "k": "audio", "h": headers})}],
    }


class YouTube(YtdlpPlatform):
    id = "youtube"
    name = "YouTube"
    color = "#ff0033"
    domains = ("youtube.com", "youtu.be", "youtube-nocookie.com")
    extractors = ("youtube",)
    # Other YouTube clients sometimes slip past the bot check when the default one is blocked.
    fallback_clients = (["android_vr"], ["tv"], ["mweb"], ["web_safari"])

    def extract(self, url):
        try:
            return super().extract(url)
        except ApiError as first:
            if first.code != "blocked_by_platform":
                raise
            for clients in self.fallback_clients:
                try:
                    opts = ydl_opts(self.extractors, skip_download=True,
                                    extractor_args={"youtube": {"player_client": clients}})
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.sanitize_info(ydl.extract_info(url, download=False))
                    info["_clients"] = clients
                    return info
                except (DownloadError, ExtractorError) as e:
                    log.info("YouTube client %s failed: %s", clients, str(e)[:160])
            raise first

    def media_from_info(self, info, page_url):
        media = super().media_from_info(info, page_url)
        clients = info.get("_clients")
        if clients:  # remember which client worked, so the download uses it too
            from services.tokens import read_ticket
            for it in media["items"]:
                for f in it["formats"]:
                    t = read_ticket(f["ticket"])
                    t["c"] = clients
                    f["ticket"] = make_ticket(t)
        return media


class Instagram(YtdlpPlatform):
    id = "instagram"
    name = "Instagram"
    color = "#e1306c"
    domains = ("instagram.com", "instagr.am")
    extractors = ("instagram",)


def _browser_get(extractor_key, url, video_id="page"):
    """Fetch a page through yt-dlp's networking (browser impersonation + cookie handling)."""
    with yt_dlp.YoutubeDL(ydl_opts((extractor_key.lower(),))) as ydl:
        ie = ydl.get_info_extractor(extractor_key)
        try:
            webpage, urlh = ie._download_webpage_handle(
                url, video_id, note=False, impersonate=True, headers={"Accept-Language": "en-US,en;q=0.9"})
        except (DownloadError, ExtractorError) as e:
            raise ApiError("extract_failed", f"Couldn't open that link ({str(e)[:80]}).", 502)
        return webpage, urlh.url


class Facebook(YtdlpPlatform):
    id = "facebook"
    name = "Facebook"
    color = "#1877f2"
    domains = ("facebook.com", "fb.com", "fb.watch")
    extractors = ("facebook", "facebook:reel", "facebookredirecturl")
    VIDEO_PATH = re.compile(r"/(?:reel|videos|watch|[\w.]+/videos)/|[?&]v=\d|story_fbid=")

    def resolve_share(self, url):
        """Turn /share/v/..., /share/r/... and fb.watch links into the real video link."""
        webpage, final = _browser_get("Facebook", url)
        parsed = urlsplit(final)
        if "login" in parsed.path:
            from urllib.parse import parse_qs, unquote
            nxt = parse_qs(parsed.query).get("next", [None])[0]
            if nxt:
                final = unquote(nxt)
        if self.VIDEO_PATH.search(final):
            return final
        for pat in (r'<meta[^>]+property="og:url"[^>]+content="([^"]+)"',
                    r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"',
                    r'"(https:\\/\\/www\.facebook\.com\\/(?:reel|watch|[^"]+?\\/videos)\\/[^"]+)"'):
            m = re.search(pat, webpage)
            if m:
                cand = m.group(1).replace("\\/", "/").replace("&amp;", "&")
                if self.VIDEO_PATH.search(cand):
                    return cand
        m = re.search(r'"video_id":"(\d{6,})"', webpage) or re.search(r"/reel/(\d{6,})", webpage)
        if m:
            return f"https://www.facebook.com/reel/{m.group(1)}"
        log.warning("Facebook share link didn't resolve: %s -> %s", url, final)
        raise ApiError("login_required_platform",
                       "Facebook wouldn't show this shared link to our server. Open it in Facebook, tap Share → "
                       "Copy link on the video itself (a /reel/ or /videos/ link), and paste that.", 403)

    def analyze(self, url, session=None):
        p = urlsplit(url)
        if "/share/" in p.path or (p.hostname or "").endswith("fb.watch"):
            url = self.resolve_share(url)
        return super().analyze(url)


class TikTok(YtdlpPlatform):
    id = "tiktok"
    name = "TikTok"
    color = "#25f4ee"
    domains = ("tiktok.com",)
    extractors = ("tiktok", "vm.tiktok")
    cdn_headers = {"User-Agent": DESKTOP_UA, "Referer": "https://www.tiktok.com/"}

    def resolve_short(self, url):
        try:
            _, final = _browser_get("TikTok", url, "short")
            return final
        except ApiError:
            return self.resolve(url)

    def analyze(self, url, session=None):
        p = urlsplit(url)
        if (p.hostname or "").startswith(("vm.", "vt.")) or p.path.startswith("/t/"):
            url = self.resolve_short(url)
        if "/photo/" in urlsplit(url).path:
            return self.photo_post(url)
        media = super().analyze(url)
        if all(it["type"] == "audio" for it in media["items"]):
            # Slideshow posts come back from yt-dlp as audio only — fetch the photos too.
            try:
                return self.photo_post(url)
            except ApiError:
                pass
        return media

    def photo_post(self, url):
        m = re.search(r"/(?:photo|video)/(\d+)", url)
        if not m:
            raise ApiError("invalid_url", "That doesn't look like a TikTok post link.", 400)
        post_id = m.group(1)
        um = re.search(r"/@([\w.-]+)/", url)
        user = um.group(1) if um else "_"
        candidates = [f"https://www.tiktok.com/@{user}/video/{post_id}",
                      f"https://www.tiktok.com/@{user}/photo/{post_id}"]

        images, title, author, music = [], None, None, None
        with yt_dlp.YoutubeDL(ydl_opts(self.extractors)) as ydl:
            ie = ydl.get_info_extractor("TikTok")

            # Route 1 + 2: the web page (yt-dlp handles TikTok's challenge cookie).
            for cand in candidates:
                try:
                    item, status = ie._extract_web_data_and_status(cand, post_id, fatal=False)
                except (DownloadError, ExtractorError) as e:
                    log.info("TikTok web data failed for %s: %s", cand, str(e)[:160])
                    item, status = None, -1
                if status in (10216, 10222):
                    raise ApiError("private", "That TikTok post is private, so it can't be downloaded.", 403)
                found = _find_image_post(item)
                if not found:
                    try:
                        page = ie._download_webpage(cand, post_id, note=False, fatal=False, impersonate=True,
                                                    headers=ie._generate_blockbuster_headers())
                        data = ie._get_universal_data(page, post_id) if page else {}
                        log.info("TikTok page %s scopes: %s", cand, list(data)[:12])
                        found = _find_image_post(data)
                    except (DownloadError, ExtractorError) as e:
                        log.info("TikTok page fetch failed for %s: %s", cand, str(e)[:160])
                if found:
                    images = [u for u in (_pick_jpeg((i.get("imageURL") or {}).get("urlList"))
                                          for i in found["imagePost"]["images"]) if u]
                    title = found.get("desc")
                    author = (found.get("author") or {}).get("uniqueId")
                    music = (found.get("music") or {}).get("playUrl")
                    break

            # Route 3: TikTok's app API.
            if not images:
                try:
                    from yt_dlp.utils import urlencode_postdata
                    res = ie._call_api("multi/aweme/detail", post_id, data=urlencode_postdata({
                        "aweme_ids": f"[{post_id}]", "request_source": "0"}), headers={"X-Argus": ""})
                    aweme = ((res or {}).get("aweme_details") or [None])[0] or {}
                    imgs = (aweme.get("image_post_info") or {}).get("images") or []
                    images = [u for u in (_pick_jpeg((i.get("display_image") or {}).get("url_list"))
                                          for i in imgs) if u]
                    title = aweme.get("desc")
                    author = (aweme.get("author") or {}).get("unique_id")
                    music = (((aweme.get("music") or {}).get("play_url") or {}).get("url_list") or [None])[0]
                    log.info("TikTok app API for %s: %d images", post_id, len(images))
                except Exception as e:  # noqa: BLE001 — best effort
                    log.info("TikTok app API failed for %s: %s", post_id, str(e)[:160])

        if not images:
            log.warning("TikTok photo post %s: no images found by any route", post_id)
            raise ApiError("extract_failed", "TikTok didn't give our server the photos for this post. "
                                             "Try again in a minute.", 502)
        title = (title or f"tiktok_{post_id}").splitlines()[0][:70]
        items = _image_items(images, title, self.cdn_headers)
        if music:
            items.append(_audio_direct_item(music, title, self.cdn_headers))
        return {"title": title, "author": author, "thumbnail": images[0],
                "kind": "carousel" if len(items) > 1 else "image", "items": items}


def _pick_jpeg(urls):
    urls = urls or []
    return next((u for u in urls if "jpeg" in u or ".jpg" in u), urls[0] if urls else None)


def _find_image_post(obj, depth=0):
    """Find the first dict holding a non-empty imagePost anywhere in TikTok's page data."""
    if depth > 8 or obj is None:
        return None
    if isinstance(obj, dict):
        ip = obj.get("imagePost")
        if isinstance(ip, dict) and ip.get("images"):
            return obj
        for v in obj.values():
            r = _find_image_post(v, depth + 1)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj[:50]:
            r = _find_image_post(v, depth + 1)
            if r:
                return r
    return None


class Douyin(YtdlpPlatform):
    id = "douyin"
    name = "Douyin"
    color = "#fe2c55"
    domains = ("douyin.com", "iesdouyin.com")
    extractors = ("douyin",)
    cdn_headers = {"User-Agent": MOBILE_UA, "Referer": "https://www.douyin.com/"}

    def aweme_id(self, url):
        for pat in (r"/(?:video|note|slides|share/video|share/note|share/slides)/(\d{8,})", r"modal_id=(\d{8,})",
                    r"aweme_id=(\d{8,})"):
            m = re.search(pat, url)
            if m:
                return m.group(1)
        return None

    def analyze(self, url, session=None):
        aid = self.aweme_id(url)
        if not aid:
            aid = self.aweme_id(self.resolve(url))
        if not aid:
            raise ApiError("invalid_url", "That doesn't look like a Douyin video or photo link.", 400)
        try:
            return self.share_page(aid)
        except ApiError as first:
            try:
                return super().analyze(f"https://www.douyin.com/video/{aid}")
            except ApiError:
                raise first

    def share_page(self, aid):
        r = safe_request(f"https://www.iesdouyin.com/share/video/{aid}/", headers={"User-Agent": MOBILE_UA})
        html = r.text
        r.close()
        m = re.search(r"window\._ROUTER_DATA\s*=\s*(\{.*?\})\s*</script>", html, re.S)
        if not m:
            t = re.search(r"<title>(.*?)</title>", html, re.S)
            log.warning("Douyin share page %s: no _ROUTER_DATA (final=%s, %d bytes, title=%r)",
                        aid, r.url, len(html), (t.group(1).strip()[:80] if t else None))
            raise ApiError("extract_failed", "Couldn't read that Douyin post. Try again in a moment.", 502)
        try:
            loader = json.loads(m.group(1))["loaderData"]
            res = next(v["videoInfoRes"] for v in loader.values() if isinstance(v, dict) and v.get("videoInfoRes"))
            item = res["item_list"][0]
        except (ValueError, KeyError, StopIteration, IndexError, TypeError) as e:
            log.warning("Douyin share page %s: unexpected data (%s: %s)", aid, type(e).__name__, str(e)[:120])
            raise ApiError("not_found", "That Douyin post was removed, is private, or couldn't be read.", 404)

        title = (item.get("desc") or f"douyin_{aid}").splitlines()[0][:70]
        author = (item.get("author") or {}).get("nickname")
        images = [img["url_list"][0] for img in (item.get("images") or []) if img.get("url_list")]
        if images:
            items = _image_items(images, title, self.cdn_headers)
            music = ((item.get("music") or {}).get("play_url") or {}).get("url_list") or []
            if music:
                items.append(_audio_direct_item(music[0], title, self.cdn_headers))
            return {"title": title, "author": author, "thumbnail": images[0],
                    "kind": "carousel" if len(items) > 1 else "image", "items": items}

        video = item.get("video") or {}
        urls = (video.get("play_addr") or {}).get("url_list") or []
        if not urls:
            raise ApiError("format_unavailable", "Douyin didn't provide a video file for this post.", 422)
        play = urls[0].replace("playwm", "play")  # no-watermark variant
        cover = ((video.get("cover") or {}).get("url_list") or [None])[0]
        it = build_item(source_url=play, kind="video", title=title, ext="mp4", thumbnail=cover, item_id=aid)
        for f in it["formats"]:
            f["ticket"] = make_ticket({"u": play, "m": "original" if f["id"] == "mp4" else "mp3",
                                       "n": f["filename"], "k": "video", "h": self.cdn_headers})
        return {"title": title, "author": author, "thumbnail": cover, "kind": "video", "items": [it]}


# --- downloading ---------------------------------------------------------------
EXTRACTORS = {cls.id: cls.extractors for cls in (YouTube, Instagram, Facebook, TikTok, Douyin)}
NAMES = {cls.id: cls.name for cls in (YouTube, Instagram, Facebook, TikTok, Douyin)}


def download_to(workdir, ticket):
    """Download one item with yt-dlp into workdir. Returns the file path."""
    pid = ticket["x"]
    opts = ydl_opts(
        EXTRACTORS[pid],
        outtmpl=os.path.join(workdir, "media.%(ext)s"),
        format=ticket["f"],
        merge_output_format="mp4",
        ffmpeg_location=ffmpeg_dir(),
        max_filesize=Config.MAX_DOWNLOAD_MB * 1024 * 1024,
        overwrites=True,
        format_sort=["vcodec:h264", "acodec:aac"],
        # Instagram doesn't say whether its video files carry sound; letting yt-dlp merge the
        # separate audio track anyway avoids silent videos (the phone-friendly step keeps one track).
        allow_multiple_audio_streams=True,
    )
    if ticket.get("c"):
        opts["extractor_args"] = {"youtube": {"player_client": ticket["c"]}}
    if ticket.get("i"):
        opts["noplaylist"] = False
        opts["playlist_items"] = str(ticket["i"])
    attempts = [opts]
    if pid == "youtube":
        # The bot check can hit any client at any time — try the others before giving up.
        tried = ticket.get("c")
        # Without cookies every client usually hits the same block; don't make people wait for all of them.
        candidates = [None, *YouTube.fallback_clients] if Config.YTDLP_COOKIES else [None, ["android_vr"]]
        for clients in candidates:
            if clients == tried:
                continue
            alt = dict(opts)
            if clients:
                alt["extractor_args"] = {"youtube": {"player_client": clients}}
            else:
                alt.pop("extractor_args", None)
            attempts.append(alt)
    err = None
    for attempt in attempts:
        try:
            with yt_dlp.YoutubeDL(attempt) as ydl:
                ydl.download([ticket["y"]])
            err = None
            break
        except (DownloadError, ExtractorError) as e:
            err = e
            low = str(e).lower()
            retriable = ("not a bot", "sign in", "format", "empty", "403", "forbidden", "unable to download",
                         "fragment", "http error")
            if pid != "youtube" or not any(k in low for k in retriable):
                break
            log.info("YouTube download attempt failed (%s): %s",
                     (attempt.get("extractor_args") or {}).get("youtube"), str(e)[:120])
            for f in os.listdir(workdir):
                os.remove(os.path.join(workdir, f))
    if err:
        raise friendly_error(NAMES[pid], err)
    files = [os.path.join(workdir, f) for f in os.listdir(workdir)
             if not f.endswith((".part", ".ytdl", ".temp")) and os.path.isfile(os.path.join(workdir, f))]
    if not files:
        raise ApiError("too_large", f"That file is over the {Config.MAX_DOWNLOAD_MB} MB limit, "
                                    "or the platform didn't send it. Try a lower quality.", 413)
    return max(files, key=os.path.getsize)
