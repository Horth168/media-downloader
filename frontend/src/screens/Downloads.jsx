import { CheckCircle2, CircleAlert, Download, RotateCw, Trash2, X } from 'lucide-react'
import PlatformMark from '../components/PlatformMark'
import { useApp } from '../lib/AppContext'
import { formatBytes } from '../lib/platforms'

export default function Downloads({ go }) {
  const { jobs, clearFinished } = useApp()
  const finished = jobs.some((j) => ['done', 'failed', 'cancelled'].includes(j.status))

  return (
    <div className="space-y-5 pt-3">
      <header className="flex items-center justify-between">
        <h1 className="text-[26px] font-extrabold tracking-tight">Downloads</h1>
        {finished && (
          <button onClick={clearFinished} className="btn-ghost focus-ring text-sm text-muted">
            <Trash2 size={16} /> Clear finished
          </button>
        )}
      </header>

      {jobs.length === 0 ? (
        <div className="rounded-[22px] bg-charcoal px-6 py-12 text-center">
          <Download size={30} className="mx-auto text-muted" />
          <p className="mt-3 font-bold">Nothing downloading</p>
          <p className="mt-1 text-sm text-muted">Paste a link on Home to start a download.</p>
          <button onClick={() => go('home')} className="btn-primary focus-ring mx-auto mt-5">Paste a link</button>
        </div>
      ) : (
        <ul className="space-y-2.5">
          {jobs.map((j) => <JobRow key={j.id} job={j} />)}
        </ul>
      )}
      <p className="px-1 text-[12.5px] leading-relaxed text-muted">
        Downloads in progress stop if you close the app. Finished files are saved to your device, not kept on our server.
      </p>
    </div>
  )
}

function JobRow({ job }) {
  const { cancel, retry, dismiss } = useApp()
  const active = ['queued', 'downloading', 'saving'].includes(job.status)
  const pct = job.total ? Math.min(100, Math.round((job.loaded / job.total) * 100)) : null
  const isZip = job.kind === 'zip'

  let line
  if (job.status === 'queued') line = 'Starting…'
  else if (job.status === 'downloading') {
    line = isZip
      ? `${job.loaded} of ${job.total} files`
      : pct != null ? `${formatBytes(job.loaded)} of ${formatBytes(job.total)}` : `${formatBytes(job.loaded) || '0 B'} downloaded`
  } else if (job.status === 'saving') line = isZip ? 'Building ZIP…' : 'Saving to your device…'
  else if (job.status === 'done') line = `${formatBytes(job.size)}, ${job.savedVia === 'shared' ? 'shared' : 'saved'}`
  else if (job.status === 'cancelled') line = 'Cancelled'
  else line = job.error

  return (
    <li className="rounded-[20px] bg-charcoal p-3.5">
      <div className="flex items-center gap-3">
        <PlatformMark id={job.platform} size={38} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[15px] font-bold">{job.filename}</p>
          <p className={`truncate text-[12.5px] ${job.status === 'failed' ? 'text-bad' : 'text-muted'}`}>
            {job.format}: {line}
          </p>
        </div>
        {job.status === 'done' && <CheckCircle2 size={22} className="text-ok" aria-label="Done" />}
        {job.status === 'failed' && <CircleAlert size={22} className="text-bad" aria-label="Failed" />}
        {active && job.status !== 'saving' && (
          <button onClick={() => cancel(job.id)} className="btn-ghost focus-ring !px-2.5" aria-label="Cancel download"><X size={19} /></button>
        )}
        {(job.status === 'failed' || job.status === 'cancelled') && (
          <button onClick={() => retry(job.id)} className="btn-ghost focus-ring bg-white/5 text-sm"><RotateCw size={16} /> Retry</button>
        )}
        {!active && (
          <button onClick={() => dismiss(job.id)} className="btn-ghost focus-ring !px-2 text-muted" aria-label="Remove from list"><X size={17} /></button>
        )}
      </div>
      {active && (
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-graphite" role="progressbar"
             aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct ?? undefined}>
          {pct != null && job.status === 'downloading'
            ? <div className="h-full rounded-full bg-gradient-to-r from-violet to-azure transition-[width] duration-200" style={{ width: `${pct}%` }} />
            : <div className="shimmer h-full w-full" />}
        </div>
      )}
    </li>
  )
}
