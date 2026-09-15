import { CheckCircle2, Info, XCircle } from 'lucide-react'
import { useStudio } from '../store'
import { cls } from '../utils'

export function Toasts() {
  const toasts = useStudio((s) => s.toasts)
  const dismiss = useStudio((s) => s.dismiss)
  return (
    <div className="pointer-events-none fixed right-4 bottom-4 z-[60] flex w-[min(420px,calc(100vw-2rem))] flex-col gap-2">
      {toasts.map((t) => (
        <button
          key={t.id}
          onClick={() => dismiss(t.id)}
          className={cls(
            'toast-in pointer-events-auto transition-transform duration-200 hover:-translate-x-1 flex items-start gap-2.5 rounded-2xl border px-4 py-3 text-left text-sm shadow-2xl backdrop-blur-xl',
            t.kind === 'error' ? 'border-neutral-500 bg-neutral-950/95 text-white' : t.kind === 'success' ? 'border-white bg-white text-black' : 'border-line-strong bg-neutral-950/95 text-white',
          )}
        >
          {t.kind === 'error' ? <XCircle className="mt-0.5 size-4 shrink-0" /> : t.kind === 'success' ? <CheckCircle2 className="mt-0.5 size-4 shrink-0" /> : <Info className="mt-0.5 size-4 shrink-0" />}
          <span className="break-words">{t.message}</span>
        </button>
      ))}
    </div>
  )
}
