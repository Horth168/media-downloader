# Fetchly — Media Saver PWA

An installable web app for saving videos, audio and photos **you own or are allowed to download**.
Paste a link, see what's available, and save it as MP4, MP3 or original-quality photos.

- **Frontend:** React + Vite + Tailwind CSS + Lucide icons, installable PWA (`frontend/`)
- **Backend:** Python Flask REST API served by Gunicorn (`backend/`)
- **Hosting:** Render (free) — a Web Service for the API and a Static Site for the app

## What works

Platform media is fetched with [yt-dlp](https://github.com/yt-dlp/yt-dlp), which reads the platforms' public
web pages (not their official APIs). Platforms change often and sometimes block servers, so a link that fails
may work later. yt-dlp is upgraded on every deploy.

| Source | What you get |
| --- | --- |
| **TikTok** | Videos (MP4 up to 1080p, MP3), photo posts (each photo or all as ZIP) plus the post's sound |
| **Douyin** | Videos (no-watermark MP4, MP3) and photo posts |
| **Instagram** | Public reels, videos and video carousels |
| **Facebook** | Public videos and reels, including `/share/` and `fb.watch` links |
| **YouTube** | Videos and Shorts at 1080p / 720p / 480p, or MP3 |
| **Direct media links** | Any `.mp4`, `.mov`, `.webm`, `.mp3`, `.m4a`, `.jpg`, `.png`, `.webp`… file; MP3 extraction |

Not possible: private posts, posts that need a login the server doesn't have, and DRM-protected video.
Only save and reuse media you have the right to — downloading can be against a platform's terms of service.

### When a platform blocks the server

YouTube ("confirm you're not a bot") and Instagram ("login required") often block cloud servers. You can give
yt-dlp browser cookies so requests look like a signed-in browser:

1. Install a "Get cookies.txt LOCALLY" extension in Chrome, sign in to the site (a spare account is safer —
   platforms can restrict accounts used for downloading), and export `cookies.txt` for that site.
2. In Render → **fetchly-api** → **Environment**, add `YTDLP_COOKIES` and paste the whole file's contents.
3. Save. Cookies expire, so repeat when blocks return.

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
│   │   └── api.py              /api/health, /api/platforms, /api/detect, /api/analyze, /api/download
│   └── services/
│       ├── netguard.py         SSRF-safe HTTP (public IPs only, safe redirects, timeouts)
│       ├── downloader.py       Streaming, yt-dlp downloads, MP3 conversion, temp-file cleanup
│       ├── tokens.py           Signed download tickets
│       ├── errors.py
│       └── platforms/          One module per integration
│           ├── base.py         Shared model: items, formats, filenames
│           ├── direct.py       Direct media links
│           └── ytdlp.py        TikTok, Douyin, Instagram, Facebook, YouTube (yt-dlp + page readers)
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

Errors always look like `{ "ok": false, "error": "<code>", "message": "<plain English>" }`.

## Environment variables

### Backend (Render Web Service)

| Variable | Required | Example / default | Notes |
| --- | --- | --- | --- |
| `ALLOWED_ORIGINS` | yes | `https://fetchly-app.onrender.com` | Comma-separated frontend origins allowed by CORS |
| `SECRET_KEY` | yes | long random string | Signs download tickets |
| `YTDLP_COOKIES` | no | contents of cookies.txt | Helps when YouTube/Instagram block the server |
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

## Installing the app (PWA)

- **Android (Chrome):** open the site → menu (⋮) → **Install app**. It opens full-screen with its own icon
  and splash screen. You can also share a link from TikTok/YouTube/etc. straight into Fetchly.
- **iPhone/iPad (Safari):** open the site → **Share** → **Add to Home Screen** → **Add**. It opens without
  Safari's address bar.
- **Saving on iPhone:** iOS doesn't let web apps write straight to Photos. Fetchly opens the share sheet —
  choose **Save Video** / **Save Image**, or **Save to Files**. Very large files may hit Safari memory limits.

## Security

- Server-side URL validation and SSRF protection: only `http`/`https`, ports 80/443, no embedded credentials,
  every resolved address must be public (blocks localhost, private ranges, link-local/cloud metadata,
  reserved, multicast); redirects are followed manually and re-validated each hop.
- Only recognised integrations: yt-dlp runs with just the five platform extractors enabled (its generic
  extractor is off), and unknown sites must serve an actual media file, otherwise they're rejected.
- Downloads use signed, expiring tickets — the download endpoint can't be used as an open proxy.
- Secrets live only in Render environment variables.
- File size limits, request timeouts, per-IP rate limiting, strict CORS, `nosniff`/`DENY` frame headers.
- Nothing is stored permanently: direct files stream through; yt-dlp downloads and MP3 conversion use a
  private temp folder deleted when the response finishes (stale folders are swept after an hour).

## Free-tier limits (Render)

- The API **sleeps after 15 minutes idle**; the first request after that takes ~30–60 s. The app shows a
  "waking up" message.
- 512 MB RAM and shared CPU — platform downloads are fetched to the server first, so long or 1080p videos
  take a while before the progress bar starts. MP3 conversion is capped at 150 MB.
- Monthly free bandwidth and build minutes are limited; every download passes through the server, so
  heavy use counts against bandwidth. Check your Render dashboard for current numbers.
- In-memory rate limits reset when the service restarts.
