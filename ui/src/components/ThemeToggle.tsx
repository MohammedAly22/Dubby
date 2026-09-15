import { Moon, Sun } from 'lucide-react'
import { useTheme } from '../theme'
import { cls } from '../utils'

export function ThemeToggle() {
  const theme = useTheme((s) => s.theme)
  const toggle = useTheme((s) => s.toggle)
  const dark = theme === 'dark'
  return (
    <button
      type="button"
      role="switch"
      aria-checked={!dark}
      title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
      onClick={(e) => {
        const r = e.currentTarget.getBoundingClientRect()
        toggle({ x: r.left + r.width / 2, y: r.top + r.height / 2 })
      }}
      className="group relative inline-flex h-8 w-[58px] items-center rounded-full border border-line-strong bg-raised px-1 transition-colors duration-300 hover:border-neutral-500"
    >
      <span
        className={cls(
          'absolute top-1 flex size-6 items-center justify-center rounded-full bg-white text-black transition-all duration-500 ease-[cubic-bezier(.3,1.4,.5,1)]',
          dark ? 'left-1' : 'left-[29px]',
        )}
      >
        <Moon className={cls('absolute size-3.5 transition-all duration-500', dark ? 'rotate-0 scale-100 opacity-100' : '-rotate-90 scale-0 opacity-0')} />
        <Sun className={cls('absolute size-3.5 transition-all duration-500', dark ? 'rotate-90 scale-0 opacity-0' : 'rotate-0 scale-100 opacity-100')} />
      </span>
      <Sun className={cls('ml-auto size-3 text-neutral-500 transition-opacity duration-300', dark ? 'opacity-100' : 'opacity-0')} />
      <Moon className={cls('absolute left-2 size-3 text-neutral-500 transition-opacity duration-300', dark ? 'opacity-0' : 'opacity-100')} />
    </button>
  )
}
