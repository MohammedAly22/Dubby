import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, ArrowRight, ExternalLink } from 'lucide-react'
import { LangLabel } from '../components/Flags'
import { Timeline } from '../components/Timeline'
import { VideoPlayer } from '../components/VideoPlayer'
import { StatusIcon, useIndicator } from '../components/ui'
import { DubPanel } from '../panels/DubPanel'
import { ExportPanel } from '../panels/ExportPanel'
import { SourcePanel } from '../panels/SourcePanel'
import { TranscribePanel } from '../panels/TranscribePanel'
import { TranslatePanel } from '../panels/TranslatePanel'
import { VoicePanel } from '../panels/VoicePanel'
import { useStudio } from '../store'
import type { Project, StageStatus } from '../types'
import { cls } from '../utils'

type Tab = 'source' | 'asr' | 'translation' | 'voice' | 'tts' | 'export'

const TABS: { id: Tab; label: string; stage: string }[] = [
  { id: 'source', label: 'Source', stage: 'download' },
  { id: 'asr', label: 'Transcribe', stage: 'asr' },
  { id: 'translation', label: 'Translate', stage: 'translation' },
  { id: 'voice', label: 'Voice', stage: 'voice' },
  { id: 'tts', label: 'Dub', stage: 'tts' },
  { id: 'export', label: 'Export', stage: 'render' },
]

function firstOpenTab(p: Project): Tab {
  for (const t of TABS) {
    if (p.stages[t.stage]?.status !== 'done') return t.id
  }
  return 'export'
}

export function ProjectPage({ id }: { id: string }) {
  const project = useStudio((s) => s.project)
  const openProject = useStudio((s) => s.openProject)
  const [tab, setTab] = useState<Tab | null>(null)

  useEffect(() => {
    openProject(id)
  }, [id, openProject])

  const loaded = !!project && project.id === id
  // Derive the starting tab during render so the tab pill appears in place (no slide on load).
  const active: Tab = tab ?? (loaded ? firstOpenTab(project!) : 'source')
  const statuses = useMemo(
    () => (loaded ? Object.fromEntries(TABS.map((t) => [t.id, (project!.stages[t.stage]?.status ?? 'idle') as StageStatus])) : {}),
    [loaded, project],
  )
  const { container, items, style, ready } = useIndicator<HTMLElement>(
    TABS.findIndex((t) => t.id === active),
    [loaded],
  )

  if (!loaded) {
    return (
      <div className="mx-auto grid max-w-[1600px] gap-6 px-6 py-8 lg:grid-cols-2">
        <div className="shimmer aspect-video rounded-2xl" />
        <div className="shimmer h-96 rounded-2xl" />
      </div>
    )
  }

  const p = project!
  return (
    <div className="fade-in mx-auto flex max-w-[1600px] flex-col gap-5 px-4 py-5 sm:px-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <a
            href="#/"
            className="inline-flex size-9 shrink-0 items-center justify-center rounded-full border border-line-strong text-neutral-400 transition-all duration-200 hover:-translate-x-0.5 hover:border-white hover:text-white"
            title="All projects"
          >
            <ArrowLeft className="size-4" />
          </a>
          <div className="min-w-0">
            <h1 className="truncate text-lg font-semibold tracking-tight">{p.title}</h1>
            <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-400">
              <LangLabel code={p.settings.source_language} variant="name" size={11} />
              <ArrowRight className="size-3 text-neutral-600" />
              <LangLabel code={p.settings.target} size={11} />
              {p.source.uploader && <span className="text-neutral-500">· {p.source.uploader}</span>}
              {p.source.url && (
                <a href={p.source.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-neutral-500 transition-colors hover:text-white">
                  · YouTube <ExternalLink className="size-3" />
                </a>
              )}
            </div>
          </div>
        </div>

        <nav ref={container} className="no-scrollbar relative flex overflow-x-auto rounded-full border border-line-strong bg-panel p-1 backdrop-blur-xl">
          <span
            aria-hidden
            className={cls(
              'pointer-events-none absolute top-1 bottom-1 rounded-full bg-white',
              ready && 'transition-[left,width,opacity] duration-[400ms] ease-[cubic-bezier(.3,1.25,.5,1)]',
            )}
            style={style}
          />
          {TABS.map((t, i) => (
            <button
              key={t.id}
              ref={(el) => {
                items.current[i] = el
              }}
              role="tab"
              aria-selected={active === t.id}
              onClick={() => setTab(t.id)}
              className={cls(
                'relative z-10 flex h-8 shrink-0 items-center gap-2 rounded-full px-3.5 text-xs font-medium transition-colors duration-200',
                active === t.id ? 'text-black' : 'text-neutral-400 hover:text-white',
              )}
            >
              <span className={cls('font-mono text-[10px] transition-colors', active === t.id ? 'text-neutral-500' : 'text-neutral-600')}>{i + 1}</span>
              {t.label}
              <StatusIcon status={statuses[t.id]} className={cls('size-3.5', active === t.id && '!text-black')} />
            </button>
          ))}
        </nav>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4 lg:sticky lg:top-[72px] lg:self-start">
          <VideoPlayer project={p} />
          <Timeline project={p} />
        </div>
        <div className="min-w-0 rounded-2xl border border-line bg-panel p-4 backdrop-blur-xl sm:p-5 lg:max-h-[calc(100vh-150px)] lg:overflow-y-auto">
          <div key={active} className="fade-in">
            {active === 'source' && <SourcePanel project={p} onNext={() => setTab('asr')} />}
            {active === 'asr' && <TranscribePanel project={p} onNext={() => setTab('translation')} />}
            {active === 'translation' && <TranslatePanel project={p} onNext={() => setTab('voice')} />}
            {active === 'voice' && <VoicePanel project={p} onNext={() => setTab('tts')} />}
            {active === 'tts' && <DubPanel project={p} onNext={() => setTab('export')} onVoice={() => setTab('voice')} />}
            {active === 'export' && <ExportPanel project={p} />}
          </div>
        </div>
      </div>
    </div>
  )
}
