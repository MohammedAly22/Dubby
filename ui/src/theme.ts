import { create } from 'zustand'

export type Theme = 'dark' | 'light'

const KEY = 'dubby-theme'

function readTheme(): Theme {
  try {
    const fromUrl = new URLSearchParams(window.location.search).get('theme')
    if (fromUrl === 'light' || fromUrl === 'dark') return fromUrl
    const stored = localStorage.getItem(KEY)
    if (stored === 'light' || stored === 'dark') return stored
  } catch {
    /* storage unavailable */
  }
  return 'dark'
}

export function applyTheme(theme: Theme) {
  const root = document.documentElement
  root.classList.toggle('light', theme === 'light')
  root.classList.toggle('dark', theme === 'dark')
  root.style.colorScheme = theme
  try {
    localStorage.setItem(KEY, theme)
  } catch {
    /* storage unavailable */
  }
}

interface ThemeState {
  theme: Theme
  toggle: (origin?: { x: number; y: number }) => void
}

export const useTheme = create<ThemeState>((set, get) => ({
  theme: readTheme(),
  toggle: (origin) => {
    const next: Theme = get().theme === 'dark' ? 'light' : 'dark'
    const commit = () => {
      applyTheme(next)
      set({ theme: next })
    }
    const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown }
    if (!doc.startViewTransition || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      commit()
      return
    }
    // Circular reveal expanding from the toggle button.
    const x = origin?.x ?? window.innerWidth - 60
    const y = origin?.y ?? 28
    const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y))
    const root = document.documentElement
    root.style.setProperty('--tx', `${x}px`)
    root.style.setProperty('--ty', `${y}px`)
    root.style.setProperty('--tr', `${radius}px`)
    doc.startViewTransition(commit)
  },
}))

applyTheme(useTheme.getState().theme)
