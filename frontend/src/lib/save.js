import { isIOS } from './platforms'

function asFile(blob, filename) {
  return new File([blob], filename, { type: blob.type || 'application/octet-stream' })
}

// True on iPhone/iPad when the share sheet can take this file (and offer "Save Video" / "Save Image").
export function canShareFile(blob, filename) {
  try {
    return isIOS() && !!navigator.canShare && navigator.canShare({ files: [asFile(blob, filename)] })
  } catch {
    return false
  }
}

// Save a Blob to the device in the most compatible way.
// * iPhone/iPad: the share sheet offers "Save Video"/"Save Image" to Photos or "Save to Files".
//   iOS can't write straight into the Photos library from a web app, so this is the best route.
// * Everywhere else: a normal browser download.
export async function saveBlob(blob, filename, { preferShare = true } = {}) {
  if (preferShare && isIOS() && navigator.canShare) {
    const file = asFile(blob, filename)
    if (navigator.canShare({ files: [file] })) {
      try {
        await navigator.share({ files: [file] })
        return 'shared'
      } catch (e) {
        if (e.name === 'AbortError') return 'cancelled'
        // fall through to a normal download
      }
    }
  }
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
  return 'downloaded'
}
