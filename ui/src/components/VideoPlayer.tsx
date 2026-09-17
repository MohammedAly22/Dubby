import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Captions, Clapperboard, Film, Headphones, Maximize2, Minimize2 } from 'lucide-react'
import { fileUrl } from '../api'
import { CaptionOverlay, type ContentRect } from './CaptionOverlay'
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

  // ------------------------------------------------------------------ fullscreen
  // The whole stage (video + caption overlay) goes fullscreen: a fullscreen <video> element would hide the captions.
  const stage = useRef<HTMLDivElement>(null)
  const [fullscreen, setFullscreen] = useState(false)
  const [pseudoFullscreen, setPseudoFullscreen] = useState(false) // iPhone Safari: no element fullscreen API
  const isFull = fullscreen || pseudoFullscreen

  const toggleFullscreen = useCallback(async () => {
    const el = stage.current
    if (!el) return
    if (document.fullscreenElement || (document as any).webkitFullscreenElement) {
      await (document.exitFullscreen?.() ?? (document as any).webkitExitFullscreen?.())?.catch?.(() => {})
      return
    }
    if (pseudoFullscreen) return setPseudoFullscreen(false)
    const request = el.requestFullscreen?.bind(el) ?? (el as any).webkitRequestFullscreen?.bind(el)
    if (!request) return setPseudoFullscreen(true)
    try {
      await request({ navigationUI: 'hide' })
      await (screen.orientation as any)?.lock?.('landscape').catch(() => {})
    } catch {
      setPseudoFullscreen(true)
    }
  }, [pseudoFullscreen])

  useEffect(() => {
    const sync = () => {
      const active = document.fullscreenElement ?? (document as any).webkitFullscreenElement
      setFullscreen(active === stage.current)
      // a browser's own fullscreen button (Firefox) fullscreens the bare video: move the captions along
      if (active && active === videoRef.current) {
        document.exitFullscreen().then(() => stage.current?.requestFullscreen()).catch(() => setPseudoFullscreen(true))
      }
    }
    document.addEventListener('fullscreenchange', sync)
    document.addEventListener('webkitfullscreenchange', sync)
    return () => {
      document.removeEventListener('fullscreenchange', sync)
      document.removeEventListener('webkitfullscreenchange', sync)
    }
  }, [])

  useEffect(() => {
    if (!pseudoFullscreen) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setPseudoFullscreen(false)
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', onKey)
    // position: fixed is trapped by transformed / filtered ancestors and hidden behind their stacking contexts:
    // neutralize those on the way up while the in-page fullscreen is open
    const touched: { el: HTMLElement; css: string }[] = []
    for (let el = stage.current?.parentElement; el && el !== document.body; el = el.parentElement) {
      touched.push({ el, css: el.style.cssText })
      el.style.setProperty('transform', 'none', 'important')
      el.style.setProperty('filter', 'none', 'important')
      el.style.setProperty('backdrop-filter', 'none', 'important')
      el.style.setProperty('contain', 'none', 'important')
      el.style.setProperty('will-change', 'auto', 'important')
      el.style.setProperty('animation', 'none', 'important')
      if (getComputedStyle(el).position === 'static') el.style.setProperty('position', 'relative', 'important')
      el.style.setProperty('z-index', '2147483000', 'important')
    }
    return () => {
      document.body.style.overflow = overflow
      window.removeEventListener('keydown', onKey)
      for (const { el, css } of touched) el.style.cssText = css
    }
  }, [pseudoFullscreen])

  useEffect(() => {
    // iOS plays fullscreen in its native player, which can't show our captions: use the in-page fullscreen instead
    const v = videoRef.current as any
    if (!v) return
    const onNative = () => {
      v.webkitExitFullscreen?.()
      setPseudoFullscreen(true)
    }
    v.addEventListener('webkitbeginfullscreen', onNative)
    return () => v.removeEventListener('webkitbeginfullscreen', onNative)
  }, [src])

  // where the picture sits inside the stage (letterboxing), so captions scale with the picture like in the export
  const [rect, setRect] = useState<ContentRect>({ left: 0, top: 0, width: 0, height: 0 })
  const measure = useCallback(() => {
    const el = stage.current
    const v = videoRef.current
    if (!el) return
    const cw = el.clientWidth
    const ch = v?.clientHeight || el.clientHeight
    const vw = v?.videoWidth || 16
    const vh = v?.videoHeight || 9
    const scale = Math.min(cw / vw, ch / vh)
    const width = vw * scale
    const height = vh * scale
    const top = (v?.offsetTop ?? 0) + (ch - height) / 2
    setRect((r) => {
      const next = { left: (cw - width) / 2, top, width, height }
      return Math.abs(r.width - next.width) < 0.5 && Math.abs(r.top - next.top) < 0.5 && Math.abs(r.left - next.left) < 0.5 ? r : next
    })
  }, [])
  useEffect(() => {
    const el = stage.current
    if (!el) return
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    if (videoRef.current) observer.observe(videoRef.current)
    measure()
    return () => observer.disconnect()
  }, [measure, src, isFull])

  // ------------------------------------------------------------------ captions
  const idx = segmentIndexAt(project.segments, time)
  const seg = idx >= 0 ? project.segments[idx] : null
  // in the rendered video a dub clip may sit (or run) outside its source segment: follow the clip placement
  const dubSeg = useMemo(() => {
    if (effectiveMode !== 'render') return seg
    const clip = (project.render.clips ?? []).find((c) => time >= c.start && time < c.end + 0.15)
    return clip ? (project.segments.find((s) => s.id === clip.id) ?? null) : null
  }, [effectiveMode, seg, project.render.clips, project.segments, time])
  const dubWords = effectiveMode === 'render' ? (dubSeg?.dub_words ?? []) : []

  return (
    <div className="flex flex-col gap-2">
      <div
        ref={stage}
        className={cls(
          'group relative overflow-hidden bg-[#000]',
          isFull ? 'flex h-full w-full items-center justify-center' : 'rounded-2xl border border-line',
        )}
        style={pseudoFullscreen ? { position: 'fixed', top: 0, left: 0, width: '100vw', height: '100dvh', zIndex: 2147483001, borderRadius: 0 } : undefined}
      >
        {src ? (
          <video
            key={src}
            ref={videoRef}
            src={src}
            controls
            controlsList="nofullscreen"
            playsInline
            preload="metadata"
            className={cls('bg-[#000]', isFull ? 'h-full max-h-full w-full object-contain' : 'aspect-video w-full')}
            onDoubleClick={toggleFullscreen}
            onLoadedMetadata={(e) => {
              if (resumeAt.current) e.currentTarget.currentTime = resumeAt.current
              usePlayer.setState({ duration: e.currentTarget.duration })
              usePlayer.getState().setVideo(e.currentTarget)
              measure()
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
        {captions && (
          <CaptionOverlay
            rect={rect}
            time={time}
            original={effectiveMode !== 'dub' ? seg : null}
            dub={dubSeg}
            dubWords={dubWords}
            source={project.settings.source_language}
            target={project.settings.target}
          />
        )}
        {src && (
          <button
            type="button"
            title={isFull ? 'Exit fullscreen (Esc)' : 'Fullscreen with captions'}
            onClick={toggleFullscreen}
            className={cls(
              'absolute top-2 right-2 z-10 grid size-9 place-items-center rounded-full bg-[#000]/60 text-[#fff] backdrop-blur transition-opacity hover:bg-[#000]/80 focus-visible:opacity-100',
              isFull ? 'opacity-70 hover:opacity-100' : 'opacity-100 sm:opacity-0 sm:group-hover:opacity-100',
            )}
          >
            {isFull ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
          </button>
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
          <IconButton title="Fullscreen with captions" onClick={toggleFullscreen}>
            <Maximize2 className="size-4" />
          </IconButton>
        </div>
      </div>
    </div>
  )
}
