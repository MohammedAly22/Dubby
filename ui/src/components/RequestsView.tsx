import { useEffect, useMemo, useState } from 'react'
import { Ban, CheckCircle2, ChevronRight, Clock, Loader2, XCircle } from 'lucide-react'
import { useStudio } from '../store'
import type { RequestEvent } from '../types'
import { cls } from '../utils'

type StatusFilter = 'all' | RequestEvent['status']

const KIND_LABEL: Record<string, string> = {
  vad: 'VAD',
  asr: 'ASR',
  langid: 'Language ID',
  translation: 'Translation',
  tts: 'TTS',
  alignment: 'Alignment',
  model: 'Model load',
  separation: 'Separation',
  render: 'Render',
  export: 'Export',
  download: 'Download',
  upload: 'Upload',
  ffmpeg: 'ffmpeg',
}
const kindLabel = (k: string) => KIND_LABEL[k] ?? k

const STATUSES: RequestEvent['status'][] = ['running', 'queued', 'done', 'error', 'cancelled']
const MAX_ROWS = 400

const fmtDuration = (s: number) => (s < 1 ? `${Math.round(s * 1000)} ms` : s < 60 ? `${s.toFixed(1)} s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`)

/** Every tracked request — jobs, VAD passes, API calls, TTS batches, model loads — with live status. */
export function RequestsView() {
  const requests = useStudio((s) => s.requests)
  const project = useStudio((s) => s.project)
  const [status, setStatus] = useState<StatusFilter>('all')
  const [kind, setKind] = useState<string>('all')
  const [projectOnly, setProjectOnly] = useState(false)
  const [open, setOpen] = useState<string | null>(null)
  const [now, setNow] = useState(Date.now() / 1000)

  const all = useMemo(() => Object.values(requests), [requests])
  const scoped = useMemo(() => (projectOnly && project ? all.filter((r) => r.project_id === project.id) : all), [all, projectOnly, project])
  const anyRunning = scoped.some((r) => r.status === 'running')

  useEffect(() => {
    if (!anyRunning) return
    const t = setInterval(() => setNow(Date.now() / 1000), 250)
    return () => clearInterval(t)
  }, [anyRunning])

  const byStatus = useMemo(() => {
    const out: Record<string, number> = {}
    for (const r of scoped) out[r.status] = (out[r.status] ?? 0) + 1
    return out
  }, [scoped])
  const byKind = useMemo(() => {
    const out: Record<string, number> = {}
    for (const r of scoped) out[r.kind] = (out[r.kind] ?? 0) + 1
    return Object.entries(out).sort((a, b) => b[1] - a[1])
  }, [scoped])

  const rows = useMemo(() => {
    const list = scoped.filter((r) => (status === 'all' || r.status === status) && (kind === 'all' || r.kind === kind))
    // running first, then newest
    list.sort((a, b) => Number(b.status === 'running') - Number(a.status === 'running') || (b.started ?? b.queued ?? 0) - (a.started ?? a.queued ?? 0))
    return list
  }, [scoped, status, kind])

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-col gap-2 border-b border-line px-4 py-2.5">
        <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
          <Chip active={status === 'all'} onClick={() => setStatus('all')}>
            Total <b className="font-mono">{scoped.length}</b>
          </Chip>
          {STATUSES.map((s) => (
            <Chip key={s} active={status === s} disabled={!byStatus[s]} onClick={() => setStatus(status === s ? 'all' : s)}>
              <StatusGlyph status={s} /> {s} <b className="font-mono">{byStatus[s] ?? 0}</b>
            </Chip>
          ))}
          {project && (
            <label className="ml-auto flex cursor-pointer items-center gap-1.5 text-neutral-500 select-none hover:text-neutral-300">
              <input type="checkbox" className="accent-white" checked={projectOnly} onChange={(e) => setProjectOnly(e.target.checked)} />
              This project only
            </label>
          )}
        </div>
        {byKind.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
            <Chip active={kind === 'all'} onClick={() => setKind('all')}>
              All kinds
            </Chip>
            {byKind.map(([k, n]) => (
              <Chip key={k} active={kind === k} onClick={() => setKind(kind === k ? 'all' : k)}>
                {kindLabel(k)} <b className="font-mono">{n}</b>
              </Chip>
            ))}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-auto font-mono text-[11.5px]">
        {rows.length ? (
          <table className="w-full border-separate border-spacing-0">
            <thead className="sticky top-0 z-10 bg-black text-left text-[10px] tracking-wider text-neutral-600 uppercase">
              <tr>
                <th className="w-24 px-4 py-1.5 font-semibold">Status</th>
                <th className="w-28 py-1.5 font-semibold">Kind</th>
                <th className="py-1.5 font-semibold">Request</th>
                <th className="hidden w-44 py-1.5 font-semibold md:table-cell">Engine</th>
                <th className="w-20 py-1.5 font-semibold">Started</th>
                <th className="w-20 px-4 py-1.5 text-right font-semibold">Time</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, MAX_ROWS).map((r) => (
                <Row key={r.id} r={r} now={now} open={open === r.id} onToggle={() => setOpen(open === r.id ? null : r.id)} />
              ))}
            </tbody>
          </table>
        ) : (
          <div className="px-4 py-6 text-neutral-600">{all.length ? 'No requests match these filters.' : 'No requests yet — they appear here as soon as the studio starts working.'}</div>
        )}
        {rows.length > MAX_ROWS && <div className="px-4 py-2 text-neutral-600">Showing the latest {MAX_ROWS} of {rows.length}.</div>}
      </div>
    </div>
  )
}

function Row({ r, now, open, onToggle }: { r: RequestEvent; now: number; open: boolean; onToggle: () => void }) {
  const elapsed = r.status === 'running' && r.started ? Math.max(0, now - r.started) : r.duration
  const expandable = !!(r.error || (r.detail && Object.keys(r.detail).length))
  return (
    <>
      <tr
        onClick={expandable ? onToggle : undefined}
        className={cls('transition-colors hover:bg-white/[.04]', expandable && 'cursor-pointer', r.level === 'call' ? 'text-neutral-400' : 'text-neutral-200', r.status === 'error' && 'text-white')}
      >
        <td className="border-b border-line/60 px-4 py-1.5">
          <span className="flex items-center gap-1.5">
            <StatusGlyph status={r.status} />
            <span className={cls(r.status === 'error' && 'font-semibold')}>{r.status}</span>
          </span>
        </td>
        <td className="border-b border-line/60 py-1.5 text-neutral-500">{kindLabel(r.kind)}</td>
        <td className="max-w-0 border-b border-line/60 py-1.5 pr-3">
          <span className="flex items-center gap-1.5">
            {expandable ? <ChevronRight className={cls('size-3 shrink-0 text-neutral-600 transition-transform', open && 'rotate-90')} /> : <span className="w-3 shrink-0" />}
            {r.level === 'call' && <span className="shrink-0 text-neutral-700">└</span>}
            <span className="truncate" title={r.label}>
              {r.label}
            </span>
          </span>
          {r.status === 'error' && r.error && !open && <div className="truncate pl-[18px] text-[11px] text-neutral-500">{r.error}</div>}
        </td>
        <td className="hidden truncate border-b border-line/60 py-1.5 text-neutral-500 md:table-cell">{r.engine ?? r.family ?? '—'}</td>
        <td className="border-b border-line/60 py-1.5 text-neutral-600">{r.started || r.queued ? new Date((r.started ?? r.queued)! * 1000).toLocaleTimeString() : '—'}</td>
        <td className="border-b border-line/60 px-4 py-1.5 text-right text-neutral-400 tabular-nums">{elapsed !== undefined && elapsed !== null ? fmtDuration(elapsed) : '—'}</td>
      </tr>
      {open && (
        <tr className="bg-white/[.02]">
          <td colSpan={6} className="border-b border-line/60 px-4 py-2 pl-12 text-[11px] whitespace-pre-wrap break-all text-neutral-400">
            {r.error && <div className="mb-1 text-white">✖ {r.error}</div>}
            {r.detail &&
              Object.entries(r.detail).map(([k, v]) => (
                <div key={k}>
                  <span className="text-neutral-600">{k}:</span> {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                </div>
              ))}
            <div className="text-neutral-700">{r.id}</div>
          </td>
        </tr>
      )}
    </>
  )
}

function StatusGlyph({ status }: { status: RequestEvent['status'] }) {
  if (status === 'running') return <Loader2 className="size-3 shrink-0 animate-spin" />
  if (status === 'done') return <CheckCircle2 className="size-3 shrink-0" />
  if (status === 'error') return <XCircle className="size-3 shrink-0" />
  if (status === 'cancelled') return <Ban className="size-3 shrink-0 text-neutral-500" />
  return <Clock className="size-3 shrink-0 text-neutral-500" />
}

function Chip({ active, disabled, onClick, children }: { active: boolean; disabled?: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={cls(
        'flex h-6 items-center gap-1.5 rounded-full border px-2.5 capitalize transition-colors disabled:opacity-35',
        active ? 'border-white bg-white text-black' : 'border-line-strong text-neutral-400 hover:border-neutral-500 hover:text-white',
      )}
    >
      {children}
    </button>
  )
}
