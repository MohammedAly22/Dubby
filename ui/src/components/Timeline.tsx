import { useEffect, useMemo, useRef, useState } from 'react'
import { ZoomIn, ZoomOut } from 'lucide-react'
import { usePlayer } from '../player'
import { useStudio } from '../store'
import type { Project } from '../types'
import { cls, fmtTime } from '../utils'
import { IconButton } from './ui'

const STEPS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600]

export function Timeline({ project }: { project: Project }) {
  const wrap = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(600)
  const [zoom, setZoom] = useState(1)
  const time = usePlayer((s) => s.time)
  const playing = usePlayer((s) => s.playing)
  const seek = usePlayer((s) => s.seek)
  const selectedId = useStudio((s) => s.selectedId)
  const select = useStudio((s) => s.select)
  const preview = useStudio((s) => s.asrPreview)
  const clip = useStudio((s) => s.clipDraft)

  const duration = Math.max(project.source.duration ?? 0, project.segments.at(-1)?.end ?? 0, 1)

  useEffect(() => {
    const el = wrap.current
    if (!el) return
    const ro = new ResizeObserver(() => setWidth(el.clientWidth))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const pps = (width / duration) * zoom
  const total = duration * pps
  const step = STEPS.find((s) => s * pps >= 64) ?? 1200
  const ticks = useMemo(() => Array.from({ length: Math.floor(duration / step) + 1 }, (_, i) => i * step), [duration, step])

  useEffect(() => {
    const el = wrap.current
    if (!el || !playing || zoom === 1) return
    const x = time * pps
    if (x < el.scrollLeft + 20 || x > el.scrollLeft + el.clientWidth - 40) el.scrollLeft = x - el.clientWidth * 0.2
  }, [time, pps, playing, zoom])

  const onClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const el = wrap.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    seek((e.clientX - rect.left + el.scrollLeft) / pps)
  }

  const showPreview = preview && preview.projectId === project.id

  return (
    <div className="rounded-2xl border border-line bg-panel backdrop-blur-xl">
      <div className="flex items-center justify-between px-3 pt-2">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-neutral-500">Timeline</span>
        <div className="flex items-center gap-1">
          <span className="font-mono text-[11px] text-neutral-500">×{zoom}</span>
          <IconButton title="Zoom out" onClick={() => setZoom((z) => Math.max(1, z / 2))} disabled={zoom === 1}>
            <ZoomOut className="size-3.5" />
          </IconButton>
          <IconButton title="Zoom in" onClick={() => setZoom((z) => Math.min(64, z * 2))}>
            <ZoomIn className="size-3.5" />
          </IconButton>
        </div>
      </div>
      <div ref={wrap} className="relative overflow-x-auto overflow-y-hidden px-0 pb-2">
        <div className="relative cursor-crosshair" style={{ width: total, height: 104 }} onClick={onClick}>
          {/* ruler */}
          {ticks.map((t) => (
            <div key={t} className="absolute top-0 h-full border-l border-white/[.06]" style={{ left: t * pps }}>
              <span className="absolute top-0.5 left-1 font-mono text-[9px] text-neutral-600">{fmtTime(t, false)}</span>
            </div>
          ))}

          {/* voice clip range */}
          {clip.start !== null && clip.end !== null && clip.end > clip.start && (
            <div className="hatch absolute top-4 bottom-0 rounded border border-white/60" style={{ left: clip.start * pps, width: (clip.end - clip.start) * pps }} title="Reference voice clip" />
          )}

          {/* source lane */}
          <div className="absolute inset-x-0 top-5 h-11">
            {showPreview
              ? preview!.segments.map((s, i) => (
                  <div key={i} className="absolute top-0 h-full rounded-md border border-dashed border-white/30 bg-white/[.04]" style={{ left: s.start * pps, width: Math.max(2, (s.end - s.start) * pps) }} title={s.text} />
                ))
              : project.segments.map((s) => {
                  const translated = s.translation_status === 'done'
                  const active = time >= s.start && time < s.end
                  return (
                    <button
                      key={s.id}
                      type="button"
                      title={`${fmtTime(s.start)} → ${fmtTime(s.end)}\n${s.text}${s.translation ? `\n${s.translation}` : ''}`}
                      onClick={(e) => {
                        e.stopPropagation()
                        select(s.id)
                        seek(s.start)
                      }}
                      className={cls(
                        'absolute top-0 h-full overflow-hidden rounded-md border px-1 text-left text-[10px] leading-tight transition',
                        translated ? 'border-white/30 bg-white/[.13] text-neutral-200' : 'border-white/15 bg-white/[.05] text-neutral-400',
                        active && 'border-white/80',
                        selectedId === s.id && 'ring-2 ring-white',
                      )}
                      style={{ left: s.start * pps, width: Math.max(2, (s.end - s.start) * pps - 1) }}
                    >
                      {(s.end - s.start) * pps > 40 ? s.text : ''}
                    </button>
                  )
                })}
          </div>

          {/* dub lane */}
          <div className="absolute inset-x-0 top-[70px] h-5">
            {project.segments.map((s) => {
              if (s.tts.status !== 'done' || !s.tts.duration) {
                return s.tts.status === 'running' || s.tts.status === 'queued' ? (
                  <div key={s.id} className="shimmer absolute top-0 h-full rounded" style={{ left: s.start * pps, width: Math.max(2, (s.end - s.start) * pps - 1) }} />
                ) : null
              }
              const slot = s.end - s.start
              const fit = Math.min(s.tts.duration, slot)
              const over = Math.max(0, s.tts.duration - slot)
              return (
                <div key={s.id} className="absolute top-0 flex h-full" style={{ left: s.start * pps }} title={`dub ${s.tts.duration.toFixed(2)}s / slot ${slot.toFixed(2)}s`}>
                  <div className="h-full rounded-l bg-white" style={{ width: Math.max(2, fit * pps) }} />
                  {over > 0 && <div className="hatch h-full rounded-r border border-white/60" style={{ width: over * pps }} />}
                </div>
              )
            })}
          </div>

          {/* playhead */}
          <div className="pointer-events-none absolute top-0 bottom-0 w-px bg-white shadow-[0_0_8px_color-mix(in_srgb,var(--color-white)_60%,transparent)]" style={{ left: time * pps }}>
            <div className="absolute -top-0.5 -left-[3px] size-[7px] rotate-45 bg-white" />
          </div>
        </div>
        <div className="flex gap-4 px-3 pt-1 text-[10px] text-neutral-600">
          <span>▭ source segments</span>
          <span>▬ dubbed clips</span>
          <span>▨ overflow beyond slot</span>
        </div>
      </div>
    </div>
  )
}
