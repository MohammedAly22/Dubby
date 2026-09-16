import { useEffect, useMemo, useRef, useState } from 'react'
import { ZoomIn, ZoomOut } from 'lucide-react'
import { usePlayer } from '../player'
import { useStudio } from '../store'
import type { Project } from '../types'
import { cls, fmtTime } from '../utils'
import { IconButton } from './ui'

const STEPS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600]
const DRAG_THRESHOLD = 3 // px before a press on a segment turns into a scrub
const EDGE = 32 // px from the edge where scrubbing auto-scrolls a zoomed timeline

export function Timeline({ project }: { project: Project }) {
  const wrap = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(600)
  const [zoom, setZoom] = useState(1)
  const [scrubbing, setScrubbing] = useState(false)
  const time = usePlayer((s) => s.time)
  const playing = usePlayer((s) => s.playing)
  const seek = usePlayer((s) => s.seek)
  const selectedId = useStudio((s) => s.selectedId)
  const select = useStudio((s) => s.select)
  const preview = useStudio((s) => s.asrPreview)
  const clip = useStudio((s) => s.clipDraft)

  const press = useRef<{ x: number; id: number; moved: boolean } | null>(null)
  const swallowClick = useRef(false)
  const frame = useRef<number | null>(null)
  const target = useRef<number | null>(null)

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
    if (!el || !playing || zoom === 1 || scrubbing) return
    const x = time * pps
    if (x < el.scrollLeft + 20 || x > el.scrollLeft + el.clientWidth - 40) el.scrollLeft = x - el.clientWidth * 0.2
  }, [time, pps, playing, zoom, scrubbing])

  // keep the grabbing hand everywhere while scrubbing, even when the pointer leaves the timeline
  useEffect(() => {
    if (!scrubbing) return
    document.body.classList.add('scrubbing')
    return () => document.body.classList.remove('scrubbing')
  }, [scrubbing])

  useEffect(() => () => {
    if (frame.current !== null) cancelAnimationFrame(frame.current)
  }, [])

  const timeAt = (clientX: number) => {
    const el = wrap.current!
    const rect = el.getBoundingClientRect()
    return Math.max(0, Math.min(duration, (clientX - rect.left + el.scrollLeft) / pps))
  }

  // seek at most once per frame: setting video.currentTime on every pointermove stutters
  const scheduleSeek = (t: number) => {
    target.current = t
    if (frame.current !== null) return
    frame.current = requestAnimationFrame(() => {
      frame.current = null
      if (target.current !== null) seek(target.current)
    })
  }

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return
    swallowClick.current = false
    const onSegment = !!(e.target as HTMLElement).closest('[data-segment]')
    press.current = { x: e.clientX, id: e.pointerId, moved: !onSegment }
    if (!onSegment) {
      // pressing empty track grabs the playhead right away
      e.currentTarget.setPointerCapture(e.pointerId)
      setScrubbing(true)
      scheduleSeek(timeAt(e.clientX))
    }
  }

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const p = press.current
    if (!p || p.id !== e.pointerId) return
    if (!p.moved) {
      if (Math.abs(e.clientX - p.x) < DRAG_THRESHOLD) return
      // a press on a segment became a drag: scrub instead of selecting
      p.moved = true
      e.currentTarget.setPointerCapture(e.pointerId)
      setScrubbing(true)
    }
    const el = wrap.current
    if (el && zoom > 1) {
      const rect = el.getBoundingClientRect()
      if (e.clientX > rect.right - EDGE) el.scrollLeft += 14
      else if (e.clientX < rect.left + EDGE) el.scrollLeft -= 14
    }
    scheduleSeek(timeAt(e.clientX))
  }

  const endPress = (e: React.PointerEvent<HTMLDivElement>) => {
    const p = press.current
    if (!p || p.id !== e.pointerId) return
    press.current = null
    if (p.moved) {
      swallowClick.current = true
      if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId)
    }
    setScrubbing(false)
  }

  const showPreview = preview && preview.projectId === project.id

  return (
    <div className="rounded-2xl border border-line bg-panel backdrop-blur-xl">
      <div className="flex items-center justify-between px-3 pt-2">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-neutral-500">Timeline</span>
        <div className="flex items-center gap-1">
          {scrubbing && <span className="fade-in font-mono text-[11px] text-neutral-300">{fmtTime(time)}</span>}
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
        <div
          className={cls('relative touch-none select-none', scrubbing ? 'cursor-grabbing' : 'cursor-grab')}
          style={{ width: total, height: 104 }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endPress}
          onPointerCancel={endPress}
          title="Drag to scrub"
        >
          {/* ruler */}
          {ticks.map((t) => (
            <div key={t} className="absolute top-0 h-full border-l border-white/[.06]" style={{ left: t * pps }}>
              <span className="absolute top-0.5 left-1 font-mono text-[9px] text-neutral-600">{fmtTime(t, false)}</span>
            </div>
          ))}

          {/* voice clip range */}
          {clip.start !== null && clip.end !== null && clip.end > clip.start && (
            <div className="hatch pointer-events-none absolute top-4 bottom-0 rounded border border-white/60" style={{ left: clip.start * pps, width: (clip.end - clip.start) * pps }} title="Reference voice clip" />
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
                      data-segment
                      title={`${fmtTime(s.start)} → ${fmtTime(s.end)}\n${s.text}${s.translation ? `\n${s.translation}` : ''}`}
                      onClick={(e) => {
                        e.stopPropagation()
                        if (swallowClick.current) {
                          swallowClick.current = false // this "click" ended a scrub
                          return
                        }
                        select(s.id)
                        seek(s.start)
                      }}
                      className={cls(
                        'absolute top-0 h-full overflow-hidden rounded-md border px-1 text-left text-[10px] leading-tight transition',
                        scrubbing ? 'cursor-grabbing' : 'cursor-pointer',
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
          <div className="pointer-events-none absolute inset-x-0 top-[70px] h-5">
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
          <div
            className={cls(
              'pointer-events-none absolute top-0 bottom-0 w-px bg-white shadow-[0_0_8px_color-mix(in_srgb,var(--color-white)_60%,transparent)]',
              scrubbing && 'w-0.5 shadow-[0_0_14px_color-mix(in_srgb,var(--color-white)_80%,transparent)]',
            )}
            style={{ left: time * pps }}
          >
            <div className={cls('absolute -top-0.5 -left-[3px] size-[7px] rotate-45 bg-white transition-transform duration-150', scrubbing && 'scale-150')} />
          </div>
        </div>
        <div className="flex gap-4 px-3 pt-1 text-[10px] text-neutral-600">
          <span>▭ source segments</span>
          <span>▬ dubbed clips</span>
          <span>▨ overflow beyond slot</span>
          <span className="ml-auto hidden sm:inline">drag anywhere to scrub</span>
        </div>
      </div>
    </div>
  )
}
