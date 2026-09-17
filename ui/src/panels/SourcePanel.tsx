import { useEffect, useRef, useState } from 'react'
import { ArrowRight, Cookie, Globe2, RotateCcw, Sparkles, Upload } from 'lucide-react'
import { api } from '../api'
import { CookiesField } from '../components/CookiesField'
import { UploadProgressCard, advance, startUpload, type UploadState } from '../components/UploadProgress'
import { LangLabel, SOURCE_OPTIONS, TARGET_OPTIONS } from '../components/Flags'
import { Select } from '../components/Select'
import { StageHeader } from '../components/StageHeader'
import { Button, Field, Progress } from '../components/ui'
import { useStudio } from '../store'
import type { Project } from '../types'
import { fmtDuration, isBusy } from '../utils'

export function SourcePanel({ project, onNext }: { project: Project; onNext: () => void }) {
  const st = project.stages.download
  const langSt = project.stages.langid
  const runStage = useStudio((s) => s.runStage)
  const cancelStage = useStudio((s) => s.cancelStage)
  const patchSettings = useStudio((s) => s.patchSettings)
  const toast = useStudio((s) => s.toast)
  const busy = isBusy(st)
  const detecting = isBusy(langSt)
  const src = project.source

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
            <Button variant="primary" icon={<ArrowRight className="size-4" />} onClick={onNext} disabled={detecting}>
              Transcribe
            </Button>
          ) : (
            <Button icon={<RotateCcw className="size-4" />} onClick={() => runStage('download')}>
              Retry download
            </Button>
          )
        }
      />

      {st?.status === 'error' && src.kind === 'youtube' && <DownloadRecovery project={project} />}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Info label="Title" value={src.title ?? project.title} />
        <Info label="Channel" value={src.uploader ?? '—'} />
        <Info label="Duration" value={fmtDuration(src.duration)} />
        <Info label="Origin" value={src.kind === 'youtube' ? src.url ?? '' : 'Uploaded file'} mono />
      </div>

      <div className="flex flex-col gap-4 rounded-2xl border border-line p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Globe2 className="size-4" /> Spoken language
          </div>
          <Button
            size="sm"
            icon={<Sparkles className="size-3.5" />}
            disabled={!src.audio16k || detecting}
            loading={detecting}
            onClick={() => api.detectLanguage(project.id).catch((e) => toast(e.message, 'error'))}
          >
            {src.detected_language ? 'Detect again' : 'Auto-detect'}
          </Button>
        </div>

        {detecting && (
          <div className="flex flex-col gap-1.5">
            <Progress value={langSt?.progress ?? 0} active />
            <span className="text-xs text-neutral-500">{langSt?.message || 'Listening to the speech…'}</span>
          </div>
        )}
        {!detecting && langSt?.status === 'done' && (
          <div className="fade-in flex flex-wrap items-center gap-2 text-xs text-neutral-400">
            <span className="text-neutral-300">{langSt.message}</span>
            {(src.detected_candidates ?? []).slice(1, 4).map(([code, p]) => (
              <span key={code} className="rounded-full border border-line px-2 py-0.5 font-mono">
                {code} {(p * 100).toFixed(0)}%
              </span>
            ))}
          </div>
        )}
        {langSt?.status === 'error' && <div className="text-xs text-neutral-400">Detection failed: {langSt.error}</div>}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Spoken language" hint="Changing it swaps in engines that support the language.">
            <Select value={project.settings.source_language} onChange={(v) => patchSettings({ source_language: v })} options={SOURCE_OPTIONS} menuWidth={280} />
          </Field>
          <Field label="Dub into">
            <Select value={project.settings.target} onChange={(v) => patchSettings({ target: v })} options={TARGET_OPTIONS} menuWidth={300} />
          </Field>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line-strong bg-white/[.02] px-3 py-2.5 text-xs text-neutral-400">
          <span className="flex flex-wrap items-center gap-2">
            Current pipeline for <LangLabel code={project.settings.source_language} size={10} /> → <LangLabel code={project.settings.target} size={10} />:
            <b className="text-neutral-200">{project.settings.asr.engine}</b>·<b className="text-neutral-200">{project.settings.translation.engine}</b>·
            <b className="text-neutral-200">{project.settings.tts.engine}</b>
          </span>
          <Button
            size="sm"
            icon={<Sparkles className="size-3.5" />}
            onClick={() =>
              api
                .applyRecommendations(project.id)
                .then(() => toast('Recommended engines applied', 'success'))
                .catch((e) => toast(e.message, 'error'))
            }
          >
            Use recommended engines
          </Button>
        </div>
      </div>
    </div>
  )
}

/** Shown when a YouTube download fails: drop in the video file (instant) or retry. */
function DownloadRecovery({ project }: { project: Project }) {
  const toast = useStudio((s) => s.toast)
  const runStage = useStudio((s) => s.runStage)
  const fileInput = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState<UploadState | null>(null)
  const [dragging, setDragging] = useState(false)
  const [advanced, setAdvanced] = useState(false)
  const [cookies, setCookies] = useState(false)

  useEffect(() => {
    api.getSettings().then((s) => setCookies(!!s.cookies_configured)).catch(() => {})
  }, [])

  const useFile = async (file: File) => {
    setUploading(startUpload(file))
    try {
      await api.replaceSource(project.id, file, (progress) => setUploading((state) => advance(state, progress)))
      toast(`Using ${file.name} as the source`, 'success')
    } catch (err: any) {
      toast(err.message, 'error')
    } finally {
      setUploading(null)
    }
  }

  return (
    <div className="fade-in flex flex-col gap-4 rounded-2xl border border-line-strong p-4">
      <button
        type="button"
        onClick={() => fileInput.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          const file = e.dataTransfer.files?.[0]
          if (file) useFile(file)
        }}
        className={`flex flex-col items-center gap-2 rounded-2xl border border-dashed px-4 py-7 text-center transition-colors ${dragging ? 'border-leaf bg-white/[.04]' : 'border-line-strong hover:bg-white/[.03]'}`}
      >
        <Upload className="size-6" />
        <span className="text-sm font-semibold">{uploading ? 'Uploading…' : 'Drop the video file here, or click to choose'}</span>
        <span className="text-xs text-neutral-500">Fastest fix — this project keeps its languages and engines, and the pipeline continues as usual.</span>
      </button>
      <input ref={fileInput} type="file" accept="video/*,audio/*" hidden onChange={(e) => e.target.files?.[0] && useFile(e.target.files[0])} />
      {uploading && <UploadProgressCard state={uploading} compact />}

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" icon={<RotateCcw className="size-3.5" />} onClick={() => runStage('download')}>
          Retry download
        </Button>
        <span className="text-xs text-neutral-500">Retries run every strategy again (PO tokens, TV and embedded clients). A new Colab runtime gets a new IP.</span>
        <button type="button" className="ml-auto text-xs text-neutral-500 underline-offset-4 hover:text-neutral-200 hover:underline" onClick={() => setAdvanced((v) => !v)}>
          {advanced ? 'Hide advanced' : 'Advanced: cookies'}
        </button>
      </div>

      {advanced && (
        <div className="fade-in flex flex-col gap-2 border-t border-line pt-3">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-neutral-500">
            <Cookie className="size-3.5" /> Optional · YouTube cookies
          </div>
          <CookiesField
            configured={cookies}
            onChange={(s) => {
              const ok = !!s.cookies_configured
              setCookies(ok)
              if (ok) runStage('download')
            }}
          />
          <p className="text-xs text-neutral-500">A proxy can also be set in ⚙️ Settings. Neither is needed for most videos.</p>
        </div>
      )}
    </div>
  )
}

function Info({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0 rounded-2xl border border-line p-3">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-neutral-500">{label}</div>
      <div className={mono ? 'mt-1 truncate font-mono text-xs text-neutral-300' : 'mt-1 truncate text-sm'} title={value}>
        {value}
      </div>
    </div>
  )
}
