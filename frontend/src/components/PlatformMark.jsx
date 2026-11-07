import { Facebook, Instagram, Link2, Music2, Youtube } from 'lucide-react'
import { PLATFORMS } from '../lib/platforms'

const ICONS = { youtube: Youtube, tiktok: Music2, douyin: Music2, instagram: Instagram, facebook: Facebook, direct: Link2 }

export default function PlatformMark({ id, size = 36, dim = false }) {
  const p = PLATFORMS[id] || PLATFORMS.direct
  const Icon = ICONS[id] || Link2
  return (
    <span
      className={`grid shrink-0 place-items-center rounded-full transition-opacity ${dim ? 'opacity-45' : ''}`}
      style={{ width: size, height: size, background: `color-mix(in srgb, ${p.color} 16%, #121219)`, color: p.color }}
      title={p.name}
    >
      <Icon size={Math.round(size * 0.5)} strokeWidth={2.2} />
    </span>
  )
}
