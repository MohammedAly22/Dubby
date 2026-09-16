import { memo } from 'react'
import { AlertTriangle, ArrowRight, Languages, Play, RefreshCw } from 'lucide-react'
import { EnginePicker } from '../components/EnginePicker'
import { isArabic, isRtl, TARGET_OPTIONS } from '../components/Flags'
import { Select } from '../components/Select'
import { StageHeader } from '../components/StageHeader'
import { AutoTextarea, Button, Empty, IconButton, Progress, Segmented, StatusIcon } from '../components/ui'
import { usePlayer } from '../player'
import { useStudio } from '../store'
import type { Project, Segment, TargetDialect } from '../types'
import { cls, fmtTime, isBusy, translationStale } from '../utils'
import { DiacriticsBar } from './DiacriticsBar'

export function TranslatePanel({ project, onNext }: { project: Project; onNext: () => void }) {
  const st = project.stages.translation
  const busy = isBusy(st)
  const runStage = useStudio((s) => s.runStage)
  const cancelStage = useStudio((s) => s.cancelStage)
  const saveChoice = useStudio((s) => s.saveChoice)
  const patchSettings = useStudio((s) => s.patchSettings)
  const confirm = useStudio((s) => s.confirm)
  const done = project.segments.filter((s) => s.translation_status === 'done').length
  const missing = project.segments.filter((s) => s.translation_status !== 'done' || translationStale(s)).map((s) => s.id)

  if (!project.segments.length) {
    return <Empty icon={<Languages className="size-8" />} title="Nothing to translate yet">Transcribe the video first.</Empty>
  }

  return (
    <div className="flex flex-col gap-6">
      <StageHeader
        icon="🌍"
        title="Translation"
        subtitle="Each translated chunk appears instantly — edit freely, retranslate single lines, or keep going while the rest streams in."
        state={st}
        actions={
          busy ? (
            <Button onClick={() => cancelStage('translation')}>Cancel</Button>
          ) : (
            <>
              {done > 0 && missing.length > 0 && (
                <Button onClick={() => runStage('translation', { segment_ids: missing })}>Translate {missing.length} missing</Button>
              )}
              <Button variant={done ? 'secondary' : 'primary'} icon={<Languages className="size-4" />} onClick={async () => {
                if (done) {
                  const ok = await confirm({
                    title: 'Retranslate every segment?',
                    message: `All ${done} translated segment${done === 1 ? '' : 's'} will be translated again, replacing any wording you edited by hand.`,
                    confirmLabel: 'Retranslate all',
                    icon: '🌍',
                  })
                  if (!ok) return
                }
                runStage('translation')
              }}>
                {done ? 'Retranslate all' : 'Translate all'}
              </Button>
              {done > 0 && (
                <Button variant="primary" icon={<ArrowRight className="size-4" />} onClick={onNext}>
                  Voice
                </Button>
              )}
            </>
          )
        }
      />

      <div className="flex flex-wrap items-center gap-3 text-sm text-neutral-400">
        Target dialect
        <Select<TargetDialect> value={project.settings.target} onChange={(v) => patchSettings({ target: v })} options={TARGET_OPTIONS} className="w-64" menuWidth={300} />
      </div>

      <EnginePicker
        kind="translation"
        choice={project.settings.translation}
        source={project.settings.source_language}
        target={project.settings.target}
        disabled={busy}
        onChange={(c) => saveChoice('translation', c)}
      />

      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-3">
          <span className="shrink-0 text-[11px] font-semibold uppercase tracking-wider text-neutral-500">
            {done}/{project.segments.length} translated
          </span>
          <Progress value={done / project.segments.length} />
        </div>
        {isArabic(project.settings.target) && <DiacriticsBar />}
        {project.segments.map((s, i) => (
          <TranslationRow key={s.id} seg={s} index={i} rtl={isRtl(project.settings.target)} />
        ))}
      </div>
    </div>
  )
}

const TranslationRow = memo(function TranslationRow({ seg, index, rtl }: { seg: Segment; index: number; rtl: boolean }) {
  const updateSegment = useStudio((s) => s.updateSegment)
  const runStage = useStudio((s) => s.runStage)
  const select = useStudio((s) => s.select)
  const selected = useStudio((s) => s.selectedId === seg.id)
  const playRange = usePlayer((s) => s.playRange)
  const active = usePlayer((s) => s.time >= seg.start && s.time < seg.end)
  const stale = translationStale(seg)
  const working = seg.translation_status === 'queued' || seg.translation_status === 'running'

  return (
    <div onClick={() => select(seg.id)} className={cls('row-auto group grid gap-2 rounded-2xl border p-3 transition sm:grid-cols-2', active ? 'border-white/70' : selected ? 'border-neutral-500' : 'border-line hover:border-line-strong')}>
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2 font-mono text-[11px] text-neutral-500">
          <span className="text-neutral-600">#{index + 1}</span>
          {fmtTime(seg.start)}
          <IconButton title="Play original" onClick={() => playRange(seg.start, seg.end)} className="size-6">
            <Play className="size-3" />
          </IconButton>
        </div>
        <p className="px-1 text-sm leading-relaxed text-neutral-400" dir="auto">
          {seg.text}
        </p>
      </div>
      <div className="flex flex-col gap-1">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-[11px] text-neutral-500">
            <StatusIcon status={seg.translation_status === 'pending' ? 'idle' : seg.translation_status} className="size-3.5" />
            {stale && (
              <span className="flex items-center gap-1 text-neutral-300" title="The source text changed after this translation">
                <AlertTriangle className="size-3" /> source edited
              </span>
            )}
          </span>
          <IconButton title="Retranslate this segment" disabled={working} onClick={() => runStage('translation', { segment_ids: [seg.id] })} className="size-6 opacity-50 group-hover:opacity-100">
            <RefreshCw className="size-3" />
          </IconButton>
        </div>
        {working && !seg.translation ? (
          <div className="shimmer h-9 rounded-xl" />
        ) : (
          <AutoTextarea rtl={rtl} value={seg.translation} placeholder="…" onCommit={(translation) => updateSegment(seg.id, { translation })} />
        )}
      </div>
    </div>
  )
})
