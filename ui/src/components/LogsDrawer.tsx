import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowDownToLine, Trash2, X } from 'lucide-react'
import { useStudio } from '../store'
import { cls } from '../utils'
import { IconButton, Segmented } from './ui'

type Level = 'all' | 'info' | 'warning' | 'error'

export function LogsDrawer() {
  const open = useStudio((s) => s.logsOpen)
  const setOpen = useStudio((s) => s.setLogsOpen)
  const logs = useStudio((s) => s.logs)
  const [level, setLevel] = useState<Level>('info')
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
    <div className="slide-up fixed inset-x-0 bottom-0 z-40 flex h-[42vh] flex-col border-t border-line-strong bg-black/95 backdrop-blur-xl">
      <div className="flex items-center justify-between border-b border-line px-4 py-2">
        <div className="flex items-center gap-3">
          <span className="text-xs font-semibold uppercase tracking-wider text-neutral-400">Studio logs</span>
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
        </div>
        <div className="flex items-center gap-1">
          <IconButton title="Follow" onClick={() => setFollow(!follow)} className={follow ? 'text-white' : ''}>
            <ArrowDownToLine className="size-4" />
          </IconButton>
          <IconButton title="Clear" onClick={() => useStudio.setState({ logs: [] })}>
            <Trash2 className="size-4" />
          </IconButton>
          <IconButton title="Close" onClick={() => setOpen(false)}>
            <X className="size-4" />
          </IconButton>
        </div>
      </div>
      <div ref={box} className="flex-1 overflow-auto px-4 py-2 font-mono text-[11.5px] leading-5">
        {filtered.map((l, i) => (
          <div key={i} className="flex gap-3 whitespace-pre-wrap break-all">
            <span className="shrink-0 text-neutral-600">{new Date(l.ts * 1000).toLocaleTimeString()}</span>
            <span className="w-28 shrink-0 truncate text-neutral-500">{l.source}</span>
            <span className={cls(l.level === 'error' ? 'font-semibold text-white' : l.level === 'warning' ? 'text-neutral-200' : l.level === 'debug' ? 'text-neutral-600' : 'text-neutral-400')}>
              {l.level === 'error' ? '✖ ' : l.level === 'warning' ? '▲ ' : ''}
              {l.message}
            </span>
          </div>
        ))}
        {!filtered.length && <div className="py-6 text-neutral-600">No logs yet.</div>}
      </div>
    </div>
  )
}
