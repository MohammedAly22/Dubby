import { useEffect, useMemo, useRef } from 'react'
import { Captions, Clapperboard, Film, Headphones } from 'lucide-react'
import { fileUrl } from '../api'
import { usePlayer, type PlayerMode } from '../player'
import type { Project } from '../types'
import { cls, fmtTime, segmentIndexAt } from '../utils'
import { IconButton, Segmented } from './ui'

export function VideoPlayer({ project }: { project: Project }) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const mode = usePlayer((s) => s.mode)
  const setMode = usePlayer((s) => s.setMode)
  const captions = usePlayer((s) => s.captions)
  const setCaptions = usePlayer((s) => s.setCaptions)
  const bgVolume = usePlayer((s) => s.bgVolume)
  const setBgVolume = usePlayer((s) => s.setBgVolume)
  const time = usePlayer((s) => s.time)

  const voiced = useMemo(() => project.segments.filter((s) => s.tts.status === 'done' && s.tts.audio), [project.segments])
  const hasDub = voiced.length > 0
  const hasRender = !!project.render.video
  const effectiveMode: PlayerMode = mode === 'render' && !hasRender ? 'original' : mode === 'dub' && !hasDub ? 'original' : mode

  const src =
    effectiveMode === 'render' && project.render.video
      ? fileUrl(project.id, project.render.video, project.render.version)
      : project.source.video
        ? fileUrl(project.id, project.source.video)
        : undefined

  const resumeAt = useRef(0)
  useEffect(() => {
    usePlayer.getState().setVideo(videoRef.current)
    return () => usePlayer.getState().setVideo(null)
  }, [src])

  // ------------------------------------------------------------------ clock + dub preview
  const audios = useRef(new Map<string, HTMLAudioElement>())
  const current = useRef<HTMLAudioElement | null>(null)
  useEffect(() => {
    let raf = 0
    const tick = () => {
      const v = videoRef.current
      if (v) {
        const t = v.currentTime
        const st = usePlayer.getState()
        st.setTime(t)
        if (st.stopAt !== null && t >= st.stopAt) {
          v.pause()
          usePlayer.setState({ stopAt: null })
        }
        if (effectiveMode === 'dub') {
          const seg = voiced.find((s) => t >= s.start && t < s.start + Math.max(s.tts.duration ?? 0, 0.05))
          if (v.paused || !seg) {
            if (current.current && !current.current.paused) current.current.pause()
            if (!seg) current.current = null
          } else {
            const key = `${seg.id}:${seg.tts.version}`
            let a = audios.current.get(key)
            if (!a) {
              a = new Audio(fileUrl(project.id, seg.tts.audio!, seg.tts.version))
              a.preload = 'auto'
              audios.current.set(key, a)
            }
            const offset = t - seg.start
            const within = Number.isFinite(a.duration) ? offset < a.duration - 0.05 : true
            if (current.current !== a) {
              current.current?.pause()
              current.current = a
              a.currentTime = offset
              a.play().catch(() => {})
            } else if (a.paused && within) {
              a.currentTime = offset
              a.play().catch(() => {})
            } else if (!a.paused && Math.abs(a.currentTime - offset) > 0.3) {
              a.currentTime = offset
            }
            a.playbackRate = v.playbackRate
          }
        }
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(raf)
      current.current?.pause()
      current.current = null
    }
  }, [effectiveMode, voiced, project.id])

  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    v.volume = effectiveMode === 'dub' ? bgVolume : 1
  }, [effectiveMode, bgVolume, src])

  const changeMode = (m: PlayerMode) => {
    resumeAt.current = videoRef.current?.currentTime ?? 0
    setMode(m)
  }

  // ------------------------------------------------------------------ captions
  const idx = segmentIndexAt(project.segments, time)
  const seg = idx >= 0 ? project.segments[idx] : null

  return (
    <div className="flex flex-col gap-2">
      <div className="group relative overflow-hidden rounded-2xl border border-line bg-black">
        {src ? (
          <video
            key={src}
            ref={videoRef}
            src={src}
            controls
            playsInline
            preload="metadata"
            className="aspect-video w-full bg-black"
            onLoadedMetadata={(e) => {
              if (resumeAt.current) e.currentTarget.currentTime = resumeAt.current
              usePlayer.setState({ duration: e.currentTarget.duration })
              usePlayer.getState().setVideo(e.currentTarget)
            }}
            onPlay={() => usePlayer.setState({ playing: true })}
            onPause={() => usePlayer.setState({ playing: false })}
          />
        ) : (
          <div className="grain flex aspect-video w-full items-center justify-center text-sm text-neutral-500">
            {project.source.thumbnail ? <img src={project.source.thumbnail} alt="" className="absolute inset-0 size-full object-cover opacity-25 grayscale" /> : null}
            <span className="relative">Preparing video…</span>
          </div>
        )}
        {captions && seg && effectiveMode !== 'render' && (
          <div className="pointer-events-none absolute inset-x-0 bottom-14 flex flex-col items-center gap-1 px-6">
            {effectiveMode === 'original' && (
              <div className="max-w-[92%] rounded-lg bg-black/75 px-3 py-1.5 text-center text-sm leading-relaxed backdrop-blur" dir="auto">
                {seg.words.length
                  ? seg.words.map((w, i) => (
                      <span key={i} className={cls('transition-colors', time >= w.start && time < w.end ? 'text-white' : time >= w.end ? 'text-neutral-300' : 'text-neutral-500')}>
                        {w.text}{' '}
                      </span>
                    ))
                  : seg.text}
              </div>
            )}
            {seg.translation && (
              <div className="arabic max-w-[92%] rounded-lg bg-white px-3 py-1 text-center text-[15px] font-medium text-black">{seg.translation}</div>
            )}
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 px-1">
        <Segmented<PlayerMode>
          size="sm"
          value={effectiveMode}
          onChange={changeMode}
          options={[
            { value: 'original', label: <span className="flex items-center gap-1"><Film className="size-3" /> Original</span> },
            { value: 'dub', label: <span className="flex items-center gap-1"><Headphones className="size-3" /> Dub preview</span>, disabled: !hasDub, title: hasDub ? 'Plays generated clips in sync with the video' : 'Generate voices first' },
            { value: 'render', label: <span className="flex items-center gap-1"><Clapperboard className="size-3" /> Rendered</span>, disabled: !hasRender, title: hasRender ? `Render v${project.render.version}` : 'Render first' },
          ]}
        />
        <div className="flex items-center gap-3">
          {effectiveMode === 'dub' && (
            <label className="flex items-center gap-2 text-[11px] text-neutral-500">
              original
              <input type="range" min={0} max={1} step={0.01} value={bgVolume} onChange={(e) => setBgVolume(Number(e.target.value))} className="w-20" />
            </label>
          )}
          <span className="font-mono text-xs text-neutral-400">{fmtTime(time)}</span>
          <IconButton title="Toggle captions" onClick={() => setCaptions(!captions)} className={captions ? 'text-white' : ''}>
            <Captions className="size-4" />
          </IconButton>
        </div>
      </div>
    </div>
  )
}
