import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { api, ApiError } from './api'
import { saveBlob } from './save'
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

  const patchJob = (id, patch) => setJobs((js) => js.map((j) => (j.id === id ? { ...j, ...patch } : j)))

  const run = useCallback(async (job) => {
    const ctrl = new AbortController()
    controllers.current.set(job.id, ctrl)
    patchJob(job.id, { status: 'downloading', loaded: 0, total: job.sizeHint || 0, error: null })
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
          patchJob(job.id, { loaded, total: total || job.sizeHint || 0 }))
        patchJob(job.id, { status: 'saving' })
      }
      const how = await saveBlob(blob, filename, { preferShare: prefs.iosShareSheet })
      patchJob(job.id, { status: 'done', size: blob.size, savedVia: how })
      notify(how === 'cancelled' ? 'Download ready — saving was cancelled.' : `Saved ${filename}`, 'ok')
      if (prefs.keepHistory) {
        setHistory(addHistory({
          id: job.id, title: job.title, platform: job.platform, format: job.format,
          filename, size: blob.size, thumbnail: job.thumbnail, sourceUrl: job.sourceUrl, at: Date.now(),
        }))
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
  }, [notify, prefs.iosShareSheet, prefs.keepHistory])

  const startDownload = useCallback((spec) => {
    const job = { id: newId(), status: 'queued', loaded: 0, total: 0, createdAt: Date.now(), ...spec }
    setJobs((js) => [job, ...js])
    run(job)
    return job.id
  }, [run])

  const cancel = useCallback((id) => controllers.current.get(id)?.abort(), [])
  const jobsRef = useRef(jobs)
  jobsRef.current = jobs
  const retry = useCallback((id) => {
    const job = jobsRef.current.find((j) => j.id === id)
    if (job && !controllers.current.has(id)) run(job)
  }, [run])
  const dismiss = useCallback((id) => setJobs((js) => js.filter((j) => j.id !== id)), [])
  const clearFinished = useCallback(() => setJobs((js) => js.filter((j) => ['queued', 'downloading', 'saving'].includes(j.status))), [])

  const value = {
    prefs, setPrefs,
    history, clearHistory: () => setHistory(clearHistory()), removeHistory: (id) => setHistory(removeHistory(id)),
    jobs, startDownload, cancel, retry, dismiss, clearFinished,
    toast, notify,
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
