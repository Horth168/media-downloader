import { CheckCircle2, CircleAlert, Info } from 'lucide-react'
import { useApp } from '../lib/AppContext'

export default function Toast() {
  const { toast } = useApp()
  if (!toast) return null
  const Icon = toast.tone === 'ok' ? CheckCircle2 : toast.tone === 'bad' ? CircleAlert : Info
  const color = toast.tone === 'ok' ? 'text-ok' : toast.tone === 'bad' ? 'text-bad' : 'text-[#A995FF]'
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-24 z-40 flex justify-center px-4" role="status" aria-live="polite">
      <div key={toast.id} className="sheet-in flex max-w-[440px] items-start gap-2.5 rounded-2xl border border-line bg-graphite/95 px-4 py-3 text-sm font-medium shadow-2xl backdrop-blur">
        <Icon size={18} className={`mt-0.5 shrink-0 ${color}`} />
        <span>{toast.message}</span>
      </div>
    </div>
  )
}
