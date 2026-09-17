import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ButtonHTMLAttributes, type CSSProperties, type ReactNode } from 'react'
import { Ban, CheckCircle2, Circle, Clock3, Loader2, PauseCircle, X, XCircle } from 'lucide-react'
import type { StageStatus } from '../types'
import { cls } from '../utils'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'

export function Button({
  variant = 'secondary',
  size = 'md',
  icon,
  loading,
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: 'sm' | 'md' | 'lg'; icon?: ReactNode; loading?: boolean }) {
  const base =
    'inline-flex items-center justify-center gap-2 rounded-full font-medium select-none whitespace-nowrap transition-all duration-200 ease-out active:scale-[.96] disabled:opacity-35 disabled:active:scale-100'
  const variants: Record<Variant, string> = {
    primary: 'btn-shine bg-white text-black hover:bg-neutral-100 hover:shadow-[0_0_28px_color-mix(in_srgb,var(--color-white)_25%,transparent)]',
    secondary: 'bg-raised text-white border border-line-strong hover:border-neutral-500 hover:bg-neutral-900',
    ghost: 'text-neutral-300 hover:text-white hover:bg-white/5',
    danger: 'border border-neutral-700 text-neutral-200 hover:bg-white hover:text-black',
  }
  const sizes = { sm: 'h-7 px-3 text-xs', md: 'h-9 px-4 text-sm', lg: 'h-12 px-6 text-base' }
  return (
    <button className={cls(base, variants[variant], sizes[size], className)} {...rest}>
      {loading ? <Loader2 className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  )
}

export function IconButton({ className, title, children, ...rest }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      title={title}
      aria-label={title}
      className={cls(
        'inline-flex size-7 items-center justify-center rounded-full text-neutral-400 transition-all duration-200 hover:bg-white/10 hover:text-white active:scale-90 disabled:opacity-30 disabled:hover:bg-transparent disabled:active:scale-100',
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  )
}

export function Badge({ children, tone = 'default', className }: { children: ReactNode; tone?: 'default' | 'solid' | 'outline' | 'muted'; className?: string }) {
  const tones = {
    default: 'bg-white/8 text-neutral-200 border border-white/10',
    solid: 'bg-white text-black',
    outline: 'border border-neutral-600 text-neutral-300',
    muted: 'text-neutral-500 border border-line',
  }
  return <span className={cls('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider', tones[tone], className)}>{children}</span>
}

/** Progress bars are one of the few places that carry the brand accent. */
export function Progress({ value, active, className }: { value: number; active?: boolean; className?: string }) {
  return (
    <div className={cls('relative h-1.5 w-full overflow-hidden rounded-full bg-white/10', className)}>
      <div
        className={cls(
          'relative h-full rounded-full transition-[width] duration-500 ease-[cubic-bezier(.2,.8,.2,1)]',
          active ? 'stripes shadow-[0_0_12px_rgba(155,210,60,.6)]' : 'bg-accent-gradient',
        )}
        style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }}
      />
      {active && <div className="shimmer absolute inset-0" />}
    </div>
  )
}

export function StatusIcon({ status, className }: { status: StageStatus | 'pending'; className?: string }) {
  const c = cls('size-4 shrink-0', className)
  switch (status) {
    case 'running':
      return <Loader2 className={cls(c, 'animate-spin text-white')} />
    case 'queued':
      return <Clock3 className={cls(c, 'animate-pulse text-neutral-400')} />
    case 'done':
      return <CheckCircle2 className={cls(c, 'text-white')} />
    case 'error':
      return <XCircle className={cls(c, 'text-neutral-300')} />
    case 'cancelled':
      return <Ban className={cls(c, 'text-neutral-500')} />
    case 'paused':
      return <PauseCircle className={cls(c, 'text-neutral-200')} />
    default:
      return <Circle className={cls(c, 'text-neutral-600')} />
  }
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cls('rounded-2xl border border-line bg-panel', className)}>{children}</div>
}

export function Switch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label?: ReactNode; disabled?: boolean }) {
  return (
    <span className={cls('inline-flex items-center gap-2 text-sm text-neutral-300', disabled && 'opacity-40')}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cls('relative h-5 w-9 shrink-0 rounded-full border transition-all duration-300', checked ? 'border-white bg-white' : 'border-neutral-700 bg-neutral-900 hover:border-neutral-500')}
      >
        <span className={cls('absolute top-0.5 size-3.5 rounded-full transition-all duration-300 ease-[cubic-bezier(.3,1.5,.5,1)]', checked ? 'left-[18px] bg-black' : 'left-0.5 bg-neutral-500')} />
      </button>
      {label && (
        <span className="cursor-pointer" onClick={() => !disabled && onChange(!checked)}>
          {label}
        </span>
      )}
    </span>
  )
}

/**
 * Measures the active item so a pill can glide between options.
 * The first measurement snaps into place; only later changes animate (`ready`).
 */
export function useIndicator<C extends HTMLElement = HTMLDivElement>(activeIndex: number, deps: unknown[] = []) {
  const container = useRef<C>(null)
  const items = useRef<(HTMLElement | null)[]>([])
  const [style, setStyle] = useState<CSSProperties>({ left: 0, width: 0, opacity: 0 })
  const [ready, setReady] = useState(false)
  const placed = useRef(false)

  const measure = useCallback(() => {
    const el = items.current[activeIndex]
    if (!el) {
      setStyle((s) => ({ ...s, opacity: 0 }))
      return
    }
    setStyle({ left: el.offsetLeft, width: el.offsetWidth, opacity: 1 })
    if (!placed.current) {
      placed.current = true
      requestAnimationFrame(() => requestAnimationFrame(() => setReady(true)))
    }
  }, [activeIndex])

  useLayoutEffect(() => {
    measure()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [measure, ...deps])

  useEffect(() => {
    const c = container.current
    if (!c) return
    const ro = new ResizeObserver(() => measure())
    ro.observe(c)
    items.current.forEach((el) => el && ro.observe(el))
    document.fonts?.ready.then(() => measure()).catch(() => {})
    return () => ro.disconnect()
  }, [measure])

  return { container, items, style, ready }
}

export function Segmented<T extends string>({
  value,
  onChange,
  options,
  size = 'md',
  className,
}: {
  value: T
  onChange: (v: T) => void
  options: { value: T; label: ReactNode; disabled?: boolean; title?: string }[]
  size?: 'sm' | 'md'
  className?: string
}) {
  const index = options.findIndex((o) => o.value === value)
  const { container, items, style, ready } = useIndicator<HTMLDivElement>(index, [options.length, size])
  return (
    <div ref={container} role="tablist" className={cls('relative inline-flex rounded-full border border-line-strong bg-black p-0.5', className)}>
      <span
        aria-hidden
        className={cls('pointer-events-none absolute top-0.5 bottom-0.5 rounded-full bg-white', ready && 'transition-[left,width,opacity] duration-300 ease-[cubic-bezier(.3,1.25,.5,1)]')}
        style={style}
      />
      {options.map((o, i) => (
        <button
          key={o.value}
          ref={(el) => {
            items.current[i] = el
          }}
          type="button"
          role="tab"
          aria-selected={value === o.value}
          title={o.title}
          disabled={o.disabled}
          onClick={() => onChange(o.value)}
          className={cls(
            'relative z-10 inline-flex items-center gap-1.5 rounded-full font-medium transition-colors duration-200 disabled:opacity-30',
            size === 'sm' ? 'h-6 px-2.5 text-[11px]' : 'h-8 px-3.5 text-xs',
            value === o.value ? 'text-black' : 'text-neutral-400 hover:text-white',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Field({ label, hint, children, className }: { label: ReactNode; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={cls('flex flex-col gap-1.5', className)}>
      <span className="text-[11px] font-semibold uppercase tracking-wider text-neutral-500">{label}</span>
      {children}
      {hint && <span className="text-xs text-neutral-500">{hint}</span>}
    </div>
  )
}

/** Inputs keep the accent only on focus. */
export const inputCls =
  'h-9 w-full rounded-xl border border-line-strong bg-black px-3 text-sm text-white outline-none transition-all duration-200 placeholder:text-neutral-600 hover:border-neutral-600 focus:border-leaf focus:shadow-[0_0_0_4px_rgba(155,210,60,.15)]'

export function Slider({ value, onChange, min, max, step, format }: { value: number; onChange: (v: number) => void; min: number; max: number; step: number; format?: (v: number) => string }) {
  return (
    <div className="flex items-center gap-3">
      <input type="range" className="w-full" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
      <span className="w-14 text-right font-mono text-xs text-neutral-300 tabular-nums">{format ? format(value) : value}</span>
    </div>
  )
}

/** Animated audio bars shown while something is playing. */
export function Equalizer({ className, bars = 4 }: { className?: string; bars?: number }) {
  return (
    <span className={cls('eq inline-flex h-3.5 items-end gap-[2px]', className)} aria-label="playing">
      {Array.from({ length: bars }).map((_, i) => (
        <span key={i} className="h-full w-[2.5px] rounded-full bg-current" style={{ animationDelay: `${i * 0.13}s` }} />
      ))}
    </span>
  )
}

/** Textarea that grows with its content and commits on blur / Ctrl+Enter. */
export function AutoTextarea({
  value,
  onCommit,
  rtl,
  placeholder,
  className,
  disabled,
  onFocus,
}: {
  value: string
  onCommit: (v: string) => void
  rtl?: boolean
  placeholder?: string
  className?: string
  disabled?: boolean
  onFocus?: () => void
}) {
  const ref = useRef<HTMLTextAreaElement>(null)
  const [draft, setDraft] = useState(value)
  const focused = useRef(false)

  useEffect(() => {
    if (!focused.current) setDraft(value)
  }, [value])

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = '0px'
    el.style.height = `${el.scrollHeight}px`
  }, [draft])

  const commit = () => {
    if (draft.trim() !== value.trim()) onCommit(draft)
  }

  return (
    <textarea
      ref={ref}
      rows={1}
      dir={rtl ? 'rtl' : 'auto'}
      value={draft}
      disabled={disabled}
      placeholder={placeholder}
      onFocus={() => {
        focused.current = true
        onFocus?.()
      }}
      onBlur={() => {
        focused.current = false
        commit()
      }}
      onChange={(e) => setDraft(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
          e.preventDefault()
          ;(e.target as HTMLTextAreaElement).blur()
        }
        if (e.key === 'Escape') {
          setDraft(value)
          ;(e.target as HTMLTextAreaElement).blur()
        }
      }}
      className={cls(
        'w-full cursor-text resize-none overflow-hidden rounded-xl border border-transparent bg-transparent px-2.5 py-1.5 text-sm text-white outline-none transition-all duration-200 hover:border-line-strong focus:border-leaf focus:bg-black focus:shadow-[0_0_0_4px_rgba(155,210,60,.14)]',
        rtl && 'arabic text-[15px]',
        className,
      )}
    />
  )
}

export function Empty({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="fade-in flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-line-strong px-6 py-12 text-center">
      {icon && <div className="float text-neutral-500">{icon}</div>}
      <div className="text-sm font-semibold text-white">{title}</div>
      {children && <div className="max-w-md text-sm text-neutral-500">{children}</div>}
    </div>
  )
}

export function Modal({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  if (!open) return null
  return (
    <div className="backdrop-in fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/75 p-4 backdrop-blur-md sm:p-10" onMouseDown={onClose}>
      <div
        className={cls('scale-in w-full rounded-2xl border border-line-strong bg-panel shadow-[0_40px_120px_-20px_rgba(0,0,0,.8)] backdrop-blur-xl', wide ? 'max-w-4xl' : 'max-w-xl')}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-line px-6 py-4">
          <div className="text-base font-semibold">{title}</div>
          <IconButton title="Close" onClick={onClose} className="hover:rotate-90">
            <X className="size-4" />
          </IconButton>
        </div>
        <div className="p-6">{children}</div>
      </div>
    </div>
  )
}
