import { useEffect, useRef, useState } from 'react'
import { ArrowRight, Clock, FileVideo, Trash2, Youtube } from 'lucide-react'
import { api } from '../api'
import { Flag, lang, SOURCE_OPTIONS_WITH_AUTO, TARGET_OPTIONS, type FlagCode } from '../components/Flags'
import { Select } from '../components/Select'
import { Button, StatusIcon } from '../components/ui'
import { useStudio } from '../store'
import type { ProjectSummary, SourceLanguage, TargetDialect } from '../types'
import { cls, fmtDuration, timeAgo } from '../utils'

const PIPELINE = [
  ['download', 'Source'],
  ['asr', 'Transcript'],
  ['translation', 'Translation'],
  ['tts', 'Voices'],
  ['render', 'Render'],
] as const

const HERO_WORDS: { text: string; flag?: FlagCode; arabic?: boolean }[] = [
  { text: 'مصري', flag: 'eg', arabic: true },
  { text: 'فصحى', flag: 'sa', arabic: true },
  { text: 'Español', flag: 'es' },
  { text: 'Français', flag: 'fr' },
  { text: 'Italiano', flag: 'it' },
  { text: 'हिन्दी', flag: 'in' },
  { text: '中文', flag: 'cn' },
  { text: '日本語', flag: 'jp' },
]

export function HomePage() {
  const projects = useStudio((s) => s.projects)
  const loadProjects = useStudio((s) => s.loadProjects)
  const closeProject = useStudio((s) => s.closeProject)
  const toast = useStudio((s) => s.toast)
  const [url, setUrl] = useState('')
  const [source, setSource] = useState<SourceLanguage>('auto')
  const [target, setTarget] = useState<TargetDialect>('arz')
  const [busy, setBusy] = useState(false)
  const [word, setWord] = useState(0)
  const fileInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    closeProject()
    loadProjects()
  }, [closeProject, loadProjects])

  useEffect(() => {
    const t = setInterval(() => setWord((i) => (i + 1) % HERO_WORDS.length), 2600)
    return () => clearInterval(t)
  }, [])

  const create = async () => {
    setBusy(true)
    try {
      const p = await api.create(url, source, target)
      window.location.hash = `#/p/${p.id}`
    } catch (e: any) {
      toast(e.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  const upload = async (file: File) => {
    setBusy(true)
    try {
      const p = await api.upload(file, source, target)
      window.location.hash = `#/p/${p.id}`
    } catch (e: any) {
      toast(e.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  const hero = HERO_WORDS[word]

  return (
    <div className="mx-auto flex max-w-[1200px] flex-col gap-14 px-4 pt-14 pb-24 sm:px-6">
      <section className="fade-in grain relative overflow-hidden rounded-[28px] border border-line bg-panel/60 px-6 py-14 backdrop-blur-sm sm:px-12">
        <div className="orb pointer-events-none absolute -top-40 -right-40 size-[480px] rounded-full bg-white/[.07] blur-3xl" />
        <div className="orb pointer-events-none absolute -bottom-52 left-10 size-[380px] rounded-full bg-white/[.04] blur-3xl" style={{ animationDelay: '-7s' }} />
        <div className="relative flex max-w-3xl flex-col gap-6">
          <span className="flex w-fit items-center gap-2 rounded-full border border-line-strong bg-black px-3 py-1 text-xs text-neutral-400">
            {(['us', 'eg', 'sa', 'es', 'fr', 'it', 'in', 'cn', 'jp'] as FlagCode[]).map((f) => (
              <Flag key={f} code={f} size={10} />
            ))}
            <span className="ml-1">9 languages · ASR · Translation · Voice cloning · Mix</span>
          </span>
          <h1 className="text-4xl leading-[1.1] font-extrabold tracking-tight sm:text-6xl">
            Dub any YouTube video
            <br />
            <span className="text-neutral-500">into</span>{' '}
            {/* rotates through every supported dub language */}
            <span key={word} className="word-in inline-flex items-center gap-3 align-middle">
              <span className={cls('font-semibold', hero.arabic && 'font-arabic')} style={{ lineHeight: 1.2 }}>
                {hero.text}
              </span>
              {hero.flag && <Flag code={hero.flag} size={30} className="rounded-md" />}
            </span>
          </h1>
          <p className="max-w-xl text-base text-neutral-400">
            Paste a link. Review word-aligned transcripts, edit translations as they stream in, clone the original voice and export a perfectly timed dubbed video.
          </p>

          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault()
              if (url.trim()) create()
            }}
          >
            <div className="flex flex-col gap-2 rounded-[22px] border border-line-strong bg-black p-2 transition-all duration-300 focus-within:border-leaf focus-within:shadow-[0_0_0_5px_rgba(155,210,60,.14)] sm:flex-row sm:items-center">
              <div className="flex flex-1 items-center gap-3 px-3">
                <Youtube className="size-5 shrink-0 text-neutral-500" />
                <input
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://www.youtube.com/watch?v=…"
                  className="h-11 w-full bg-transparent text-base outline-none placeholder:text-neutral-600"
                  autoFocus
                />
              </div>
              <Button type="submit" variant="primary" size="lg" disabled={!url.trim()} loading={busy} icon={!busy ? <ArrowRight className="size-4" /> : undefined}>
                Start dubbing
              </Button>
            </div>
            <div className="flex flex-wrap items-center gap-3 px-1 text-xs text-neutral-500">
              <span className="flex items-center gap-2">
                from
                <Select<SourceLanguage> size="sm" value={source} onChange={setSource} options={SOURCE_OPTIONS_WITH_AUTO} className="w-40" menuWidth={280} />
              </span>
              <span className="flex items-center gap-2">
                to
                <Select<TargetDialect> size="sm" value={target} onChange={setTarget} options={TARGET_OPTIONS} className="w-52" menuWidth={300} />
              </span>
              <button type="button" onClick={() => fileInput.current?.click()} className="flex items-center gap-1.5 underline-offset-4 transition-colors hover:text-white hover:underline">
                <FileVideo className="size-3.5" /> or upload a video file
              </button>
              <input ref={fileInput} type="file" accept="video/*" hidden onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
            </div>
          </form>
        </div>
      </section>

      <section className="flex flex-col gap-5">
        <div className="flex items-end justify-between">
          <h2 className="text-xl font-semibold tracking-tight">Projects</h2>
          <span className="text-sm text-neutral-500">{projects.length} total</span>
        </div>
        {projects.length === 0 ? (
          <div className="fade-in rounded-2xl border border-dashed border-line-strong p-10 text-center text-sm text-neutral-500">No projects yet — your dubbed videos will show up here.</div>
        ) : (
          <div className="stagger grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {projects.map((p, i) => (
              <ProjectCard key={p.id} p={p} index={i} onDeleted={loadProjects} />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function ProjectCard({ p, index, onDeleted }: { p: ProjectSummary; index: number; onDeleted: () => void }) {
  const toast = useStudio((s) => s.toast)
  const confirm = useStudio((s) => s.confirm)
  const src = lang(p.settings.source_language)
  const tgt = lang(p.settings.target)
  return (
    <a
      href={`#/p/${p.id}`}
      style={{ ['--i' as string]: Math.min(index, 12) }}
      className="lift group flex flex-col overflow-hidden rounded-2xl border border-line bg-panel backdrop-blur-xl hover:border-neutral-600"
    >
      <div className="relative aspect-video overflow-hidden bg-neutral-950">
        {p.source.thumbnail ? (
          <img src={p.source.thumbnail} alt="" className="size-full object-cover opacity-80 grayscale transition duration-700 group-hover:scale-[1.05] group-hover:opacity-100 group-hover:grayscale-0" />
        ) : (
          <div className="grain flex size-full items-center justify-center text-4xl">
            <span className="float">🐨</span>
          </div>
        )}
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-transparent opacity-0 transition-opacity duration-500 group-hover:opacity-100" />
        <span className="absolute right-2 bottom-2 rounded-md bg-black/80 px-1.5 py-0.5 font-mono text-[11px]">{fmtDuration(p.source.duration)}</span>
        <span className="absolute top-2 left-2 inline-flex items-center gap-1.5 rounded-full border border-white/15 bg-black/75 px-2 py-1 text-[10px] font-semibold tracking-wider backdrop-blur" title={`${src.name} → ${tgt.name}`}>
          <Flag code={src.flag} size={10} />
          <ArrowRight className="size-2.5 text-neutral-400" />
          <Flag code={tgt.flag} size={10} />
          {tgt.short}
        </span>
      </div>
      <div className="flex flex-1 flex-col gap-3 p-4">
        <div className="line-clamp-2 min-h-[2.5rem] text-sm font-semibold leading-snug">{p.title}</div>
        <div className="flex items-center gap-1.5">
          {PIPELINE.map(([stage, label]) => (
            <div key={stage} className="flex flex-1 flex-col gap-1" title={`${label}: ${p.stages[stage]?.status ?? 'idle'}`}>
              <div
                className={cls(
                  'h-1 rounded-full transition-all duration-500',
                  p.stages[stage]?.status === 'done' ? 'bg-white' : p.stages[stage]?.status === 'running' ? 'shimmer bg-white/30' : p.stages[stage]?.status === 'error' ? 'hatch' : 'bg-white/10',
                )}
              />
            </div>
          ))}
        </div>
        <div className="flex items-center justify-between text-xs text-neutral-500">
          <span className="flex items-center gap-3">
            <span>{p.segments} seg</span>
            <span>{p.translated} tr</span>
            <span>{p.voiced} 🔊</span>
            {p.render.video && (
              <span className="flex items-center gap-1 text-neutral-300">
                <StatusIcon status="done" className="size-3" /> v{p.render.version}
              </span>
            )}
          </span>
          <span className="flex items-center gap-2">
            <Clock className="size-3" /> {timeAgo(p.updated_at)}
            <button
              title="Delete project"
              className="rounded-full p-1 opacity-0 transition-all duration-200 group-hover:opacity-100 hover:bg-white hover:text-black active:scale-90"
              onClick={async (e) => {
                e.preventDefault()
                const ok = await confirm({
                  title: 'Delete this project?',
                  message: `“${p.title}” and everything in it — the video, transcripts, translations, voice clips and exports — will be removed from disk. This cannot be undone.`,
                  confirmLabel: 'Delete project',
                  tone: 'danger',
                })
                if (!ok) return
                try {
                  await api.remove(p.id)
                  onDeleted()
                } catch (err: any) {
                  toast(err.message, 'error')
                }
              }}
            >
              <Trash2 className="size-3.5" />
            </button>
          </span>
        </div>
      </div>
    </a>
  )
}
