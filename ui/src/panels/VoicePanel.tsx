import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowRight, AudioLines, Check, Crosshair, Info, Mic, Pause, Play, Scissors, Sparkles, Upload, Users, Wand2 } from 'lucide-react'
import { api, fileUrl, presetAudioUrl } from '../api'
import { isArabic, lang, SOURCE_OPTIONS } from '../components/Flags'
import { Select } from '../components/Select'
import { StageHeader } from '../components/StageHeader'
import { Badge, Button, Field, Switch, inputCls } from '../components/ui'
import { playPreview, stopPreview, usePlayer } from '../player'
import { recommendationsFor, useStudio } from '../store'
import type { Preset, Project, VoiceConfig } from '../types'
import { cls, fmtTime, isBusy } from '../utils'

type Mode = VoiceConfig['mode']

const MODES: { id: Mode; title: string; desc: string; icon: JSX.Element }[] = [
  { id: 'clip', title: 'From this video', desc: 'Pick 3–12 s of the original speaker on the timeline.', icon: <Scissors className="size-4" /> },
  { id: 'auto', title: 'Auto per segment', desc: 'Every chunk clones the voice speaking in it — great for multiple speakers.', icon: <Users className="size-4" /> },
  { id: 'preset', title: 'Studio voice', desc: '17 built-in Egyptian Arabic voices from VoiceTut.', icon: <Sparkles className="size-4" /> },
  { id: 'upload', title: 'Upload', desc: 'Your own recording — transcribed automatically with an ASR engine.', icon: <Upload className="size-4" /> },
]

export function VoicePanel({ project, onNext }: { project: Project; onNext: () => void }) {
  const st = project.stages.voice
  const toast = useStudio((s) => s.toast)
  const arabicTarget = isArabic(project.settings.target)
  const [mode, setMode] = useState<Mode>(project.voice.mode === 'preset' && !arabicTarget && st?.status !== 'done' ? 'auto' : project.voice.mode)
  const [saving, setSaving] = useState(false)

  const apply = async (body: Record<string, unknown>) => {
    setSaving(true)
    try {
      await api.setVoice(project.id, body)
      toast('Reference voice saved', 'success')
    } catch (e: any) {
      toast(e.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <StageHeader
        icon="🧬"
        title="Reference voice"
        subtitle="The TTS engine clones timbre and style from a short reference clip plus its transcript. Use a reference in the dub language for the most natural accent."
        state={st}
        actions={
          st?.status === 'done' && (
            <Button variant="primary" icon={<ArrowRight className="size-4" />} onClick={onNext}>
              Generate dub
            </Button>
          )
        }
      />

      <div className="grid gap-2 sm:grid-cols-2">
        {MODES.map((m) => (
          <button
            key={m.id}
            onClick={() => setMode(m.id)}
            className={cls('lift flex flex-col gap-1 rounded-2xl border p-3 text-left', mode === m.id ? 'border-white bg-white/[.06]' : 'border-line hover:border-neutral-600')}
          >
            <span className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-sm font-semibold">
                {m.icon} {m.title}
              </span>
              {project.voice.mode === m.id && st?.status === 'done' && <Badge tone="solid">active</Badge>}
            </span>
            <span className="text-xs text-neutral-500">{m.desc}</span>
          </button>
        ))}
      </div>

      {mode === 'clip' && <ClipEditor project={project} saving={saving} apply={apply} />}
      {mode === 'preset' && <PresetPicker project={project} saving={saving} apply={apply} />}
      {mode === 'upload' && <UploadVoice project={project} />}
      {mode === 'auto' && (
        <div className="flex flex-col gap-3 rounded-2xl border border-line p-4 text-sm text-neutral-400">
          <p>Each segment uses its own original audio (padded to at least 3 s) and its aligned transcript as the reference, so every speaker keeps their voice. Run vocal separation below for cleaner references.</p>
          <Button variant="primary" icon={<Wand2 className="size-4" />} loading={saving} onClick={() => apply({ mode: 'auto' })} className="self-start">
            Use automatic voices
          </Button>
        </div>
      )}

      {(project.voice.mode === 'clip' || project.voice.mode === 'upload') && project.voice.ref_audio && (mode === 'clip' || mode === 'upload') && (
        <ReferenceTranscriber project={project} />
      )}

      <SeparationCard project={project} />
    </div>
  )
}

/** Re-transcribe the saved reference clip with any ASR engine that supports its language. */
function ReferenceTranscriber({ project }: { project: Project }) {
  const toast = useStudio((s) => s.toast)
  const engines = useStudio((s) => s.engines)
  const languages = useStudio((s) => s.languages)
  const voice = project.voice
  const [language, setLanguage] = useState(voice.ref_language || project.settings.source_language)
  const recs = recommendationsFor(languages, 'asr', language)
  const rankOf = (id: string) => {
    const i = recs.findIndex((r) => r.engine === id)
    return i < 0 ? 99 : i
  }
  const options = useMemo(
    () =>
      engines
        .filter((e) => e.kind === 'asr' && e.source_languages.includes(language))
        .sort((a, b) => Number(b.available) - Number(a.available) || rankOf(a.id) - rankOf(b.id))
        .map((e) => ({
          value: e.id,
          label: e.name,
          description: `${e.available ? 'ready' : 'not installed'}${recs[0]?.engine === e.id ? ' · top pick' : ''}`,
          disabled: !e.available,
        })),
    [engines, language, recs],
  )
  const defaultEngine = options.find((o) => !o.disabled && (o.value === project.settings.asr.engine || recs.some((r) => r.engine === o.value)))?.value ?? options.find((o) => !o.disabled)?.value
  const [engine, setEngine] = useState<string | undefined>(defaultEngine)
  useEffect(() => {
    if (!engine || !options.some((o) => o.value === engine && !o.disabled)) setEngine(defaultEngine)
  }, [defaultEngine, engine, options])

  const busy = voice.ref_text_status === 'queued' || voice.ref_text_status === 'running'
  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-line p-4">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Mic className="size-4" /> Reference transcript
        {voice.ref_text_status === 'done' && <Badge tone="outline">auto-transcribed</Badge>}
        {voice.ref_text_status === 'error' && <Badge tone="outline">failed — see logs</Badge>}
      </div>
      <p className={cls('min-h-[2.5rem] rounded-xl border border-line bg-black/30 px-3 py-2 text-sm', !voice.ref_text && 'text-neutral-600')} dir="auto">
        {busy ? <span className="shimmer inline-block h-4 w-2/3 rounded" /> : voice.ref_text || 'No transcript yet.'}
      </p>
      <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <Field label="Reference language">
          <Select value={language} onChange={setLanguage} options={SOURCE_OPTIONS} menuWidth={260} />
        </Field>
        <Field label="Transcribe with">
          <Select value={engine ?? ''} onChange={setEngine} options={options} placeholder="No compatible engine installed" />
        </Field>
        <Button
          icon={<Wand2 className="size-4" />}
          loading={busy}
          disabled={!engine || busy}
          onClick={() => api.transcribeVoice(project.id, { engine, language }).catch((e) => toast(e.message, 'error'))}
        >
          Transcribe
        </Button>
      </div>
    </div>
  )
}

function ClipEditor({ project, saving, apply }: { project: Project; saving: boolean; apply: (b: Record<string, unknown>) => Promise<void> }) {
  const clip = useStudio((s) => s.clipDraft)
  const setClip = useStudio((s) => s.setClipDraft)
  const selectedId = useStudio((s) => s.selectedId)
  const playRange = usePlayer((s) => s.playRange)
  const [refText, setRefText] = useState(project.voice.ref_text)
  const [playing, setPlaying] = useState(false)

  useEffect(() => {
    setClip({ start: project.voice.clip_start ?? null, end: project.voice.clip_end ?? null })
    return () => setClip({ start: null, end: null })
  }, [project.voice.clip_start, project.voice.clip_end, setClip])

  useEffect(() => setRefText(project.voice.ref_text), [project.voice.ref_text])

  const now = () => usePlayer.getState().time
  const selected = project.segments.find((s) => s.id === selectedId)
  const length = clip.start !== null && clip.end !== null ? clip.end - clip.start : 0
  const savedAudio = project.voice.mode === 'clip' && project.voice.ref_audio ? fileUrl(project.id, project.voice.ref_audio, project.updated_at) : null

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-line p-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Start">
          <div className="flex gap-2">
            <input type="number" step={0.05} className={cls(inputCls, 'font-mono')} value={clip.start ?? ''} onChange={(e) => setClip({ start: e.target.value === '' ? null : Number(e.target.value) })} />
            <Button size="md" icon={<Crosshair className="size-3.5" />} onClick={() => setClip({ start: Number(now().toFixed(2)) })}>
              now
            </Button>
          </div>
        </Field>
        <Field label="End">
          <div className="flex gap-2">
            <input type="number" step={0.05} className={cls(inputCls, 'font-mono')} value={clip.end ?? ''} onChange={(e) => setClip({ end: e.target.value === '' ? null : Number(e.target.value) })} />
            <Button size="md" icon={<Crosshair className="size-3.5" />} onClick={() => setClip({ end: Number(now().toFixed(2)) })}>
              now
            </Button>
          </div>
        </Field>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-500">
        <span className={cls('font-mono', length > 0 && (length < 3 || length > 15) ? 'text-white' : '')}>
          {length > 0 ? `${length.toFixed(2)} s ${length < 3 ? '· a bit short' : length > 15 ? '· a bit long' : '· good length'}` : 'Play the video and mark a clean stretch of speech.'}
        </span>
        {selected && (
          <Button size="sm" onClick={() => setClip({ start: selected.start, end: selected.end })}>
            Use selected segment ({fmtTime(selected.start)})
          </Button>
        )}
        {length > 0 && (
          <Button size="sm" icon={<Play className="size-3" />} onClick={() => playRange(clip.start!, clip.end!)}>
            Preview on video
          </Button>
        )}
      </div>
      <Field label="Reference transcript" hint="Leave empty to fill it from the aligned words inside the clip — or transcribe it with an ASR engine below after saving.">
        <textarea className={cls(inputCls, 'h-20 py-2')} dir="auto" value={refText} onChange={(e) => setRefText(e.target.value)} />
      </Field>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" icon={<Check className="size-4" />} loading={saving} disabled={!(length > 0.5)} onClick={() => apply({ mode: 'clip', clip_start: clip.start, clip_end: clip.end, ref_text: refText.trim(), ref_language: project.settings.source_language })}>
          Save clip as reference
        </Button>
        {savedAudio && (
          <Button
            icon={playing ? <Pause className="size-4" /> : <AudioLines className="size-4" />}
            onClick={() => {
              if (playing) {
                stopPreview()
                setPlaying(false)
              } else {
                playPreview(savedAudio, () => setPlaying(false))
                setPlaying(true)
              }
            }}
          >
            Listen to saved reference
          </Button>
        )}
      </div>
    </div>
  )
}

function PresetPicker({ project, saving, apply }: { project: Project; saving: boolean; apply: (b: Record<string, unknown>) => Promise<void> }) {
  const toast = useStudio((s) => s.toast)
  const [presets, setPresets] = useState<Preset[] | null>(null)
  const [playing, setPlaying] = useState<string | null>(null)
  const arabicTarget = isArabic(project.settings.target)

  useEffect(() => {
    api.presets().then(setPresets).catch((e) => {
      toast(e.message, 'error')
      setPresets([])
    })
  }, [toast])

  if (!presets) return <div className="shimmer h-40 rounded-2xl" />
  return (
    <div className="flex flex-col gap-3">
      {!arabicTarget && (
        <div className="flex items-start gap-2 rounded-2xl border border-line-strong p-3 text-xs text-neutral-400">
          <Info className="mt-0.5 size-3.5 shrink-0" />
          These studio voices speak Egyptian Arabic. Cloning them into {lang(project.settings.target).name} keeps an Arabic accent — prefer “From this video”, “Auto per segment” or an uploaded {lang(project.settings.target).name} recording.
        </div>
      )}
      <div className="stagger grid gap-2 sm:grid-cols-3">
        {presets.map((p, i) => {
          const active = project.voice.mode === 'preset' && project.voice.preset === p.id
          return (
            <div key={p.id} style={{ ['--i' as string]: Math.min(i, 12) }} className={cls('lift flex flex-col gap-2 rounded-2xl border p-3', active ? 'border-white bg-white/[.06]' : 'border-line hover:border-neutral-600')}>
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold">{p.name}</span>
                <span className="text-[10px] uppercase tracking-wider text-neutral-500">{p.gender}</span>
              </div>
              <p className="arabic line-clamp-2 text-xs text-neutral-500">{p.text}</p>
              <div className="flex gap-1.5">
                <Button
                  size="sm"
                  icon={playing === p.id ? <Pause className="size-3" /> : <Play className="size-3" />}
                  onClick={() => {
                    if (playing === p.id) {
                      stopPreview()
                      setPlaying(null)
                    } else {
                      playPreview(presetAudioUrl(p.id), () => setPlaying(null))
                      setPlaying(p.id)
                    }
                  }}
                >
                  Listen
                </Button>
                <Button size="sm" variant={active ? 'primary' : 'secondary'} loading={saving && !active} onClick={() => apply({ mode: 'preset', preset: p.id })}>
                  {active ? 'Selected' : 'Use'}
                </Button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function UploadVoice({ project }: { project: Project }) {
  const toast = useStudio((s) => s.toast)
  const engines = useStudio((s) => s.engines)
  const languages = useStudio((s) => s.languages)
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [text, setText] = useState(project.voice.mode === 'upload' ? project.voice.ref_text : '')
  const [language, setLanguage] = useState(project.voice.ref_language || (isArabic(project.settings.target) ? 'ar' : project.settings.target))
  const [auto, setAuto] = useState(true)
  const [busy, setBusy] = useState(false)

  const recs = recommendationsFor(languages, 'asr', language)
  const autoEngine =
    recs.map((r) => engines.find((e) => e.id === r.engine)).find((e) => e?.available) ?? engines.find((e) => e.kind === 'asr' && e.available && e.source_languages.includes(language))

  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-line p-4">
      <input ref={input} type="file" accept="audio/*,video/*" hidden onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      <div className="flex flex-wrap items-center gap-3">
        <Button icon={<Upload className="size-4" />} onClick={() => input.current?.click()}>
          {file ? file.name : project.voice.mode === 'upload' && project.voice.upload_name ? `Replace ${project.voice.upload_name}` : 'Choose audio file'}
        </Button>
        <div className="w-56">
          <Select value={language} onChange={setLanguage} options={SOURCE_OPTIONS} menuWidth={260} />
        </div>
      </div>
      <Field
        label="Transcript of the recording"
        hint={
          auto
            ? `Leave empty and Dubby transcribes it with ${autoEngine ? autoEngine.name : 'the recommended ASR engine'} after upload.`
            : 'An accurate transcript noticeably improves cloning.'
        }
      >
        <textarea className={cls(inputCls, 'h-20 py-2')} dir="auto" value={text} onChange={(e) => setText(e.target.value)} placeholder={auto ? 'Optional — auto-transcribed when empty' : ''} />
      </Field>
      <Switch checked={auto} onChange={setAuto} label={<span className="text-xs">Auto-transcribe with ASR when the transcript is empty</span>} />
      <Button
        variant="primary"
        disabled={!file}
        loading={busy}
        className="self-start"
        onClick={async () => {
          if (!file) return
          setBusy(true)
          try {
            await api.uploadVoice(project.id, file, text, { autoTranscribe: auto, engine: autoEngine?.id ?? null, language })
            toast(auto && !text.trim() ? 'Reference uploaded — transcribing…' : 'Reference voice uploaded', 'success')
          } catch (e: any) {
            toast(e.message, 'error')
          } finally {
            setBusy(false)
          }
        }}
      >
        Save uploaded voice
      </Button>
    </div>
  )
}

function SeparationCard({ project }: { project: Project }) {
  const st = project.stages.separation
  const runStage = useStudio((s) => s.runStage)
  const cancelStage = useStudio((s) => s.cancelStage)
  const engine = useStudio((s) => s.engines.find((e) => e.id === 'demucs'))
  const busy = isBusy(st)
  return (
    <div className="rounded-2xl border border-line p-4">
      <StageHeader
        icon="🎚️"
        title="Vocal separation"
        subtitle={project.source.vocals ? 'Clean vocals are used for references; the music stem can go under the dub.' : 'Optional · Demucs removes background music from references and gives a clean music bed for the mix.'}
        state={st}
        actions={
          busy ? (
            <Button size="sm" onClick={() => cancelStage('separation')}>
              Cancel
            </Button>
          ) : (
            <Button size="sm" disabled={engine ? !engine.available : true} title={engine && !engine.available ? engine.install : undefined} onClick={() => runStage('separation', { engine: 'demucs' })}>
              {project.source.vocals ? 'Run again' : engine?.available ? 'Separate vocals' : 'Demucs not installed'}
            </Button>
          )
        }
      />
    </div>
  )
}
