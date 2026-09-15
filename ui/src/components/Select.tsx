import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Check, ChevronDown } from 'lucide-react'
import { cls } from '../utils'

export interface SelectOption<T extends string> {
  value: T
  label: ReactNode
  description?: ReactNode
  icon?: ReactNode
  disabled?: boolean
}

interface Position {
  left: number
  top: number
  bottom: number
  width: number
  up: boolean
}

/** Animated, keyboard-accessible dropdown rendered in a portal (never clipped by scroll panels). */
export function Select<T extends string>({
  value,
  onChange,
  options,
  placeholder = 'Select…',
  disabled,
  size = 'md',
  className,
  menuWidth,
}: {
  value: T
  onChange: (v: T) => void
  options: SelectOption<T>[]
  placeholder?: string
  disabled?: boolean
  size?: 'sm' | 'md' | 'lg'
  className?: string
  menuWidth?: number
}) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const [pos, setPos] = useState<Position | null>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const menu = useRef<HTMLDivElement>(null)
  const selectedIndex = options.findIndex((o) => o.value === value)
  const selected = selectedIndex >= 0 ? options[selectedIndex] : undefined

  const place = () => {
    const r = trigger.current?.getBoundingClientRect()
    if (!r) return
    const below = window.innerHeight - r.bottom
    const up = below < 280 && r.top > below
    const width = Math.max(r.width, menuWidth ?? 0)
    const left = Math.max(8, Math.min(r.left, window.innerWidth - width - 8))
    setPos({ left, top: r.bottom + 6, bottom: window.innerHeight - r.top + 6, width, up })
  }

  const openMenu = () => {
    if (disabled) return
    setActive(Math.max(0, selectedIndex))
    place()
    setOpen(true)
  }

  const close = (focusTrigger = true) => {
    setOpen(false)
    if (focusTrigger) trigger.current?.focus()
  }

  useLayoutEffect(() => {
    if (!open) return
    const onMove = () => place()
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node
      if (!trigger.current?.contains(t) && !menu.current?.contains(t)) setOpen(false)
    }
    window.addEventListener('resize', onMove)
    window.addEventListener('scroll', onMove, true)
    document.addEventListener('mousedown', onDown)
    return () => {
      window.removeEventListener('resize', onMove)
      window.removeEventListener('scroll', onMove, true)
      document.removeEventListener('mousedown', onDown)
    }
  }, [open])

  useEffect(() => {
    if (open) menu.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [active, open])

  const choose = (i: number) => {
    const o = options[i]
    if (!o || o.disabled) return
    onChange(o.value)
    close()
  }

  const move = (dir: 1 | -1) => {
    if (!options.length) return
    let i = active
    for (let n = 0; n < options.length; n++) {
      i = (i + dir + options.length) % options.length
      if (!options[i].disabled) break
    }
    setActive(i)
  }

  const onKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (!open) {
      if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) {
        e.preventDefault()
        openMenu()
      }
      return
    }
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        move(1)
        break
      case 'ArrowUp':
        e.preventDefault()
        move(-1)
        break
      case 'Home':
        e.preventDefault()
        setActive(0)
        break
      case 'End':
        e.preventDefault()
        setActive(options.length - 1)
        break
      case 'Enter':
      case ' ':
        e.preventDefault()
        choose(active)
        break
      case 'Escape':
        e.preventDefault()
        close()
        break
      case 'Tab':
        close(false)
        break
    }
  }

  const sizes = {
    sm: 'h-7 rounded-lg px-2.5 text-xs',
    md: 'h-9 rounded-xl px-3 text-sm',
    lg: 'h-11 rounded-2xl px-4 text-sm',
  }

  return (
    <>
      <button
        ref={trigger}
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => (open ? close() : openMenu())}
        onKeyDown={onKey}
        className={cls(
          'group inline-flex w-full items-center justify-between gap-2 border bg-black text-left text-white outline-none transition-all duration-200 hover:border-neutral-500 focus-visible:border-leaf active:scale-[.99] disabled:opacity-40',
          open ? 'border-leaf shadow-[0_0_0_4px_rgba(155,210,60,.18)]' : 'border-line-strong',
          sizes[size],
          className,
        )}
      >
        <span className="flex min-w-0 items-center gap-2">
          {selected?.icon}
          <span className={cls('truncate', !selected && 'text-neutral-600')}>{selected ? selected.label : placeholder}</span>
        </span>
        <ChevronDown className={cls('size-4 shrink-0 transition-transform duration-300 ease-[cubic-bezier(.3,1.4,.5,1)]', open ? 'rotate-180 text-white' : 'text-neutral-500 group-hover:text-neutral-300')} />
      </button>

      {open &&
        pos &&
        createPortal(
          <div
            ref={menu}
            role="listbox"
            className={cls(
              'fixed z-[80] max-h-72 overflow-auto rounded-2xl border border-line-strong bg-neutral-950/95 p-1 shadow-[0_28px_70px_-16px_rgba(0,0,0,.95)] backdrop-blur-xl',
              pos.up ? 'dropdown-up' : 'dropdown-in',
            )}
            style={{ left: pos.left, width: pos.width, ...(pos.up ? { bottom: pos.bottom } : { top: pos.top }) }}
          >
            {options.map((o, i) => {
              const isSelected = o.value === value
              return (
                <div
                  key={o.value}
                  role="option"
                  aria-selected={isSelected}
                  aria-disabled={o.disabled || undefined}
                  data-index={i}
                  onMouseEnter={() => setActive(i)}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => choose(i)}
                  style={{ animationDelay: `${Math.min(i, 8) * 22}ms` }}
                  className={cls(
                    'option-in flex items-center gap-2.5 rounded-xl px-2.5 py-2 text-sm transition-colors duration-150',
                    i === active && !o.disabled ? 'bg-white/10 text-white' : 'text-neutral-300',
                    o.disabled && 'opacity-35',
                  )}
                >
                  {o.icon && <span className="flex shrink-0 items-center">{o.icon}</span>}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">{o.label}</span>
                    {o.description && <span className="block truncate text-xs text-neutral-500">{o.description}</span>}
                  </span>
                  <Check className={cls('size-4 shrink-0 text-white transition-all duration-200', isSelected ? 'scale-100 opacity-100' : 'scale-50 opacity-0')} />
                </div>
              )
            })}
          </div>,
          document.body,
        )}
    </>
  )
}
