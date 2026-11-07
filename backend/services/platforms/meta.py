"""Instagram and Facebook via Meta's official Graph API.

Only media belonging to accounts the signed-in user manages can be fetched:
  * Instagram: Business/Creator accounts linked to a Facebook Page they manage
  * Facebook: videos, reels and photos posted by Pages they manage
Anything else returns a clear `not_owned` response.
"""
import json
import re
import time
from urllib.parse import parse_qs, urlsplit

from config import Config
from services.errors import ApiError
from services.netguard import safe_request
from services.platforms.base import Platform, build_item
from services.tokens import decrypt_session

GRAPH = "https://graph.facebook.com"
SCOPES = "public_profile,pages_show_list,pages_read_engagement,instagram_basic"
MAX_PAGES_SCAN = 8  # pages of 50 IG posts to scan when matching a permalink


def graph(path, token, **params):
    params["access_token"] = token
    r = safe_request(f"{GRAPH}/{Config.META_GRAPH_VERSION}/{path.lstrip('/')}", params=params,
                     validate=False)
    try:
        data = r.json()
    except ValueError:
        raise ApiError("meta_error", "Meta returned an unexpected response.", 502)
    if r.status_code >= 400 or "error" in data:
        err = data.get("error", {})
        code = err.get("code")
        if code == 190:
            raise ApiError("session_invalid", "Your Meta login expired. Please reconnect in Settings.", 401)
        msg = (err.get("message") or "").lower()
        if code in (10, 200) or (code == 100 and "permission" in msg):
            raise ApiError("not_owned", "That content isn't available to your connected Meta accounts.", 403)
        if code == 100:
            raise ApiError("not_found", "Meta couldn't find that content for your connected accounts.", 404)
        if code in (4, 17, 32, 613):
            raise ApiError("meta_rate_limited", "Meta's rate limit was reached. Try again later.", 429)
        raise ApiError("meta_error", err.get("message", "Meta API error."), 502)
    return data


def user_token_from_session(session):
    if not session:
        raise ApiError("login_required",
                       "Connect your Meta account in Settings to download your own Instagram/Facebook media.",
                       401)
    data = json.loads(decrypt_session(session))
    if data.get("exp") and data["exp"] < time.time():
        raise ApiError("session_invalid", "Your Meta login expired. Please reconnect in Settings.", 401)
    return data["t"]


def managed_pages(user_token):
    data = graph("me/accounts", user_token,
                 fields="id,name,access_token,instagram_business_account{id,username}", limit=100)
    return data.get("data", [])


class _MetaPlatform(Platform):
    def status(self):
        if not Config.meta_enabled():
            return {"available": False, "requires_login": True,
                    "reason": "Meta login isn't configured on the server yet (META_APP_ID / META_APP_SECRET)."}
        return {"available": True, "requires_login": True,
                "reason": f"Only {self.name} media from accounts you manage, after connecting Meta."}

    def _require_enabled(self):
        if not Config.meta_enabled():
            raise ApiError("platform_unavailable", self.status()["reason"], 503, platform=self.describe())


class Instagram(_MetaPlatform):
    id = "instagram"
    name = "Instagram"
    color = "#e1306c"
    domains = ("instagram.com", "instagr.am")

    def shortcode(self, url):
        m = re.match(r"^/(?:[\w.]+/)?(p|reel|reels|tv)/([\w-]{5,})", urlsplit(url).path)
        return m.group(2) if m else None

    def validate(self, url):
        if not self.shortcode(url):
            raise ApiError("invalid_url", "That Instagram link doesn't point to a post, reel or carousel.")

    def analyze(self, url, session=None):
        self.validate(url)
        self._require_enabled()
        code = self.shortcode(url)
        token = user_token_from_session(session)
        accounts = [p for p in managed_pages(token) if p.get("instagram_business_account")]
        if not accounts:
            raise ApiError("not_owned", "No Instagram Business/Creator account is linked to your Facebook Pages.", 403)

        fields = ("id,caption,media_type,media_url,thumbnail_url,permalink,username,"
                  "children{id,media_type,media_url,thumbnail_url}")
        for page in accounts:
            ig_id = page["instagram_business_account"]["id"]
            path, params = f"{ig_id}/media", {"fields": fields, "limit": 50}
            for _ in range(MAX_PAGES_SCAN):
                data = graph(path, token, **params)
                for m in data.get("data", []):
                    if f"/{code}" in (m.get("permalink") or ""):
                        return self._to_media(m)
                nxt = data.get("paging", {}).get("cursors", {}).get("after")
                if not nxt or not data.get("paging", {}).get("next"):
                    break
                params = {"fields": fields, "limit": 50, "after": nxt}
        raise ApiError("not_owned",
                       "That post isn't on an Instagram account you've connected, so it can't be downloaded.",
                       403)

    def _to_media(self, m):
        title = (m.get("caption") or f"instagram_{m['id']}").splitlines()[0][:60]
        nodes = m.get("children", {}).get("data") or [m]
        items = []
        for i, n in enumerate(nodes):
            if not n.get("media_url"):
                continue  # e.g. copyrighted-audio reels where Meta omits the URL
            kind = "video" if n.get("media_type") == "VIDEO" else "image"
            items.append(build_item(
                source_url=n["media_url"], kind=kind,
                title=f"{title}_{i + 1}" if len(nodes) > 1 else title,
                ext="mp4" if kind == "video" else "jpg",
                thumbnail=n.get("thumbnail_url") or (n["media_url"] if kind == "image" else None),
                item_id=n.get("id", i)))
        if not items:
            raise ApiError("format_unavailable", "Meta didn't provide a downloadable file for this post.", 422)
        return {
            "title": title,
            "author": m.get("username"),
            "thumbnail": items[0]["thumbnail"],
            "kind": "carousel" if len(items) > 1 else items[0]["type"],
            "items": items,
        }


class Facebook(_MetaPlatform):
    id = "facebook"
    name = "Facebook"
    color = "#1877f2"
    domains = ("facebook.com", "fb.com", "fb.watch")

    def object_ref(self, url):
        p = urlsplit(url)
        q = parse_qs(p.query)
        if (p.hostname or "").endswith("fb.watch"):
            return None, None
        m = re.search(r"/(?:videos|reel|watch/live)/(?:[\w.-]+/)?(\d{5,})", p.path)
        if m:
            return "video", m.group(1)
        if p.path.startswith("/watch") and q.get("v"):
            return "video", q["v"][0]
        if q.get("fbid") and ("photo" in p.path):
            return "photo", q["fbid"][0]
        m = re.search(r"/photos/(?:[\w.-]+/)*(\d{5,})", p.path)
        if m:
            return "photo", m.group(1)
        return None, None

    def validate(self, url):
        if (urlsplit(url).hostname or "").endswith("fb.watch"):
            raise ApiError("invalid_url",
                           "Short fb.watch links can't be resolved without logging in. Open it in Facebook, "
                           "then copy the full video link (facebook.com/.../videos/...).")
        kind, _ = self.object_ref(url)
        if not kind:
            raise ApiError("invalid_url",
                           "Paste a link to a specific Facebook video, reel or photo (not a whole post or profile).")

    def analyze(self, url, session=None):
        self.validate(url)
        self._require_enabled()
        kind, obj_id = self.object_ref(url)
        token = user_token_from_session(session)
        pages = managed_pages(token)
        if not pages:
            raise ApiError("not_owned", "Your Meta account doesn't manage any Facebook Pages.", 403)
        page_ids = {p["id"] for p in pages}

        for page in pages:
            try:
                if kind == "video":
                    d = graph(obj_id, page["access_token"], fields="id,title,description,source,picture,from,length")
                else:
                    d = graph(obj_id, page["access_token"], fields="id,name,images,from")
            except ApiError as e:
                if e.code in ("not_owned", "not_found"):
                    continue
                raise
            if d.get("from", {}).get("id") not in page_ids:
                continue
            return self._video(d) if kind == "video" else self._photo(d)
        raise ApiError("not_owned",
                       "That isn't posted by a Facebook Page you manage, so it can't be downloaded.", 403)

    def _video(self, d):
        if not d.get("source"):
            raise ApiError("format_unavailable", "Facebook didn't provide a downloadable file for this video.", 422)
        title = (d.get("title") or d.get("description") or f"facebook_{d['id']}").splitlines()[0][:60]
        item = build_item(source_url=d["source"], kind="video", title=title, ext="mp4",
                          thumbnail=d.get("picture"), item_id=d["id"])
        return {"title": title, "author": d.get("from", {}).get("name"),
                "thumbnail": d.get("picture"), "kind": "video", "items": [item]}

    def _photo(self, d):
        images = sorted(d.get("images", []), key=lambda i: i.get("width", 0) * i.get("height", 0), reverse=True)
        if not images:
            raise ApiError("format_unavailable", "Facebook didn't provide this photo.", 422)
        best = images[0]
        title = (d.get("name") or f"facebook_{d['id']}").splitlines()[0][:60]
        item = build_item(source_url=best["source"], kind="image", title=title, ext="jpg",
                          width=best.get("width"), height=best.get("height"), item_id=d["id"])
        return {"title": title, "author": d.get("from", {}).get("name"),
                "thumbnail": best["source"], "kind": "image", "items": [item]}
