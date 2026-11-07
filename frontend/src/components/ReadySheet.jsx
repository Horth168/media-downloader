import { Download, Film, Image as ImageIcon, Music, Share } from 'lucide-react'
import { useApp } from '../lib/AppContext'
import { formatBytes } from '../lib/platforms'

// Shown on iPhone when a download finishes. The tap on "Save to Photos" is what lets
// iOS open the share sheet, where "Save Video" / "Save Image" puts the file in Photos.
export default function ReadySheet() {
  const { readyJob, saveReady, dismissReady } = useApp()
  if (!readyJob) return null
  const name = readyJob.filename || ''
  const isVideo = /\.(mp4|mov|m4v)$/i.test(name)
  const isImage = /\.(jpe?g|png|webp|heic)$/i.test(name)
  const isZip = /\.zip$/i.test(name)
  const Icon = isVideo ? Film : isImage ? ImageIcon : isZip ? Download : Music
  const action = isVideo || isImage ? 'Save to Photos' : 'Save to Files'
  const hint = isVideo
    ? 'Next, tap “Save Video” at the top of the share menu.'
    : isImage
      ? 'Next, tap “Save Image” at the top of the share menu.'
      : 'Next, tap “Save to Files” in the share menu.'

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 backdrop-blur-sm" role="dialog"
         aria-modal="true" aria-labelledby="ready-h" onClick={dismissReady}>
      <div className="sheet-in safe-bottom w-full max-w-[480px] rounded-t-[28px] border-t border-line bg-charcoal px-5 pb-4 pt-3"
           onClick={(e) => e.stopPropagation()}>
        <div className="mx-auto mb-4 h-1.5 w-10 rounded-full bg-line" />
        <div className="flex items-center gap-3">
          {readyJob.thumbnail
            ? <img src={readyJob.thumbnail} alt="" referrerPolicy="no-referrer" className="h-14 w-14 rounded-2xl bg-graphite object-cover" />
            : <span className="grid h-14 w-14 place-items-center rounded-2xl bg-graphite text-[#A995FF]"><Icon size={24} /></span>}
          <div className="min-w-0">
            <h2 id="ready-h" className="text-[17px] font-bold">Download finished</h2>
            <p className="truncate text-[13px] text-muted">{name}, {formatBytes(readyJob.size)}</p>
          </div>
        </div>
        <button onClick={() => saveReady(readyJob.id)} className="btn-primary focus-ring mt-5 w-full text-[17px]" autoFocus>
          <Share size={19} strokeWidth={2.4} /> {action}
        </button>
        <p className="mt-2.5 text-center text-[13px] text-muted">{hint}</p>
        <button onClick={dismissReady} className="btn-ghost focus-ring mt-2 w-full text-muted">Later</button>
      </div>
    </div>
  )
}
