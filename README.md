# Fetchly — Media Saver PWA

An installable web app for saving videos, audio and photos **you own or are allowed to download**.
Paste a link, see what's available, and save it as MP4, MP3 or original-quality photos.

- **Frontend:** React + Vite + Tailwind CSS + Lucide icons, installable PWA (`frontend/`)
- **Backend:** Python Flask REST API served by Gunicorn (`backend/`)
- **Hosting:** Render (free) — a Web Service for the API and a Static Site for the app

## What works, honestly

Fetchly only uses official APIs and public files. It does not scrape platforms or get around
logins, privacy settings or DRM.

| Source | What you get |
| --- | --- |
| **Direct media links** (`.mp4`, `.mov`, `.webm`, `.mp3`, `.m4a`, `.wav`, `.jpg`, `.png`, `.webp`…) | Download original file; MP3 extraction from video/audio |
| **Instagram** | Posts, reels and carousels from **your own** Business/Creator accounts (linked to a Facebook Page you manage), after connecting Meta. Carousels download individually or as a ZIP. |
| **Facebook** | Videos, reels and photos posted by **Pages you manage**, after connecting Meta |
| **YouTube** | Recognised and previewed (title/thumbnail via official oEmbed). No download — YouTube's API doesn't offer one, even for your own uploads. |
| **TikTok** | Recognised and previewed via official oEmbed. No download — the official API doesn't provide files. |
| **Douyin** | Recognised. No download — no official public download API. |

Other people's Instagram/Facebook posts, private content, and personal (non-Business/Creator)
Instagram accounts are not supported.

## Project structure

```
media-downloader/
├── backend/
│   ├── app.py                  Flask app factory, CORS, errors, security headers
│   ├── config.py               All settings from environment variables
│   ├── extensions.py           Rate limiter
│   ├── requirements.txt
│   ├── .env.example
│   ├── routes/
│   │   ├── api.py              /api/health, /api/platforms, /api/detect, /api/analyze, /api/download
│   │   └── auth.py             /auth/meta/login, /callback, /me, /logout
│   └── services/
│       ├── netguard.py         SSRF-safe HTTP (public IPs only, safe redirects, timeouts)
│       ├── downloader.py       Streaming + MP3 conversion with temp-file cleanup
│       ├── tokens.py           Signed download tickets, encrypted Meta sessions
│       ├── errors.py
│       └── platforms/          One module per integration
│           ├── base.py         Shared model: items, formats, filenames
│           ├── direct.py       Direct media links
│           ├── meta.py         Instagram + Facebook (Graph API)
│           └── unsupported.py  YouTube, TikTok, Douyin (detect + preview only)
└── frontend/
    ├── index.html              iOS standalone meta tags
    ├── vite.config.js          PWA manifest + service worker (vite-plugin-pwa)
    ├── public/icons/           App icons (192, 512, maskable, Apple touch)
    └── src/
        ├── App.jsx             Tab shell: Home, Downloads, History, Settings
        ├── screens/            One file per tab
        ├── components/         MediaPreview (formats, photo grid, ZIP), Notice, Toast…
        └── lib/                API client, download manager, storage, saving/sharing
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Health check (used by Render) and server limits |
| GET | `/api/platforms` | Each platform's availability and why |
| POST | `/api/detect` | `{url}` → which platform it is |
| POST | `/api/analyze` | `{url}` → title, thumbnail, items, formats, sizes, signed download tickets |
| GET | `/api/download?t=…` | Streams the file (signed ticket, valid 1 hour) |
| GET | `/auth/meta/login` | Starts Facebook Login |
| GET | `/auth/meta/me` | Connected Meta account and Pages |
| POST | `/auth/meta/logout` | Revokes the app's Meta permissions |

Errors always look like `{ "ok": false, "error": "<code>", "message": "<plain English>" }`.

## Environment variables

### Backend (Render Web Service)

| Variable | Required | Example / default | Notes |
| --- | --- | --- | --- |
| `ALLOWED_ORIGINS` | yes | `https://fetchly-app.onrender.com` | Comma-separated frontend origins allowed by CORS |
| `FRONTEND_URL` | yes | `https://fetchly-app.onrender.com` | Where Meta login sends users back |
| `BACKEND_URL` | yes | `https://fetchly-api.onrender.com` | Used to build the Meta redirect URI |
| `SECRET_KEY` | yes | long random string | Signs download tickets, encrypts Meta sessions. Render can generate it. |
| `META_APP_ID` | for IG/FB | | From developers.facebook.com |
| `META_APP_SECRET` | for IG/FB | | Secret — set only in Render, never in code |
| `META_GRAPH_VERSION` | no | `v21.0` | |
| `MAX_DOWNLOAD_MB` | no | `200` | Largest file streamed |
| `MAX_CONVERT_MB` | no | `150` | Largest file converted to MP3 |
| `REQUEST_TIMEOUT` | no | `20` | Seconds |
| `RATE_LIMIT_DEFAULT` | no | `120 per hour` | Per IP |
| `RATE_LIMIT_DOWNLOAD` | no | `30 per hour` | Per IP |
| `PYTHON_VERSION` | no | `3.12.8` | Render runtime |

### Frontend (Render Static Site, set at build time)

| Variable | Example |
| --- | --- |
| `VITE_API_URL` | `https://fetchly-api.onrender.com` |

## Run locally

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit; export the values or use your shell's dotenv
python app.py          # http://localhost:5000

# Frontend (second terminal)
cd frontend
npm install
VITE_API_URL=http://localhost:5000 npm run dev   # http://localhost:5173
```

## Deploy (Render, free tier)

**Backend — Web Service**
- Runtime: Python 3, Root: repository root
- Build: `pip install -r backend/requirements.txt`
- Start: `gunicorn --chdir backend app:app --worker-class gthread --workers 1 --threads 8 --timeout 180`
- Health check path: `/api/health`
- Set the backend environment variables above

**Frontend — Static Site**
- Build: `cd frontend && npm ci && npm run build`
- Publish directory: `frontend/dist`
- Env: `VITE_API_URL=<backend URL>`
- Rewrite rule: `/*` → `/index.html`

Both redeploy automatically when you push to `main`.

## Enabling Instagram & Facebook (optional)

1. Go to <https://developers.facebook.com/apps> → **Create app** → use case **Other** → type **Business**.
2. Add the **Facebook Login for Business** product. Under its settings, add this Valid OAuth Redirect URI:
   `https://<your-backend>.onrender.com/auth/meta/callback`
3. In **App settings → Basic**, copy the **App ID** and **App Secret**.
4. In Render → backend service → **Environment**, set `META_APP_ID` and `META_APP_SECRET`. It redeploys.
5. In the app, open **Settings → Connect with Facebook**.

While the Meta app is in **Development mode**, only you (and people you add as testers) can log in —
that's fine for personal use. Letting the public connect requires Meta App Review for
`pages_show_list`, `pages_read_engagement` and `instagram_basic`.

Your Instagram account must be a **Business or Creator** account linked to a Facebook Page you manage.

## Installing the app (PWA)

- **Android (Chrome):** open the site → menu (⋮) → **Install app**. It opens full-screen with its own icon
  and splash screen. You can also share a link from another app straight into Fetchly.
- **iPhone/iPad (Safari):** open the site → **Share** → **Add to Home Screen** → **Add**. It opens without
  Safari's address bar.
- **Saving on iPhone:** iOS doesn't let web apps write straight to Photos. Fetchly opens the share sheet —
  choose **Save Video** / **Save Image**, or **Save to Files**. Very large files may hit Safari memory limits.

## Security

- Server-side URL validation and SSRF protection: only `http`/`https`, ports 80/443, no embedded credentials,
  every resolved address must be public (blocks localhost, private ranges, link-local/cloud metadata,
  reserved, multicast); redirects are followed manually and re-validated each hop.
- Only recognised integrations: unknown sites must serve an actual media file, otherwise they're rejected.
- Downloads use signed, expiring tickets — the download endpoint can't be used as an open proxy.
- Meta tokens are encrypted with `SECRET_KEY` before reaching the browser; secrets live only in Render.
- File size limits, request timeouts, per-IP rate limiting, strict CORS, `nosniff`/`DENY` frame headers.
- Nothing is stored permanently: files stream through; MP3 conversion uses a private temp folder deleted
  when the response finishes (stale folders are swept after an hour).

## Free-tier limits (Render)

- The API **sleeps after 15 minutes idle**; the first request after that takes ~30–60 s. The app shows a
  "waking up" message.
- 512 MB RAM and shared CPU — MP3 conversion of big files is slow; that's why it's capped at 150 MB.
- Monthly free bandwidth and build minutes are limited; every download passes through the server, so
  heavy use counts against bandwidth. Check your Render dashboard for current numbers.
- In-memory rate limits reset when the service restarts.
