import { useEffect, useRef, useState } from 'react'
import { ClipboardPaste, Image as ImageIcon, Music, Video, X } from 'lucide-react'
import MediaPreview from '../components/MediaPreview'
import Notice from '../components/Notice'
import PlatformMark from '../components/PlatformMark'
import { HistoryRow } from './History'
import { api } from '../lib/api'
import { useApp } from '../lib/AppContext'
import { PLATFORMS, detectPlatform, extractUrl } from '../lib/platforms'

const FORMATS = [
  { id: 'mp4', label: 'MP4', icon: Video },
  { id: 'mp3', label: 'MP3', icon: Music },
  { id: 'photo', label: 'Photos', icon: ImageIcon },
]

export default function Home({ go, sharedText }) {
  const { prefs, history, notify } = useApp()
  const [text, setText] = useState(sharedText || '')
  const [format, setFormat] = useState(prefs.defaultFormat)
  const [state, setState] = useState({ phase: 'idle' }) // idle | loading | result | error
  const [statuses, setStatuses] = useState(null)
  const inputRef = useRef(null)
  const reqId = useRef(0)

  const url = extractUrl(text)
  const platformId = url.startsWith('http') ? detectPlatform(url) : null
  const ringColor = platformId ? PLATFORMS[platformId].color : '#7C5CFF'

  useEffect(() => {
    api.platforms().then((d) => setStatuses(Object.fromEntries(d.platforms.map((p) => [p.id, p])))).catch(() => {})
  }, [])

  useEffect(() => {
    if (sharedText && prefs.autoAnalyze) analyze(extractUrl(sharedText))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function analyze(target = url) {
    if (!target || !/^https?:\/\//i.test(target)) {
      setState({ phase: 'error', error: { code: 'invalid_url', message: 'Paste a full link that starts with https://' } })
      return
    }
    const id = ++reqId.current
    setState({ phase: 'loading', slow: false })
    const slowTimer = setTimeout(() => id === reqId.current && setState((s) => (s.phase === 'loading' ? { ...s, slow: true } : s)), 6000)
    try {
      const data = await api.analyze(target)
      if (id === reqId.current) setState({ phase: 'result', data, sourceUrl: target })
    } catch (e) {
      if (id === reqId.current) setState({ phase: 'error', error: e })
    } finally {
      clearTimeout(slowTimer)
    }
  }

  async function paste() {
    try {
      const clip = await navigator.clipboard.readText()
      if (!clip) return notify('Your clipboard is empty.')
      setText(clip)
      const u = extractUrl(clip)
      if (prefs.autoAnalyze && /^https?:\/\//i.test(u)) analyze(u)
    } catch {
      inputRef.current?.focus()
      notify('Clipboard access was blocked — long-press the box and choose Paste.')
    }
  }

  function clear() {
    reqId.current++
    setText('')
    setState({ phase: 'idle' })
    inputRef.current?.focus()
  }

  return (
    <div className="space-y-7 pt-3">
      <header className="flex items-center gap-3">
        <img src="/icons/icon-192.png" alt="" className="h-10 w-10 rounded-xl" />
        <div>
          <h1 className="text-[26px] font-extrabold leading-none tracking-tight">Fetchly</h1>
          <p className="mt-1 text-[13px] text-muted">Save media you own or are allowed to keep</p>
        </div>
      </header>

      <section aria-label="Paste a link" className="space-y-3">
        <form
          onSubmit={(e) => { e.preventDefault(); analyze() }}
          className="linkbox rounded-[22px] bg-charcoal p-2"
          style={{ '--ring': ringColor }}
        >
          <div className="flex items-center gap-2 pl-2">
            {platformId ? <PlatformMark id={platformId} size={32} /> : <span className="w-1" />}
            <label htmlFor="link" className="sr-only">Media link</label>
            <input
              id="link"
              ref={inputRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onPaste={(e) => {
                const u = extractUrl(e.clipboardData.getData('text'))
                if (prefs.autoAnalyze && /^https?:\/\//i.test(u)) setTimeout(() => analyze(u), 0)
              }}
              inputMode="url"
              autoComplete="off"
              autoCapitalize="off"
              spellCheck={false}
              enterKeyHint="go"
              placeholder="Paste a link here"
              className="h-14 min-w-0 flex-1 bg-transparent text-[17px] font-medium placeholder:text-muted/70 focus:outline-none"
            />
            {text ? (
              <button type="button" onClick={clear} className="btn-ghost focus-ring !min-h-[44px] !px-2.5" aria-label="Clear link">
                <X size={20} />
              </button>
            ) : (
              <button type="button" onClick={paste} className="btn-ghost focus-ring !min-h-[44px] bg-white/5 !px-3.5">
                <ClipboardPaste size={18} /> Paste
              </button>
            )}
          </div>
          <div className="mt-2 flex items-center gap-2">
            <div className="flex flex-1 gap-1 rounded-2xl bg-ink/60 p-1" role="radiogroup" aria-label="Format">
              {FORMATS.map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  type="button"
                  role="radio"
                  aria-checked={format === id}
                  onClick={() => setFormat(id)}
                  className={`focus-ring flex h-11 flex-1 items-center justify-center gap-1.5 rounded-xl text-sm font-bold transition-colors ${format === id ? 'bg-graphite text-fg' : 'text-muted hover:text-fg/80'}`}
                >
                  <Icon size={16} /> {label}
                </button>
              ))}
            </div>
            <button type="submit" className="btn-primary focus-ring" disabled={!text || state.phase === 'loading'}>
              {state.phase === 'loading' ? <span className="spinner" aria-label="Loading" /> : 'Get media'}
            </button>
          </div>
        </form>
        {platformId && (
          <p className="px-1 text-[13px] text-muted">
            Detected <span className="font-semibold text-fg">{PLATFORMS[platformId].name}</span>
          </p>
        )}
      </section>

      {state.phase === 'loading' && (
        <div className="sheet-in space-y-3 rounded-[22px] bg-charcoal p-4" aria-busy="true">
          <div className="shimmer aspect-video w-full rounded-2xl" />
          <div className="shimmer h-5 w-3/4 rounded-lg" />
          <div className="shimmer h-4 w-1/3 rounded-lg" />
          {state.slow && <p className="pt-1 text-sm text-muted">Still working — the free server sleeps when idle and can take up to a minute to wake up.</p>}
        </div>
      )}

      {state.phase === 'error' && (
        <ErrorNotice error={state.error} onRetry={() => analyze()} />
      )}

      {state.phase === 'result' && (
        <MediaPreview data={state.data} format={format} sourceUrl={state.sourceUrl} go={go} />
      )}

      {state.phase === 'idle' && (
        <>
          <section aria-labelledby="where-h">
            <h2 id="where-h" className="mb-3 text-[15px] font-bold">Where it works</h2>
            <ul className="divide-y divide-line/60 overflow-hidden rounded-[22px] bg-charcoal">
              {['tiktok', 'douyin', 'instagram', 'facebook', 'youtube', 'direct'].map((id) => {
                const s = statuses?.[id]
                const ok = s ? s.available : true
                return (
                  <li key={id} className="flex items-center gap-3 px-4 py-3">
                    <PlatformMark id={id} size={34} dim={!ok} />
                    <div className="min-w-0 flex-1">
                      <p className="text-[15px] font-semibold">{PLATFORMS[id].name}</p>
                      <p className="truncate text-[12.5px] text-muted">{STATUS_COPY[id](s)}</p>
                    </div>
                    <span className={`h-2 w-2 rounded-full ${ok ? 'bg-ok' : 'bg-muted/40'}`} aria-label={ok ? 'Available' : 'Not available'} />
                  </li>
                )
              })}
            </ul>
          </section>

          {history.length > 0 && (
            <section aria-labelledby="recent-h">
              <div className="mb-3 flex items-baseline justify-between">
                <h2 id="recent-h" className="text-[15px] font-bold">Recent downloads</h2>
                <button onClick={() => go('history')} className="focus-ring rounded text-sm font-semibold text-[#A995FF]">See all</button>
              </div>
              <ul className="divide-y divide-line/60 overflow-hidden rounded-[22px] bg-charcoal">
                {history.slice(0, 3).map((h) => <HistoryRow key={h.id} item={h} compact />)}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  )
}

const STATUS_COPY = {
  tiktok: () => 'Videos, photo posts and sounds',
  douyin: () => 'Videos and photo posts',
  instagram: () => 'Public reels, videos and carousels',
  facebook: () => 'Public videos and reels',
  youtube: () => 'Videos and Shorts up to 1080p, or MP3',
  direct: () => 'Links ending in .mp4, .mp3, .jpg and similar',
}

function ErrorNotice({ error, onRetry }) {
  const retryable = ['network', 'timeout', 'offline', 'unreachable', 'rate_limited', 'http_502', 'http_503', 'blocked_by_platform', 'login_required_platform', 'extract_failed', 'upstream_error'].includes(error.code)
  return (
    <Notice tone="bad" title={TITLES[error.code] || "Couldn't get that link"} action={retryable ? { label: 'Try again', onClick: onRetry } : null}>
      {error.message}
    </Notice>
  )
}

const TITLES = {
  invalid_url: 'Check the link',
  blocked_url: 'That link isn’t allowed',
  not_media: 'No media file at that link',
  private: 'That post is private',
  blocked_by_platform: 'The platform blocked the server',
  login_required_platform: 'The platform wants a login',
  extract_failed: 'Couldn\u2019t read that post',
  geo_blocked: 'Not available in the server\u2019s region',
  drm: 'Copy-protected video',
  forbidden: 'That file is private',
  not_found: 'Nothing found',
  rate_limited: 'Slow down a little',
  offline: 'You’re offline',
}
