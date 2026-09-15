import { useEffect, useRef, useState } from 'react'
import { ArrowRight, Cookie, Globe2, RotateCcw, Sparkles, Upload } from 'lucide-react'
import { api } from '../api'
import { CookiesField } from '../components/CookiesField'
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

      {st?.status === 'error' && src.kind === 'youtube' && <DownloadRecovery project={project} needsCookies={/not a bot|cookies|private|members-only|age-restricted/i.test(st.error ?? '')} />}

      <div className="grid gap-3 sm:grid-cols-2">
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

        <div className="grid gap-3 sm:grid-cols-2">
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

/** Shown when a YouTube download fails: add cookies and retry, or use an uploaded file. */
function DownloadRecovery({ project, needsCookies }: { project: Project; needsCookies: boolean }) {
  const toast = useStudio((s) => s.toast)
  const runStage = useStudio((s) => s.runStage)
  const fileInput = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [cookies, setCookies] = useState(false)

  useEffect(() => {
    api.getSettings().then((s) => setCookies(!!s.cookies_configured)).catch(() => {})
  }, [])

  return (
    <div className="fade-in flex flex-col gap-4 rounded-2xl border border-line-strong p-4">
      <div className="text-sm font-semibold">How to get this video</div>
      <div className={needsCookies ? 'grid gap-4 md:grid-cols-2' : 'grid gap-4'}>
        {needsCookies && (
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-neutral-500">
              <Cookie className="size-3.5" /> 1 · Add YouTube cookies, then retry
            </div>
            <CookiesField
              configured={cookies}
              compact
              onChange={(s) => {
                const ok = !!s.cookies_configured
                setCookies(ok)
                if (ok) runStage('download')
              }}
            />
            <p className="text-xs leading-relaxed text-neutral-500">
              In a private/incognito window sign in to YouTube, export <b>youtube.com</b> cookies as <code>cookies.txt</code> (“Get cookies.txt LOCALLY” extension), close the window, then upload the file here — the download restarts automatically.
            </p>
            {cookies && (
              <Button size="sm" icon={<RotateCcw className="size-3.5" />} onClick={() => runStage('download')} className="self-start">
                Retry with cookies
              </Button>
            )}
          </div>
        )}
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-neutral-500">
            <Upload className="size-3.5" /> {needsCookies ? '2 · Or' : 'Or'} upload the video file
          </div>
          <input
            ref={fileInput}
            type="file"
            accept="video/*,audio/*"
            hidden
            onChange={async (e) => {
              const file = e.target.files?.[0]
              if (!file) return
              setUploading(true)
              try {
                await api.replaceSource(project.id, file)
                toast(`Using ${file.name} as the source`, 'success')
              } catch (err: any) {
                toast(err.message, 'error')
              } finally {
                setUploading(false)
              }
            }}
          />
          <Button icon={<Upload className="size-4" />} loading={uploading} onClick={() => fileInput.current?.click()} className="self-start">
            Choose a video file
          </Button>
          <p className="text-xs text-neutral-500">Keeps this project and its settings; the rest of the pipeline works exactly the same.</p>
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
