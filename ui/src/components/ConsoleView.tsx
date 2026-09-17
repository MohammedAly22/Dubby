import { useEffect, useMemo, useRef } from 'react'
import type { ConsoleRecord, ConsoleSpan } from '../types'
import { cls } from '../utils'

export type ConsoleFilter = 'all' | 'warning' | 'error'

/** rich colour names from the terminal reporter → the drawer's palette (theme-aware) */
const COLOR: Record<string, string> = {
  green: 'con-green',
  yellow: 'con-yellow',
  red: 'con-red',
  white: 'text-white',
  grey30: 'text-neutral-700',
  grey35: 'text-neutral-700',
  grey42: 'text-neutral-600',
  grey50: 'text-neutral-500',
  grey62: 'text-neutral-400',
  grey70: 'text-neutral-300',
}

const RTL_TEXT = /[֐-ࣿיִ-﷿ﹰ-﻿]/

function Spans({ spans }: { spans: ConsoleSpan[] }) {
  return (
    <>
      {spans.map((s, i) => {
        const className = cls(s.c ? (COLOR[s.c] ?? 'text-neutral-300') : 'text-neutral-200', s.b && 'font-bold')
        if (!RTL_TEXT.test(s.t)) {
          return (
            <span key={i} className={className}>
              {s.t}
            </span>
          )
        }
        // Arabic (a translation, a clip line): its own right-to-left run in a font with joined letters
        const lead = s.t.match(/^\s*/)?.[0] ?? ''
        return (
          <span key={i} className={className}>
            {lead}
            <bdi dir="auto" className="font-arabic">
              {s.t.slice(lead.length)}
            </bdi>
          </span>
        )
      })}
    </>
  )
}

const TONE_RANK: Record<string, number> = { warning: 1, error: 2 }

/** The studio terminal, line for line: stage rules, progress bars, clips, ✅ / ⏸ / ❌ and worker messages. */
export function ConsoleView({ records, filter, follow }: { records: ConsoleRecord[]; filter: ConsoleFilter; follow: boolean }) {
  const box = useRef<HTMLDivElement>(null)
  const shown = useMemo(() => {
    if (filter === 'all') return records
    const min = filter === 'warning' ? 1 : 2
    return records.filter((r) => (TONE_RANK[r.tone ?? (r.kind === 'panel' ? 'error' : '')] ?? 0) >= min)
  }, [records, filter])

  useEffect(() => {
    if (follow && box.current) box.current.scrollTop = box.current.scrollHeight
  }, [shown, follow])

  return (
    <div ref={box} className="flex-1 overflow-auto px-3 py-2 font-mono text-[11.5px] leading-5 sm:px-4">
      {shown.map((r) => (
        <Record key={r.id} r={r} />
      ))}
      {!shown.length && <div className="py-6 text-neutral-600">{records.length ? 'Nothing matches this filter.' : 'Nothing yet — studio activity streams here, exactly like the terminal.'}</div>}
    </div>
  )
}

function Record({ r }: { r: ConsoleRecord }) {
  if (r.kind === 'rule') {
    return (
      <div className="my-1 flex items-center gap-2 whitespace-pre" title={new Date(r.ts * 1000).toLocaleTimeString()}>
        <span className="h-px flex-1 bg-neutral-700" />
        <span className="shrink-0">
          <Spans spans={r.spans ?? []} />
        </span>
        <span className="h-px flex-1 bg-neutral-700" />
      </div>
    )
  }
  if (r.kind === 'panel') {
    return (
      <div className={cls('my-1.5 rounded-md border px-3 py-2', r.tone === 'red' ? 'con-border-red' : 'border-neutral-700')}>
        <div className={cls('mb-1 font-bold', r.tone === 'red' ? 'con-red' : 'text-white')}>{r.title}</div>
        {(r.lines ?? []).map((line, i) => (
          <div key={i} className="whitespace-pre-wrap break-words">
            <Spans spans={line} />
          </div>
        ))}
      </div>
    )
  }
  if (r.kind === 'table') {
    return (
      <div className="my-1.5 overflow-x-auto">
        <div className="mb-1 font-bold text-white">{r.title}</div>
        <table className="border-collapse text-left">
          {r.columns && r.columns.length > 0 && (
            <thead>
              <tr>
                {r.columns.map((c) => (
                  <th key={c} className="border border-neutral-800 px-2 py-0.5 font-bold text-white">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
          )}
          <tbody>
            {(r.rows ?? []).map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td key={j} className={cls('border border-neutral-800 px-2 py-0.5', j === row.length - 1 ? 'max-w-[70ch] truncate text-white' : 'text-neutral-400')} title={cell}>
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }
  return (
    <div className="whitespace-pre-wrap break-words" title={new Date(r.ts * 1000).toLocaleTimeString()}>
      <Spans spans={r.spans ?? []} />
    </div>
  )
}
