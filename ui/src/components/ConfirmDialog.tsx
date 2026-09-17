import { useEffect } from 'react'
import { useStudio } from '../store'
import { Button } from './ui'

/**
 * The studio's confirmation dialog — replaces window.confirm, which cannot be styled
 * and freezes the page. Driven by `useStudio().confirm(...)`, which resolves to a boolean.
 */
export function ConfirmDialog() {
  const request = useStudio((s) => s.confirmRequest)
  const resolve = useStudio((s) => s.resolveConfirm)

  useEffect(() => {
    if (!request) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        resolve(false)
      } else if (e.key === 'Enter') {
        e.preventDefault()
        resolve(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [request, resolve])

  if (!request) return null
  const { title, message, confirmLabel = 'Confirm', cancelLabel = 'Cancel', tone = 'default', icon = tone === 'danger' ? '🗑️' : '❓' } = request

  return (
    <div
      className="backdrop-in fixed inset-0 z-[60] flex items-center justify-center bg-black/75 p-4 backdrop-blur-md"
      onMouseDown={() => resolve(false)}
      role="alertdialog"
      aria-modal="true"
      aria-label={title}
    >
      <div
        className="scale-in w-full max-w-md rounded-2xl border border-line-strong bg-panel p-6 shadow-[0_40px_120px_-20px_rgba(0,0,0,.8)] backdrop-blur-xl"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex gap-4">
          <div className="flex size-11 shrink-0 items-center justify-center rounded-2xl border border-line-strong bg-raised text-xl">{icon}</div>
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold">{title}</h2>
            {message && <p className="mt-1.5 text-sm leading-relaxed whitespace-pre-line text-neutral-400">{message}</p>}
          </div>
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <Button onClick={() => resolve(false)}>{cancelLabel}</Button>
          <Button autoFocus variant="primary" onClick={() => resolve(true)}>
            {confirmLabel}
          </Button>
        </div>
        <p className="mt-3 text-right text-[11px] text-neutral-600">Enter to confirm · Esc to cancel</p>
      </div>
    </div>
  )
}
