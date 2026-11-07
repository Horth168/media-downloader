import { CircleAlert, Info } from 'lucide-react'

export default function Notice({ tone = 'info', title, children, action }) {
  const Icon = tone === 'bad' ? CircleAlert : Info
  return (
    <div className="sheet-in rounded-[22px] bg-charcoal p-4" role={tone === 'bad' ? 'alert' : undefined}>
      <div className="flex items-start gap-3">
        <Icon size={20} className={`mt-0.5 shrink-0 ${tone === 'bad' ? 'text-bad' : 'text-[#A995FF]'}`} />
        <div className="min-w-0 flex-1">
          <p className="font-bold">{title}</p>
          <p className="mt-1 text-sm leading-relaxed text-muted">{children}</p>
          {action && (
            <button onClick={action.onClick} className="btn-ghost focus-ring mt-3 bg-white/5">
              {action.label}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
