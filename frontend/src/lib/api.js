// Backend URL is baked in at build time (VITE_API_URL). Falls back to local dev.
export const API_BASE = (import.meta.env.VITE_API_URL || 'http://localhost:5000').replace(/\/$/, '')


export class ApiError extends Error {
  constructor(code, message, status, extra = {}) {
    super(message)
    this.code = code
    this.status = status
    Object.assign(this, extra)
  }
}

async function request(path, { method = 'GET', body, timeout = 45000 } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeout)
  let res
  try {
    res = await fetch(API_BASE + path, {
      method, headers, body: body ? JSON.stringify(body) : undefined, signal: ctrl.signal,
    })
  } catch (e) {
    if (!navigator.onLine) throw new ApiError('offline', "You're offline. Connect to the internet and try again.")
    if (e.name === 'AbortError') throw new ApiError('timeout', 'The server took too long to respond. It may be waking up — try again in a moment.')
    throw new ApiError('network', "Couldn't reach the server. It may be waking up — try again in a moment.")
  } finally {
    clearTimeout(timer)
  }
  let data = {}
  try { data = await res.json() } catch { /* non-JSON */ }
  if (!res.ok || data.ok === false) {
    const { error, message, ...extra } = data
    throw new ApiError(error || 'http_' + res.status, message || `Request failed (${res.status}).`, res.status, extra)
  }
  return data
}

export const api = {
  health: () => request('/api/health', { timeout: 70000 }),
  platforms: () => request('/api/platforms', { timeout: 70000 }),
  analyze: (url) => request('/api/analyze', { method: 'POST', body: { url }, timeout: 90000 }),
  downloadUrl: (ticket) => `${API_BASE}/api/download?t=${encodeURIComponent(ticket)}`,
}
