import { useEffect, useRef, useState } from 'react'
import { CheckCircle2, FileVideo, Loader2 } from 'lucide-react'
import type { UploadProgress as Progress } from '../api'
import { fmtBytes } from '../utils'

export interface UploadState {
  name: string
  loaded: number
  total: number
  startedAt: number
  /** bytes are on the server: the studio now prepares the video for analysis */
  processing?: boolean
}

export const startUpload = (file: File): UploadState => ({ name: file.name, loaded: 0, total: file.size, startedAt: Date.now() })

export const advance = (state: UploadState | null, p: Progress): UploadState | null =>
  state ? { ...state, loaded: p.loaded, total: p.total || state.total, processing: p.total > 0 && p.loaded >= p.total } : state

const fmtEta = (s: number) => (s < 60 ? `${Math.max(1, Math.ceil(s))}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`)

/** Upload bar with speed and time left, then "preparing" until the studio has the file. */
export function UploadProgressCard({ state, compact }: { state: UploadState; compact?: boolean }) {
  const [now, setNow] = useState(Date.now())
  const lastSample = useRef({ t: state.startedAt, loaded: 0, rate: 0 })
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 500)
    return () => clearInterval(timer)
  }, [])

  // smoothed transfer rate
  const dt = (now - lastSample.current.t) / 1000
  if (dt >= 1) {
    const instant = (state.loaded - lastSample.current.loaded) / dt
    lastSample.current = { t: now, loaded: state.loaded, rate: lastSample.current.rate ? lastSample.current.rate * 0.6 + instant * 0.4 : instant }
  }
  const pct = state.total ? Math.min(100, (state.loaded / state.total) * 100) : 0
  const rate = lastSample.current.rate
  const eta = rate > 0 && state.total ? (state.total - state.loaded) / rate : null

  return (
    <div className={`fade-in flex flex-col gap-2 rounded-2xl border border-line-strong bg-panel ${compact ? 'p-3' : 'p-4'}`}>
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="flex min-w-0 items-center gap-2">
          {state.processing ? <Loader2 className="size-4 shrink-0 animate-spin" /> : pct >= 100 ? <CheckCircle2 className="size-4 shrink-0" /> : <FileVideo className="size-4 shrink-0" />}
          <span className="truncate font-medium" title={state.name}>
            {state.name}
          </span>
        </span>
        <span className="shrink-0 font-mono text-xs text-neutral-400">{state.processing ? 'uploaded' : `${Math.floor(pct)}%`}</span>
      </div>
      <div className="relative h-2 overflow-hidden rounded-full bg-white/10">
        {state.processing ? (
          <div className="shimmer absolute inset-0" />
        ) : (
          <div className="bg-accent-gradient absolute inset-y-0 left-0 transition-[width] duration-300 ease-out" style={{ width: `${pct}%` }} />
        )}
      </div>
      <div className="flex flex-wrap justify-between gap-2 font-mono text-[11px] text-neutral-500">
        <span>
          {fmtBytes(state.loaded)} / {fmtBytes(state.total)}
          {!state.processing && rate > 0 && ` · ${fmtBytes(rate)}/s`}
        </span>
        <span>{state.processing ? 'Preparing the video for analysis…' : eta !== null ? `${fmtEta(eta)} left` : 'Starting…'}</span>
      </div>
    </div>
  )
}
