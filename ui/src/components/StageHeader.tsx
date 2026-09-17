import type { ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'
import type { StageState } from '../types'
import { cls } from '../utils'
import { Progress, StatusIcon } from './ui'

const STATUS_TEXT: Record<string, string> = {
  idle: 'Not started',
  queued: 'Queued',
  running: 'Running',
  done: 'Done',
  error: 'Failed',
  cancelled: 'Cancelled',
  paused: 'Paused',
}

export function StageHeader({
  icon,
  title,
  subtitle,
  state,
  actions,
}: {
  icon: ReactNode
  title: string
  subtitle?: ReactNode
  state?: StageState
  actions?: ReactNode
}) {
  const st = state ?? { status: 'idle', progress: 0, message: '' }
  const busy = st.status === 'running' || st.status === 'queued'
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="flex size-10 items-center justify-center rounded-xl border border-line-strong bg-black text-lg">{icon}</div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
              <span className={cls('inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px]', st.status === 'done' ? 'border-white/40 text-white' : 'border-line-strong text-neutral-400')}>
                <StatusIcon status={st.status} className="size-3" />
                {STATUS_TEXT[st.status]}
                {st.engine ? <span className="text-neutral-500">· {st.engine}</span> : null}
              </span>
            </div>
            {subtitle && <div className="mt-0.5 text-sm text-neutral-500">{subtitle}</div>}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">{actions}</div>
      </div>
      {busy && (
        <div className="fade-in flex flex-col gap-1.5">
          <Progress value={st.progress} active />
          <div className="flex justify-between font-mono text-[11px] text-neutral-400">
            <span className="truncate">{st.message}</span>
            <span>{Math.round(st.progress * 100)}%</span>
          </div>
        </div>
      )}
      {st.status === 'done' && st.message && <div className="text-xs text-neutral-400">✓ {st.message}</div>}
      {st.status === 'paused' && (
        <div className="flex gap-2 rounded-xl border border-white/40 bg-white/[.04] p-3 text-sm text-neutral-200">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <div className="min-w-0 break-words text-xs leading-relaxed">
            <div className="font-semibold text-white">{st.message}</div>
            {st.error}
          </div>
        </div>
      )}
      {st.status === 'error' && (
        <div className="flex gap-2 rounded-xl border border-neutral-700 bg-white/[.03] p-3 text-sm text-neutral-200">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <div className="min-w-0 whitespace-pre-wrap break-words font-mono text-xs">{st.error}</div>
        </div>
      )}
    </div>
  )
}
