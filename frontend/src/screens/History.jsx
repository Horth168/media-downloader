import { useState } from 'react'
import { Clock, Copy, Trash2 } from 'lucide-react'
import PlatformMark from '../components/PlatformMark'
import { useApp } from '../lib/AppContext'
import { formatBytes } from '../lib/platforms'

const when = (t) => {
  const d = new Date(t)
  const today = new Date()
  return d.toDateString() === today.toDateString()
    ? d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
    : d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

export function HistoryRow({ item, compact = false }) {
  const { removeHistory, notify } = useApp()
  async function copy() {
    try { await navigator.clipboard.writeText(item.sourceUrl); notify('Link copied.', 'ok') }
    catch { notify('Couldn’t copy — your browser blocked clipboard access.', 'bad') }
  }
  return (
    <li className="flex items-center gap-3 px-4 py-3">
      {item.thumbnail
        ? <img src={item.thumbnail} alt="" referrerPolicy="no-referrer" loading="lazy" className="h-11 w-11 shrink-0 rounded-xl bg-graphite object-cover" />
        : <PlatformMark id={item.platform} size={44} />}
      <div className="min-w-0 flex-1">
        <p className="truncate text-[15px] font-semibold">{item.filename}</p>
        <p className="truncate text-[12.5px] text-muted">{[item.format, formatBytes(item.size), when(item.at)].filter(Boolean).join(', ')}</p>
      </div>
      {!compact && item.sourceUrl && (
        <button onClick={copy} className="btn-ghost focus-ring !px-2 text-muted" aria-label="Copy original link"><Copy size={17} /></button>
      )}
      {!compact && (
        <button onClick={() => removeHistory(item.id)} className="btn-ghost focus-ring !px-2 text-muted" aria-label="Remove from history"><Trash2 size={17} /></button>
      )}
    </li>
  )
}

export default function History({ go }) {
  const { history, clearHistory, prefs } = useApp()
  const [confirm, setConfirm] = useState(false)

  return (
    <div className="space-y-5 pt-3">
      <header className="flex items-center justify-between">
        <h1 className="text-[26px] font-extrabold tracking-tight">History</h1>
        {history.length > 0 && (
          confirm ? (
            <div className="flex gap-1">
              <button onClick={() => setConfirm(false)} className="btn-ghost focus-ring text-sm">Keep</button>
              <button onClick={() => { clearHistory(); setConfirm(false) }} className="btn-ghost focus-ring bg-bad/15 text-sm text-bad">Clear history</button>
            </div>
          ) : (
            <button onClick={() => setConfirm(true)} className="btn-ghost focus-ring text-sm text-muted"><Trash2 size={16} /> Clear</button>
          )
        )}
      </header>

      {history.length === 0 ? (
        <div className="rounded-[22px] bg-charcoal px-6 py-12 text-center">
          <Clock size={30} className="mx-auto text-muted" />
          <p className="mt-3 font-bold">No downloads yet</p>
          <p className="mt-1 text-sm text-muted">
            {prefs.keepHistory ? 'Files you save will be listed here, on this device only.' : 'History is turned off in Settings.'}
          </p>
          <button onClick={() => go('home')} className="btn-primary focus-ring mx-auto mt-5">Paste a link</button>
        </div>
      ) : (
        <ul className="divide-y divide-line/60 overflow-hidden rounded-[22px] bg-charcoal">
          {history.map((h) => <HistoryRow key={h.id} item={h} />)}
        </ul>
      )}
    </div>
  )
}
