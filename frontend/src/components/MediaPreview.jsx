import { useMemo, useState } from 'react'
import { Check, Download, FileArchive, Film, Music } from 'lucide-react'
import PlatformMark from './PlatformMark'
import { useApp } from '../lib/AppContext'
import { formatBytes } from '../lib/platforms'

export default function MediaPreview({ data, format, sourceUrl, go }) {
  const { media, platform } = data
  const photos = media.items.filter((i) => i.type === 'image')
  const isGallery = media.items.length > 1

  return (
    <article className="sheet-in overflow-hidden rounded-[22px] bg-charcoal">
      {!isGallery && media.thumbnail && (
        <img src={media.thumbnail} alt="" referrerPolicy="no-referrer"
             className="max-h-[320px] w-full bg-ink object-contain" />
      )}
      {!isGallery && !media.thumbnail && (
        <div className="grid aspect-[16/7] place-items-center bg-graphite text-muted">
          {media.kind === 'audio' ? <Music size={40} /> : <Film size={40} />}
        </div>
      )}
      <div className="flex items-start gap-3 p-4 pb-2">
        <PlatformMark id={platform.id} size={34} />
        <div className="min-w-0">
          <h2 className="line-clamp-2 text-[17px] font-bold leading-snug">{media.title}</h2>
          <p className="mt-0.5 truncate text-[13px] text-muted">
            {[platform.name, media.author, isGallery && `${media.items.length} items`].filter(Boolean).join(', ')}
          </p>
        </div>
      </div>
      {isGallery
        ? <Gallery media={media} platform={platform} sourceUrl={sourceUrl} go={go} />
        : <SingleItem item={media.items[0]} media={media} platform={platform} format={format} sourceUrl={sourceUrl} go={go} />}
      {format === 'photo' && photos.length === 0 && media.items[0]?.type !== 'image' && (
        <p className="px-4 pb-4 text-[13px] text-muted">This link has no photos — pick a video or audio format above.</p>
      )}
    </article>
  )
}

function SingleItem({ item, media, platform, format, sourceUrl, go }) {
  const { startDownload } = useApp()
  const initial = useMemo(() => {
    const want = format === 'photo' ? 'photo' : format
    return (item.formats.find((f) => f.id === want || f.id.startsWith(want + '-')) || item.formats[0])?.id
  }, [item, format])
  const [chosen, setChosen] = useState(initial)
  const f = item.formats.find((x) => x.id === chosen) || item.formats[0]

  function download() {
    startDownload({
      kind: 'file', title: media.title, platform: platform.id, thumbnail: media.thumbnail,
      format: f.label, filename: f.filename, sizeHint: f.size, sourceUrl,
      parts: [{ ticket: f.ticket, filename: f.filename }],
    })
    go('downloads')
  }

  return (
    <div className="space-y-3 p-4 pt-2">
      <fieldset>
        <legend className="sr-only">Choose a format</legend>
        <ul className="space-y-1.5">
          {item.formats.map((x) => {
            const on = x.id === chosen
            return (
              <li key={x.id}>
                <label className={`flex cursor-pointer items-center gap-3 rounded-2xl px-3.5 py-3 transition-colors ${on ? 'bg-violet/15 ring-1 ring-violet/60' : 'bg-graphite/60 hover:bg-graphite'}`}>
                  <input type="radio" name="fmt" value={x.id} checked={on} onChange={() => setChosen(x.id)} className="sr-only" />
                  <span className={`grid h-5 w-5 place-items-center rounded-full border-2 ${on ? 'border-violet bg-violet' : 'border-muted/60'}`}>
                    {on && <Check size={12} strokeWidth={3.5} className="text-white" />}
                  </span>
                  <span className="flex-1">
                    <span className="block text-[15px] font-bold">{x.label}</span>
                    <span className="block text-[12.5px] text-muted">{x.quality}</span>
                  </span>
                  <span className="text-[13px] font-semibold tabular-nums text-muted">
                    {formatBytes(x.size) ? `~${formatBytes(x.size)}` : ''}
                  </span>
                </label>
              </li>
            )
          })}
        </ul>
      </fieldset>
      <button onClick={download} className="btn-primary focus-ring w-full">
        <Download size={19} strokeWidth={2.4} /> Download {f.label.split(' ')[0]}{/^\d/.test(f.quality) ? ` ${f.quality}` : ''}
      </button>
    </div>
  )
}

function Gallery({ media, platform, sourceUrl, go }) {
  const { startDownload } = useApp()
  const [sel, setSel] = useState(() => new Set(media.items.map((i) => i.id)))
  const all = sel.size === media.items.length
  const toggle = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  const primary = (item) => item.formats[0]

  function one(item) {
    const f = primary(item)
    startDownload({
      kind: 'file', title: media.title, platform: platform.id, thumbnail: item.thumbnail,
      format: f.label, filename: f.filename, sizeHint: f.size, sourceUrl,
      parts: [{ ticket: f.ticket, filename: f.filename }],
    })
  }
  function zip() {
    const items = media.items.filter((i) => sel.has(i.id))
    if (!items.length) return
    startDownload({
      kind: 'zip', title: media.title, platform: platform.id, thumbnail: media.thumbnail,
      format: `ZIP (${items.length} files)`, filename: `${media.items[0].formats[0].filename.replace(/_1\.\w+$/, '').replace(/\.\w+$/, '')}.zip`,
      sourceUrl, parts: items.map((i) => ({ ticket: primary(i).ticket, filename: primary(i).filename })),
    })
    go('downloads')
  }

  return (
    <div className="space-y-3 p-4 pt-2">
      <div className="flex items-center justify-between">
        <p className="text-[13px] font-semibold text-muted">{sel.size} of {media.items.length} selected, original quality</p>
        <button onClick={() => setSel(all ? new Set() : new Set(media.items.map((i) => i.id)))}
                className="focus-ring rounded text-sm font-semibold text-[#A995FF]">
          {all ? 'Select none' : 'Select all'}
        </button>
      </div>
      <ul className="grid grid-cols-3 gap-1.5">
        {media.items.map((item, idx) => {
          const on = sel.has(item.id)
          return (
            <li key={item.id} className="relative aspect-square overflow-hidden rounded-xl bg-graphite">
              <button onClick={() => toggle(item.id)} aria-pressed={on} aria-label={`Select item ${idx + 1}`}
                      className="focus-ring absolute inset-0">
                {item.thumbnail
                  ? <img src={item.thumbnail} alt="" referrerPolicy="no-referrer" loading="lazy" className={`h-full w-full object-cover transition ${on ? '' : 'opacity-40'}`} />
                  : <span className="grid h-full place-items-center text-muted"><Film size={26} /></span>}
              </button>
              <span className={`pointer-events-none absolute left-1.5 top-1.5 grid h-6 w-6 place-items-center rounded-full border-2 ${on ? 'border-violet bg-violet' : 'border-white/70 bg-black/30'}`}>
                {on && <Check size={13} strokeWidth={3.5} className="text-white" />}
              </span>
              {item.type === 'video' && <Film size={16} className="pointer-events-none absolute bottom-1.5 left-1.5 text-white drop-shadow" />}
              <button onClick={() => one(item)} aria-label={`Download item ${idx + 1}`}
                      className="focus-ring absolute bottom-1 right-1 grid h-8 w-8 place-items-center rounded-full bg-black/55 text-white backdrop-blur">
                <Download size={15} strokeWidth={2.5} />
              </button>
            </li>
          )
        })}
      </ul>
      <button onClick={zip} disabled={!sel.size} className="btn-primary focus-ring w-full">
        <FileArchive size={19} /> Download {sel.size === media.items.length ? 'all' : sel.size} as ZIP
      </button>
    </div>
  )
}
