import { ArrowRight, RotateCcw } from 'lucide-react'
import { StageHeader } from '../components/StageHeader'
import { SOURCE_OPTIONS, TARGET_OPTIONS } from '../components/Flags'
import { Select } from '../components/Select'
import { Button, Field } from '../components/ui'
import { useStudio } from '../store'
import type { Project, SourceLanguage, TargetDialect } from '../types'
import { fmtDuration, isBusy } from '../utils'

export function SourcePanel({ project, onNext }: { project: Project; onNext: () => void }) {
  const st = project.stages.download
  const runStage = useStudio((s) => s.runStage)
  const cancelStage = useStudio((s) => s.cancelStage)
  const patchSettings = useStudio((s) => s.patchSettings)
  const busy = isBusy(st)

  return (
    <div className="flex flex-col gap-6">
      <StageHeader
        icon="⬇️"
        title="Source video"
        subtitle="Downloaded with yt-dlp, converted for the browser, and split into a 16 kHz speech track and a 44.1 kHz mix track."
        state={st}
        actions={
          busy ? (
            <Button onClick={() => cancelStage('download')}>Cancel</Button>
          ) : st?.status === 'done' ? (
            <Button variant="primary" icon={<ArrowRight className="size-4" />} onClick={onNext}>
              Transcribe
            </Button>
          ) : (
            <Button icon={<RotateCcw className="size-4" />} onClick={() => runStage('download')}>
              Retry download
            </Button>
          )
        }
      />

      <div className="grid gap-3 sm:grid-cols-2">
        <Info label="Title" value={project.source.title ?? project.title} />
        <Info label="Channel" value={project.source.uploader ?? '—'} />
        <Info label="Duration" value={fmtDuration(project.source.duration)} />
        <Info label="Origin" value={project.source.kind === 'youtube' ? project.source.url ?? '' : 'Uploaded file'} mono />
      </div>

      <div className="flex flex-col gap-3 rounded-2xl border border-line p-4">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-neutral-500">Languages</div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Spoken language">
            <Select<SourceLanguage> value={project.settings.source_language} onChange={(v) => patchSettings({ source_language: v })} options={SOURCE_OPTIONS} />
          </Field>
          <Field label="Dub into">
            <Select<TargetDialect> value={project.settings.target} onChange={(v) => patchSettings({ target: v })} options={TARGET_OPTIONS} />
          </Field>
        </div>
      </div>
    </div>
  )
}

function Info({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-2xl border border-line p-3">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-neutral-500">{label}</div>
      <div className={mono ? 'mt-1 truncate font-mono text-xs text-neutral-300' : 'mt-1 truncate text-sm'} title={value}>
        {value}
      </div>
    </div>
  )
}
