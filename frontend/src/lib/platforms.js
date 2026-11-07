// Client-side platform detection for instant feedback while typing.
// The server repeats this check — it is the source of truth.
export const PLATFORMS = {
  youtube: { name: 'YouTube', color: '#FF0033', domains: ['youtube.com', 'youtu.be', 'youtube-nocookie.com'] },
  tiktok: { name: 'TikTok', color: '#25F4EE', domains: ['tiktok.com'] },
  douyin: { name: 'Douyin', color: '#FE2C55', domains: ['douyin.com', 'iesdouyin.com'] },
  instagram: { name: 'Instagram', color: '#E1306C', domains: ['instagram.com', 'instagr.am'] },
  facebook: { name: 'Facebook', color: '#1877F2', domains: ['facebook.com', 'fb.com', 'fb.watch'] },
  direct: { name: 'Direct link', color: '#7C5CFF', domains: [] },
}

export function extractUrl(text) {
  if (!text) return ''
  const m = String(text).match(/https?:\/\/[^\s"'<>]+/i)
  if (m) return m[0].replace(/[),.;!?]+$/, '')
  const t = String(text).trim()
  return /^[\w-]+(\.[\w-]+)+(\/\S*)?$/.test(t) ? 'https://' + t : t
}

export function detectPlatform(url) {
  let host
  try { host = new URL(url).hostname.toLowerCase().replace(/\.$/, '') } catch { return null }
  for (const [id, p] of Object.entries(PLATFORMS)) {
    if (p.domains.some((d) => host === d || host.endsWith('.' + d))) return id
  }
  return 'direct'
}

export function formatBytes(n) {
  if (n == null || isNaN(n)) return null
  if (n < 1024) return `${n} B`
  const u = ['KB', 'MB', 'GB']
  let i = -1
  do { n /= 1024; i++ } while (n >= 1024 && i < u.length - 1)
  return `${n.toFixed(n < 10 ? 1 : 0)} ${u[i]}`
}

export const isIOS = () =>
  /iPad|iPhone|iPod/.test(navigator.userAgent) ||
  (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)

export const isStandalone = () =>
  window.matchMedia?.('(display-mode: standalone)').matches || window.navigator.standalone === true
