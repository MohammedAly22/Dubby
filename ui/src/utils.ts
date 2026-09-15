import type { Segment, StageState } from './types'

export const cls = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(' ')

export function fmtTime(seconds?: number | null, centis = true): string {
  if (seconds === undefined || seconds === null || !Number.isFinite(seconds)) return '--:--'
  const s = Math.max(0, seconds)
  const m = Math.floor(s / 60)
  const rest = s - m * 60
  const sec = centis ? rest.toFixed(2).padStart(5, '0') : String(Math.floor(rest)).padStart(2, '0')
  return `${String(m).padStart(2, '0')}:${sec}`
}

export function fmtDuration(seconds?: number | null): string {
  if (!seconds) return '—'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  return h ? `${h}h ${String(m).padStart(2, '0')}m` : `${m}m ${String(s).padStart(2, '0')}s`
}

export function fmtBytes(n: number): string {
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let v = n
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(v < 10 && i ? 1 : 0)} ${units[i]}`
}

export function timeAgo(ts: number): string {
  const diff = Date.now() / 1000 - ts
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

export function segmentIndexAt(segments: Segment[], t: number): number {
  let lo = 0
  let hi = segments.length - 1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    const s = segments[mid]
    if (t < s.start) hi = mid - 1
    else if (t >= s.end) lo = mid + 1
    else return mid
  }
  return -1
}

export const isBusy = (st?: StageState) => !!st && (st.status === 'running' || st.status === 'queued')

export const TARGET_LABEL: Record<string, string> = { arz: 'Egyptian Arabic', arb: 'Modern Standard Arabic' }
export const TARGET_SHORT: Record<string, string> = { arz: 'مصري', arb: 'فصحى' }
export const SOURCE_LABEL: Record<string, string> = { en: 'English', ar: 'Arabic' }

export function debounceByKey<T extends (...args: any[]) => void>(fn: T, wait = 400) {
  const timers = new Map<string, ReturnType<typeof setTimeout>>()
  return (key: string, ...args: Parameters<T>) => {
    const t = timers.get(key)
    if (t) clearTimeout(t)
    timers.set(
      key,
      setTimeout(() => {
        timers.delete(key)
        fn(...args)
      }, wait),
    )
  }
}

export const isStale = (s: Segment) => s.tts.status === 'done' && (s.tts.text ?? '') !== s.translation
export const translationStale = (s: Segment) => s.translation_status === 'done' && !!s.translation_source && s.translation_source !== s.text
