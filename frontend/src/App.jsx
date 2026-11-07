import { useEffect, useState } from 'react'
import { Clock, Download, House, Settings as SettingsIcon } from 'lucide-react'
import Home from './screens/Home'
import Downloads from './screens/Downloads'
import History from './screens/History'
import Settings from './screens/Settings'
import Toast from './components/Toast'
import { useApp } from './lib/AppContext'

const TABS = [
  { id: 'home', label: 'Home', icon: House },
  { id: 'downloads', label: 'Downloads', icon: Download },
  { id: 'history', label: 'History', icon: Clock },
  { id: 'settings', label: 'Settings', icon: SettingsIcon },
]

function parseHash() {
  const raw = window.location.hash.replace(/^#\/?/, '')
  const [path, query = ''] = raw.split('?')
  const tab = TABS.some((t) => t.id === path) ? path : 'home'
  return { tab, params: new URLSearchParams(query) }
}

export default function App() {
  const [route, setRoute] = useState(parseHash)
  const { jobs } = useApp()
  const active = jobs.filter((j) => ['queued', 'downloading', 'saving'].includes(j.status)).length

  // Text shared into the installed app (Android share target) arrives as ?url= / ?text=
  const [sharedText] = useState(() => {
    const q = new URLSearchParams(window.location.search)
    const v = q.get('url') || q.get('text') || ''
    if (v) window.history.replaceState(null, '', window.location.pathname + window.location.hash)
    return v
  })

  useEffect(() => {
    const onHash = () => setRoute(parseHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const go = (tab) => {
    window.location.hash = `/${tab}`
    window.scrollTo({ top: 0 })
  }

  return (
    <div className="haze min-h-full">
      <div className="mx-auto flex min-h-[100dvh] max-w-[480px] flex-col">
        <main className="safe-top flex-1 px-4 pb-28">
          {route.tab === 'home' && <Home go={go} sharedText={sharedText} />}
          {route.tab === 'downloads' && <Downloads go={go} />}
          {route.tab === 'history' && <History go={go} />}
          {route.tab === 'settings' && <Settings params={route.params} />}
        </main>

        <nav
          className="safe-bottom fixed inset-x-0 bottom-0 z-30 border-t border-line/70 bg-ink/85 backdrop-blur-xl"
          aria-label="Main"
        >
          <ul className="mx-auto grid max-w-[480px] grid-cols-4">
            {TABS.map(({ id, label, icon: Icon }) => {
              const on = route.tab === id
              return (
                <li key={id}>
                  <button
                    onClick={() => go(id)}
                    aria-current={on ? 'page' : undefined}
                    className={`focus-ring relative flex w-full flex-col items-center gap-1 pb-1 pt-2.5 text-[11px] font-semibold transition-colors ${on ? 'text-fg' : 'text-muted hover:text-fg/80'}`}
                  >
                    <span className={`grid h-8 w-14 place-items-center rounded-full transition-colors ${on ? 'bg-violet/20' : ''}`}>
                      <Icon size={20} strokeWidth={on ? 2.4 : 2} className={on ? 'text-[#A995FF]' : ''} />
                    </span>
                    {label}
                    {id === 'downloads' && active > 0 && (
                      <span className="absolute right-[22%] top-1.5 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-azure px-1 text-[10px] font-bold text-white">
                        {active}
                      </span>
                    )}
                  </button>
                </li>
              )
            })}
          </ul>
        </nav>
        <Toast />
      </div>
    </div>
  )
}
