import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowDownToLine, CheckCircle2, CloudDownload, Loader2, Trash2, X, XCircle } from 'lucide-react'
import { api } from '../api'
import { RequestsView } from './RequestsView'
import { useStudio } from '../store'
import type { DownloadEvent } from '../types'
import { cls, fmtBytes } from '../utils'
import { IconButton, Segmented } from './ui'

type Level = 'all' | 'info' | 'warning' | 'error'
type Tab = 'logs' | 'requests'

const fmtEta = (s: number) =>
  s < 60 ? `${Math.max(1, Math.ceil(s))}s` : s < 3600 ? `${Math.floor(s / 60)}m ${Math.round(s % 60)}s` : `${Math.floor(s / 3600)}h ${Math.round((s % 3600) / 60)}m`

export function LogsDrawer() {
  const open = useStudio((s) => s.logsOpen)
  const setOpen = useStudio((s) => s.setLogsOpen)
  const logs = useStudio((s) => s.logs)
  const [level, setLevel] = useState<Level>('info')
  const [tab, setTab] = useState<Tab>('logs')
  const requests = useStudio((s) => s.requests)
  const requestCount = Object.keys(requests).length
  const running = useMemo(() => Object.values(requests).filter((r) => r.status === 'running').length, [requests])
  const [follow, setFollow] = useState(true)
  const box = useRef<HTMLDivElement>(null)

  const filtered = useMemo(() => {
    const rank: Record<string, number> = { debug: 0, info: 1, warning: 2, error: 3 }
    const min = level === 'all' ? 0 : rank[level]
    return logs.filter((l) => (rank[l.level] ?? 1) >= min).slice(-800)
  }, [logs, level])

  useEffect(() => {
    if (open && follow && box.current) box.current.scrollTop = box.current.scrollHeight
  }, [filtered, open, follow])

  if (!open) return null
  return (
    <div className="slide-up fixed inset-x-0 bottom-0 z-40 flex h-[65dvh] flex-col sm:h-[42vh] border-t border-line-strong bg-black/95 backdrop-blur-xl">
      <div className="flex items-center justify-between gap-2 border-b border-line px-3 py-2 sm:px-4">
        <div className="flex min-w-0 items-center gap-2 overflow-x-auto sm:gap-3">
          <Segmented<Tab>
            size="sm"
            value={tab}
            onChange={setTab}
            options={[
              { value: 'logs', label: 'Logs' },
              {
                value: 'requests',
                label: (
                  <span className="flex items-center gap-1.5">
                    Requests
                    <span className="font-mono text-[10px] opacity-70">{requestCount}</span>
                    {running > 0 && <Loader2 className="size-3 animate-spin" />}
                  </span>
                ),
              },
            ]}
          />
          {tab === 'logs' && (
          <Segmented<Level>
            size="sm"
            value={level}
            onChange={setLevel}
            options={[
              { value: 'all', label: 'all' },
              { value: 'info', label: 'info' },
              { value: 'warning', label: 'warnings' },
              { value: 'error', label: 'errors' },
            ]}
          />
          )}
        </div>
        <div className="flex shrink-0 items-center gap-0.5 sm:gap-1">
          {tab === 'logs' && (
            <IconButton title="Follow" onClick={() => setFollow(!follow)} className={follow ? 'text-white' : ''}>
              <ArrowDownToLine className="size-4" />
            </IconButton>
          )}
          <IconButton
            title={tab === 'logs' ? 'Clear logs' : 'Clear finished requests'}
            onClick={() => (tab === 'logs' ? useStudio.setState({ logs: [] }) : api.clearRequests().catch(() => {}))}
          >
            <Trash2 className="size-4" />
          </IconButton>
          <IconButton title="Close" onClick={() => setOpen(false)}>
            <X className="size-4" />
          </IconButton>
        </div>
      </div>
      {tab === 'requests' ? (
        <RequestsView />
      ) : (
      <>
      <Downloads />
      <div ref={box} className="flex-1 overflow-auto px-3 py-2 font-mono text-[11.5px] leading-5 sm:px-4">
        {filtered.map((l, i) => (
          <div key={i} className="flex flex-col whitespace-pre-wrap break-words py-0.5 sm:flex-row sm:gap-3 sm:py-0">
            <span className="flex shrink-0 gap-3 sm:contents">
              <span className="shrink-0 text-neutral-600">{new Date(l.ts * 1000).toLocaleTimeString()}</span>
              <span className="truncate text-neutral-500 sm:w-28 sm:shrink-0">{l.source}</span>
            </span>
            <span className={cls(l.level === 'error' ? 'font-semibold text-white' : l.level === 'warning' ? 'text-neutral-200' : l.level === 'debug' ? 'text-neutral-600' : 'text-neutral-400')}>
              {l.level === 'error' ? '✖ ' : l.level === 'warning' ? '▲ ' : ''}
              {l.message}
            </span>
          </div>
        ))}
        {!filtered.length && <div className="py-6 text-neutral-600">No logs yet.</div>}
      </div>
      </>
      )}
    </div>
  )
}

/** Live model-weight downloads reported by the workers. */
function Downloads() {
  const downloads = useStudio((s) => s.downloads)
  const list = useMemo(
    () => Object.values(downloads).sort((a, b) => Number(a.done) - Number(b.done) || (b.total ?? 0) - (a.total ?? 0)),
    [downloads],
  )
  if (!list.length) return null
  const active = list.filter((d) => !d.done).length
  return (
    <div className="fade-in border-b border-line px-4 py-2.5">
      <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-neutral-500">
        <CloudDownload className="size-3.5" /> Model downloads {active > 0 && <span className="font-mono normal-case tracking-normal text-neutral-400">· {active} active</span>}
      </div>
      <div className="flex max-h-40 flex-col gap-2.5 overflow-auto pr-1">
        {list.map((d) => (
          <DownloadRow key={d.id} d={d} />
        ))}
      </div>
    </div>
  )
}

function DownloadRow({ d }: { d: DownloadEvent & { phase?: string } }) {
  const pct = d.total ? Math.min(1, d.downloaded / d.total) : null
  const remaining = d.total && d.rate > 0 ? Math.max(0, d.total - d.downloaded) / d.rate : null
  const width = d.done && !d.failed ? 1 : (pct ?? 0)
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between gap-3 font-mono text-[11px]">
        <span className="flex min-w-0 items-center gap-2">
          {d.failed ? <XCircle className="size-3.5 shrink-0" /> : d.done ? <CheckCircle2 className="size-3.5 shrink-0" /> : <Loader2 className="size-3.5 shrink-0 animate-spin" />}
          <span className="truncate text-neutral-200" title={d.name}>
            {d.name}
          </span>
          {d.phase === 'reconstructing' && !d.done && <span className="shrink-0 text-neutral-500">reconstructing</span>}
          {d.engine && <span className="hidden shrink-0 text-neutral-600 sm:inline">{d.engine}</span>}
        </span>
        <span className="shrink-0 text-neutral-400">
          {fmtBytes(d.downloaded)}
          {d.total ? ` / ${fmtBytes(d.total)}` : ''}
          {pct !== null && !d.done && ` · ${Math.floor(pct * 100)}%`}
          {!d.done && d.rate > 0 && ` · ${fmtBytes(d.rate)}/s`}
          {!d.done && remaining !== null && ` · ${fmtEta(remaining)} left`}
          {d.done && (d.failed ? ' · interrupted' : ' · done')}
        </span>
      </div>
      <div className="relative h-1.5 overflow-hidden rounded-full bg-white/10">
        {pct === null && !d.done ? (
          <div className="shimmer absolute inset-0" />
        ) : (
          <div className="bg-accent-gradient absolute inset-y-0 left-0 transition-[width] duration-300 ease-out" style={{ width: `${width * 100}%` }} />
        )}
      </div>
    </div>
  )
}
