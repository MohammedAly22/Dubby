import { memo, useEffect, useRef, useState } from 'react'
import { ArrowRight, Combine, Mic, Play, Scissors, Trash2 } from 'lucide-react'
import { api } from '../api'
import { EnginePicker } from '../components/EnginePicker'
import { StageHeader } from '../components/StageHeader'
import { AutoTextarea, Button, Empty, IconButton, Switch, inputCls } from '../components/ui'
import { usePlayer } from '../player'
import { useStudio } from '../store'
import type { Project, Segment } from '../types'
import { cls, fmtTime, isBusy } from '../utils'

export function TranscribePanel({ project, onNext }: { project: Project; onNext: () => void }) {
  const st = project.stages.asr
  const busy = isBusy(st)
  const runStage = useStudio((s) => s.runStage)
  const cancelStage = useStudio((s) => s.cancelStage)
  const saveChoice = useStudio((s) => s.saveChoice)
  const patchSettings = useStudio((s) => s.patchSettings)
  const preview = useStudio((s) => s.asrPreview)
  const confirm = useStudio((s) => s.confirm)
  const follow = usePlayer((s) => s.follow)
  const setFollow = usePlayer((s) => s.setFollow)
  const [advanced, setAdvanced] = useState(false)
  const ready = project.stages.download?.status === 'done'
  const words = project.segments.reduce((n, s) => n + s.words.length, 0)

  return (
    <div className="flex flex-col gap-6">
      <StageHeader
        icon="🎙️"
        title="Transcription & alignment"
        subtitle={`Speech → ${project.settings.source_language === 'en' ? 'English' : 'Arabic'} text with word-level timestamps, regrouped into dubbing chunks.`}
        state={st}
        actions={
          busy ? (
            <Button onClick={() => cancelStage('asr')}>Cancel</Button>
          ) : (
            <>
              <Button variant={project.segments.length ? 'secondary' : 'primary'} icon={<Mic className="size-4" />} disabled={!ready} onClick={async () => {
                if (project.segments.length) {
                  const ok = await confirm({
                    title: 'Re-transcribe this video?',
                    message: `All ${project.segments.length} segments are rebuilt from the audio, so every translation and generated voice clip is discarded along with your edits.`,
                    confirmLabel: 'Re-transcribe',
                    tone: 'danger',
                    icon: '🎙️',
                  })
                  if (!ok) return
                }
                runStage('asr')
              }}>
                {project.segments.length ? 'Re-transcribe' : 'Transcribe'}
              </Button>
              {project.segments.length > 0 && (
                <Button variant="primary" icon={<ArrowRight className="size-4" />} onClick={onNext}>
                  Translate
                </Button>
              )}
            </>
          )
        }
      />

      <EnginePicker
        kind="asr"
        choice={project.settings.asr}
        source={project.settings.source_language}
        disabled={busy}
        onChange={(c) => saveChoice('asr', c)}
      />

      <div className="rounded-2xl border border-line">
        <button className="w-full px-3 py-2 text-left text-xs text-neutral-400 hover:text-white" onClick={() => setAdvanced(!advanced)}>
          {advanced ? '▾' : '▸'} Dubbing chunk rules
        </button>
        {advanced && (
          <div className="grid gap-3 border-t border-line p-3 sm:grid-cols-3">
            {(
              [
                ['max_chunk_seconds', 'Max chunk (s)', 3, 30, 0.5],
                ['min_chunk_seconds', 'Min chunk (s)', 0.3, 6, 0.1],
                ['max_word_gap', 'Split on pause (s)', 0.2, 3, 0.1],
              ] as const
            ).map(([key, label, min, max, step]) => (
              <label key={key} className="flex flex-col gap-1.5">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-neutral-500">{label}</span>
                <input type="number" className={cls(inputCls, 'font-mono')} min={min} max={max} step={step} value={project.settings[key]} onChange={(e) => patchSettings({ [key]: Number(e.target.value) })} />
              </label>
            ))}
          </div>
        )}
      </div>

      {busy && preview?.projectId === project.id && preview.segments.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-neutral-500">Live transcript · {preview.segments.length} chunks</div>
          {preview.segments.slice(-40).map((s, i) => (
            <div key={i} className="fade-in flex gap-3 rounded-xl border border-dashed border-line-strong px-3 py-2 text-sm text-neutral-300">
              <span className="shrink-0 font-mono text-[11px] text-neutral-500">{fmtTime(s.start)}</span>
              <span dir="auto">{s.text}</span>
            </div>
          ))}
        </div>
      )}

      {project.segments.length > 0 ? (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-neutral-500">
              {project.segments.length} chunks · {words} aligned words
            </span>
            <Switch checked={follow} onChange={setFollow} label={<span className="text-xs">Follow playback</span>} />
          </div>
          {project.segments.map((s, i) => (
            <TranscriptRow key={s.id} seg={s} index={i} projectId={project.id} last={i === project.segments.length - 1} />
          ))}
        </div>
      ) : (
        !busy && (
          <Empty icon={<Mic className="size-8" />} title="No transcript yet">
            Pick an engine and press Transcribe. Chunks appear here with their word timings as soon as the engine produces them.
          </Empty>
        )
      )}
    </div>
  )
}

const TranscriptRow = memo(function TranscriptRow({ seg, index, projectId, last }: { seg: Segment; index: number; projectId: string; last: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  const active = usePlayer((s) => s.time >= seg.start && s.time < seg.end)
  const activeWord = usePlayer((s) => (s.time >= seg.start && s.time < seg.end ? seg.words.findIndex((w) => s.time >= w.start && s.time < w.end) : -1))
  const follow = usePlayer((s) => s.follow && s.playing)
  const selected = useStudio((s) => s.selectedId === seg.id)
  const select = useStudio((s) => s.select)
  const updateSegment = useStudio((s) => s.updateSegment)
  const toast = useStudio((s) => s.toast)
  const confirm = useStudio((s) => s.confirm)
  const seek = usePlayer((s) => s.seek)
  const playRange = usePlayer((s) => s.playRange)
  const [splitMode, setSplitMode] = useState(false)

  useEffect(() => {
    if ((active && follow) || selected) ref.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [active, follow, selected])

  const act = (fn: () => Promise<unknown>) => fn().catch((e) => toast(e.message, 'error'))

  return (
    <div
      ref={ref}
      onClick={() => select(seg.id)}
      className={cls('row-auto group rounded-2xl border p-3 transition', active ? 'border-white/70 bg-white/[.04]' : selected ? 'border-neutral-500' : 'border-line hover:border-line-strong')}
    >
      <div className="flex items-center justify-between gap-2">
        <button className="flex items-center gap-2 font-mono text-[11px] text-neutral-500 hover:text-white" onClick={() => seek(seg.start)}>
          <span className="text-neutral-600">#{index + 1}</span>
          {fmtTime(seg.start)} → {fmtTime(seg.end)}
          <span className="text-neutral-600">{(seg.end - seg.start).toFixed(1)}s</span>
        </button>
        <div className="flex items-center gap-0.5 opacity-60 transition group-hover:opacity-100">
          <IconButton title="Play segment" onClick={() => playRange(seg.start, seg.end)}>
            <Play className="size-3.5" />
          </IconButton>
          <IconButton title="Split at a word" onClick={() => setSplitMode(!splitMode)} className={splitMode ? 'bg-white text-black hover:bg-white hover:text-black' : ''} disabled={seg.words.length < 2}>
            <Scissors className="size-3.5" />
          </IconButton>
          <IconButton title="Merge with next" disabled={last} onClick={() => act(() => api.merge(projectId, seg.id))}>
            <Combine className="size-3.5" />
          </IconButton>
          <IconButton
            title="Delete segment"
            onClick={async () => {
              const ok = await confirm({
                title: 'Delete this segment?',
                message: 'Its text, translation and generated voice clip are removed. The surrounding segments and the original audio stay as they are.',
                confirmLabel: 'Delete segment',
                tone: 'danger',
              })
              if (ok) act(() => api.deleteSegment(projectId, seg.id))
            }}
          >
            <Trash2 className="size-3.5" />
          </IconButton>
        </div>
      </div>

      <AutoTextarea value={seg.text} onCommit={(text) => updateSegment(seg.id, { text })} className="mt-1" />

      {seg.words.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1 px-1">
          {seg.words.map((w, i) => (
            <button
              key={i}
              title={`${fmtTime(w.start)} → ${fmtTime(w.end)}${w.score != null ? ` · confidence ${(w.score * 100).toFixed(0)}%` : ''}`}
              onClick={(e) => {
                e.stopPropagation()
                if (splitMode) {
                  if (i === 0) return
                  setSplitMode(false)
                  act(() => api.split(projectId, seg.id, i))
                } else seek(w.start, true)
              }}
              className={cls(
                'rounded-md border px-1.5 py-0.5 text-[11px] leading-4 transition',
                i === activeWord ? 'border-white bg-white text-black' : 'border-line text-neutral-400 hover:border-neutral-500 hover:text-white',
                splitMode && i > 0 && 'border-dashed hover:border-l-2 hover:border-l-white',
                w.score != null && w.score < 0.4 && i !== activeWord && 'text-neutral-600',
              )}
              dir="auto"
            >
              {w.text}
              <span className="ml-1 font-mono text-[9px] text-neutral-600">{w.start.toFixed(1)}</span>
            </button>
          ))}
        </div>
      )}
      {splitMode && <div className="mt-2 px-1 text-[11px] text-neutral-400">Click the word that should start the new segment.</div>}
    </div>
  )
})
