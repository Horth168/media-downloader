// Small localStorage helpers. All reads/writes are guarded: private mode or
// blocked storage just means preferences don't persist.
const PREFS_KEY = 'fetchly.prefs'
const HISTORY_KEY = 'fetchly.history'
const HISTORY_MAX = 100

export const DEFAULT_PREFS = {
  defaultFormat: 'mp4',     // mp4 | mp3 | photo
  autoAnalyze: true,        // analyze immediately after paste
  iosShareSheet: true,      // on iPhone/iPad, open the share sheet to "Save Video"/"Save Image"
  keepHistory: true,
}

function read(key, fallback) {
  try {
    const v = localStorage.getItem(key)
    return v ? JSON.parse(v) : fallback
  } catch { return fallback }
}
function write(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)) } catch { /* ignore */ }
}

export const loadPrefs = () => ({ ...DEFAULT_PREFS, ...read(PREFS_KEY, {}) })
export const savePrefs = (p) => write(PREFS_KEY, p)

export const loadHistory = () => read(HISTORY_KEY, [])
export function addHistory(entry) {
  const list = [entry, ...loadHistory().filter((e) => e.id !== entry.id)].slice(0, HISTORY_MAX)
  write(HISTORY_KEY, list)
  return list
}
export function clearHistory() {
  write(HISTORY_KEY, [])
  return []
}
export function removeHistory(id) {
  const list = loadHistory().filter((e) => e.id !== id)
  write(HISTORY_KEY, list)
  return list
}
