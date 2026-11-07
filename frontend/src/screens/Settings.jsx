import { useEffect, useState } from 'react'
import { ExternalLink, LogOut, Server, Smartphone } from 'lucide-react'
import PlatformMark from '../components/PlatformMark'
import { API_BASE, api, getMetaSession, setMetaSession } from '../lib/api'
import { useApp } from '../lib/AppContext'
import { isIOS, isStandalone } from '../lib/platforms'

function Toggle({ label, hint, checked, onChange }) {
  return (
    <label className="flex cursor-pointer items-center gap-4 px-4 py-3.5">
      <span className="flex-1">
        <span className="block text-[15px] font-semibold">{label}</span>
        {hint && <span className="mt-0.5 block text-[12.5px] leading-snug text-muted">{hint}</span>}
      </span>
      <input type="checkbox" className="peer sr-only" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="relative h-7 w-12 shrink-0 rounded-full bg-graphite transition-colors peer-checked:bg-violet peer-focus-visible:ring-2 peer-focus-visible:ring-violet/80 after:absolute after:left-1 after:top-1 after:h-5 after:w-5 after:rounded-full after:bg-white after:transition-transform peer-checked:after:translate-x-5" />
    </label>
  )
}

function Group({ title, children }) {
  return (
    <section className="space-y-2">
      <h2 className="px-1 text-[15px] font-bold">{title}</h2>
      <div className="divide-y divide-line/60 overflow-hidden rounded-[22px] bg-charcoal">{children}</div>
    </section>
  )
}

export default function Settings({ params }) {
  const { prefs, setPrefs, notify } = useApp()
  const [health, setHealth] = useState({ state: 'checking' })
  const [meta, setMeta] = useState({ state: getMetaSession() ? 'loading' : 'out' })

  // Return from Meta login: #/settings?meta_session=... or ?meta_error=...
  useEffect(() => {
    const s = params.get('meta_session')
    const err = params.get('meta_error')
    if (s || err) {
      if (s) { setMetaSession(s); notify('Meta account connected.', 'ok') }
      if (err) notify(err, 'bad')
      window.history.replaceState(null, '', window.location.pathname + '#/settings')
      loadMeta()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params])

  useEffect(() => {
    api.health().then((d) => setHealth({ state: 'ok', ...d })).catch((e) => setHealth({ state: 'down', message: e.message }))
    if (getMetaSession()) loadMeta()
  }, [])

  function loadMeta() {
    if (!getMetaSession()) return setMeta({ state: 'out' })
    setMeta({ state: 'loading' })
    api.metaMe().then((d) => setMeta({ state: 'in', ...d })).catch((e) => setMeta({ state: 'out', error: e.message }))
  }

  async function logout() {
    try { await api.metaLogout() } catch { /* forget locally anyway */ }
    setMetaSession(null)
    setMeta({ state: 'out' })
    notify('Meta account disconnected.')
  }

  const metaReady = health.state === 'ok' && health.meta_login

  return (
    <div className="space-y-7 pt-3">
      <h1 className="text-[26px] font-extrabold tracking-tight">Settings</h1>

      <Group title="Downloads">
        <div className="px-4 py-3.5">
          <p className="text-[15px] font-semibold">Default format</p>
          <div className="mt-2 flex gap-1 rounded-2xl bg-ink/60 p-1" role="radiogroup" aria-label="Default format">
            {[['mp4', 'MP4'], ['mp3', 'MP3'], ['photo', 'Photos']].map(([id, label]) => (
              <button key={id} role="radio" aria-checked={prefs.defaultFormat === id} onClick={() => setPrefs({ defaultFormat: id })}
                      className={`focus-ring h-10 flex-1 rounded-xl text-sm font-bold transition-colors ${prefs.defaultFormat === id ? 'bg-graphite text-fg' : 'text-muted'}`}>
                {label}
              </button>
            ))}
          </div>
        </div>
        <Toggle label="Analyze when I paste" hint="Look up the link as soon as you paste it." checked={prefs.autoAnalyze} onChange={(v) => setPrefs({ autoAnalyze: v })} />
        <Toggle label="Use the share sheet on iPhone" hint="Lets you pick Save Video or Save Image to put files in Photos." checked={prefs.iosShareSheet} onChange={(v) => setPrefs({ iosShareSheet: v })} />
        <Toggle label="Keep download history" hint="Stored only on this device." checked={prefs.keepHistory} onChange={(v) => setPrefs({ keepHistory: v })} />
      </Group>

      <Group title="Instagram and Facebook">
        <div className="space-y-3 px-4 py-4">
          <div className="flex -space-x-1.5">
            <PlatformMark id="instagram" size={32} /><PlatformMark id="facebook" size={32} />
          </div>
          {meta.state === 'in' ? (
            <>
              <p className="text-[15px] font-semibold">Connected as {meta.name}</p>
              {meta.pages?.length ? (
                <ul className="space-y-1 text-[13px] text-muted">
                  {meta.pages.map((p) => <li key={p.id}>{p.name}{p.instagram ? `, Instagram @${p.instagram}` : ', no Instagram linked'}</li>)}
                </ul>
              ) : <p className="text-[13px] text-muted">No Facebook Pages found on this account, so there&rsquo;s nothing to download yet.</p>}
              <button onClick={logout} className="btn-ghost focus-ring bg-white/5 text-sm"><LogOut size={16} /> Disconnect</button>
            </>
          ) : meta.state === 'loading' ? (
            <p className="text-sm text-muted">Checking your Meta connection…</p>
          ) : (
            <>
              <p className="text-sm leading-relaxed text-muted">
                Connect Meta to download posts from Instagram Business/Creator accounts and Facebook Pages you manage.
                Other people&rsquo;s posts can&rsquo;t be downloaded.
              </p>
              {meta.error && <p className="text-sm text-bad">{meta.error}</p>}
              {metaReady ? (
                <a href={api.metaLoginUrl()} className="btn-primary focus-ring w-full">Connect with Facebook</a>
              ) : (
                <p className="rounded-xl bg-graphite/70 px-3 py-2.5 text-[13px] text-muted">
                  {health.state === 'checking' ? 'Checking server…' : 'Meta login isn’t set up on the server yet.'}
                </p>
              )}
            </>
          )}
        </div>
      </Group>

      <Group title="App">
        <div className="flex items-center gap-3 px-4 py-3.5">
          <Server size={19} className="text-muted" />
          <div className="min-w-0 flex-1">
            <p className="text-[15px] font-semibold">Server</p>
            <p className="truncate text-[12.5px] text-muted">{API_BASE.replace(/^https?:\/\//, '')}</p>
          </div>
          <span className={`text-[13px] font-bold ${health.state === 'ok' ? 'text-ok' : health.state === 'down' ? 'text-bad' : 'text-muted'}`}>
            {health.state === 'ok' ? 'Online' : health.state === 'down' ? 'Offline' : 'Checking'}
          </span>
        </div>
        {health.state === 'ok' && (
          <p className="px-4 py-3 text-[12.5px] leading-relaxed text-muted">
            Files up to {health.limits.max_download_mb} MB; MP3 conversion up to {health.limits.max_convert_mb} MB.
            The free server sleeps after 15 idle minutes, so the first request can take about a minute.
          </p>
        )}
        {!isStandalone() && (
          <div className="flex items-start gap-3 px-4 py-3.5">
            <Smartphone size={19} className="mt-0.5 text-muted" />
            <p className="text-[13px] leading-relaxed text-muted">
              {isIOS()
                ? 'Install: tap the Share button in Safari, then Add to Home Screen.'
                : 'Install: open your browser menu and choose Install app or Add to Home screen.'}
            </p>
          </div>
        )}
        <a href="https://github.com/Horth168/media-downloader" target="_blank" rel="noreferrer"
           className="focus-ring flex items-center gap-3 px-4 py-3.5 text-[15px] font-semibold">
          <span className="flex-1">Source code</span><ExternalLink size={17} className="text-muted" />
        </a>
      </Group>

      <p className="px-1 pb-2 text-[12.5px] leading-relaxed text-muted">
        Only download media you own or have permission to save. Fetchly uses official platform APIs and never gets
        around privacy settings, logins or copy protection.
      </p>
    </div>
  )
}
