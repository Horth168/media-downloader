import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { api, ApiError } from './api'
import { canShareFile, saveBlob } from './save'
import { addHistory, clearHistory, loadHistory, loadPrefs, removeHistory, savePrefs } from './storage'

const Ctx = createContext(null)
export const useApp = () => useContext(Ctx)

let seq = 0
const newId = () => `${Date.now().toString(36)}-${(seq++).toString(36)}`

async function fetchBlob(ticket, signal, onProgress) {
  const res = await fetch(api.downloadUrl(ticket), { signal })
  if (!res.ok) {
    let msg = `Download failed (${res.status}).`
    try { msg = (await res.json()).message || msg } catch { /* not JSON */ }
    throw new ApiError('download_failed', msg, res.status)
  }
  const total = Number(res.headers.get('Content-Length')) || 0
  const type = res.headers.get('Content-Type') || 'application/octet-stream'
  if (!res.body || !res.body.getReader) {
    const b = await res.blob()
    onProgress(b.size, b.size)
    return b
  }
  const reader = res.body.getReader()
  const chunks = []
  let loaded = 0
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    chunks.push(value)
    loaded += value.length
    onProgress(loaded, total)
  }
  if (total && loaded < total) throw new ApiError('incomplete', 'The download was interrupted before it finished.')
  return new Blob(chunks, { type })
}

export function AppProvider({ children }) {
  const [prefs, setPrefsState] = useState(loadPrefs)
  const [history, setHistory] = useState(loadHistory)
  const [jobs, setJobs] = useState([])
  const [toast, setToast] = useState(null)
  const controllers = useRef(new Map())
  const blobs = useRef(new Map())
  const [readyId, setReadyId] = useState(null)

  const setPrefs = useCallback((patch) => {
    setPrefsState((p) => { const n = { ...p, ...patch }; savePrefs(n); return n })
  }, [])

  const notify = useCallback((message, tone = 'info') => {
    setToast({ message, tone, id: newId() })
  }, [])
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 3200)
    return () => clearTimeout(t)
  }, [toast])

  const jobsRef = useRef(jobs)
  jobsRef.current = jobs
  const patchJob = (id, patch) => setJobs((js) => js.map((j) => (j.id === id ? { ...j, ...patch } : j)))

  const finish = useCallback((job, size, how) => {
    patchJob(job.id, { status: 'done', size, savedVia: how })
    notify(how === 'shared' ? 'Saved' : how === 'cancelled' ? 'Not saved. Tap Save again any time.' : `Saved ${job.filename}`,
      how === 'cancelled' ? 'info' : 'ok')
    if (prefs.keepHistory && how !== 'cancelled') {
      setHistory(addHistory({
        id: job.id, title: job.title, platform: job.platform, format: job.format,
        filename: job.filename, size, thumbnail: job.thumbnail, sourceUrl: job.sourceUrl, at: Date.now(),
      }))
    }
  }, [notify, prefs.keepHistory])

  const run = useCallback(async (job) => {
    const ctrl = new AbortController()
    controllers.current.set(job.id, ctrl)
    patchJob(job.id, { status: 'downloading', loaded: 0, total: 0, error: null })
    try {
      let blob, filename = job.filename
      if (job.kind === 'zip') {
        const { default: JSZip } = await import('jszip')
        const zip = new JSZip()
        let i = 0
        for (const part of job.parts) {
          const b = await fetchBlob(part.ticket, ctrl.signal, () => {})
          zip.file(part.filename, b)
          i++
          patchJob(job.id, { loaded: i, total: job.parts.length })
        }
        patchJob(job.id, { status: 'saving' })
        blob = await zip.generateAsync({ type: 'blob', compression: 'STORE' })
      } else {
        blob = await fetchBlob(job.parts[0].ticket, ctrl.signal, (loaded, total) =>
          patchJob(job.id, { loaded, total }))
        patchJob(job.id, { status: 'saving' })
      }
      if (prefs.iosShareSheet && canShareFile(blob, filename)) {
        // iOS only opens the share sheet straight after a tap, and a long download has
        // used that up. Hold the file and let the person tap "Save to Photos".
        blobs.current.set(job.id, blob)
        patchJob(job.id, { status: 'ready', size: blob.size })
        setReadyId(job.id)
      } else {
        const how = await saveBlob(blob, filename, { preferShare: false })
        finish(job, blob.size, how)
      }
    } catch (e) {
      if (e.name === 'AbortError') {
        patchJob(job.id, { status: 'cancelled', error: null })
      } else {
        patchJob(job.id, { status: 'failed', error: e.message || 'Download failed.' })
        notify(e.message || 'Download failed.', 'bad')
      }
    } finally {
      controllers.current.delete(job.id)
    }
  }, [notify, finish, prefs.iosShareSheet])

  // Called from a tap, so iOS allows the share sheet ("Save Video" / "Save Image").
  const saveReady = useCallback(async (id) => {
    const job = jobsRef.current.find((j) => j.id === id)
    const blob = blobs.current.get(id)
    setReadyId(null)
    if (!job || !blob) return
    const how = await saveBlob(blob, job.filename, { preferShare: true })
    if (how === 'cancelled') {
      patchJob(id, { status: 'ready' })
      notify('Not saved. Tap Save to Photos again any time.')
      return
    }
    blobs.current.delete(id)
    finish(job, blob.size, how)
  }, [finish, notify])

  const startDownload = useCallback((spec) => {
    const job = { id: newId(), status: 'queued', loaded: 0, total: 0, createdAt: Date.now(), ...spec }
    setJobs((js) => [job, ...js])
    run(job)
    return job.id
  }, [run])

  const cancel = useCallback((id) => controllers.current.get(id)?.abort(), [])
  const retry = useCallback((id) => {
    const job = jobsRef.current.find((j) => j.id === id)
    if (job && !controllers.current.has(id)) run(job)
  }, [run])
  const dismiss = useCallback((id) => { blobs.current.delete(id); setJobs((js) => js.filter((j) => j.id !== id)) }, [])
  const clearFinished = useCallback(() => setJobs((js) => js.filter((j) => {
    const keep = ['queued', 'downloading', 'saving', 'ready'].includes(j.status)
    if (!keep) blobs.current.delete(j.id)
    return keep
  })), [])

  const value = {
    prefs, setPrefs,
    history, clearHistory: () => setHistory(clearHistory()), removeHistory: (id) => setHistory(removeHistory(id)),
    jobs, startDownload, cancel, retry, dismiss, clearFinished, saveReady,
    readyJob: jobs.find((j) => j.id === readyId && j.status === 'ready') || null,
    dismissReady: () => setReadyId(null),
    toast, notify,
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
