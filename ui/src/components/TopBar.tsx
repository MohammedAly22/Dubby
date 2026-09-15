import { Loader2, Settings, SquareTerminal } from 'lucide-react'
import { useStudio } from '../store'
import { cls } from '../utils'
import { ThemeToggle } from './ThemeToggle'

const STAGE_NAMES: Record<string, string> = { asr: 'Transcribing', translation: 'Translating', tts: 'Voicing', separation: 'Separating' }

export function TopBar() {
  const connected = useStudio((s) => s.connected)
  const jobs = useStudio((s) => s.jobs)
  const logsOpen = useStudio((s) => s.logsOpen)
  const setLogsOpen = useStudio((s) => s.setLogsOpen)
  const setSettingsOpen = useStudio((s) => s.setSettingsOpen)
  const errors = useStudio((s) => s.logs.filter((l) => l.level === 'error').length)

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-black/75 backdrop-blur-xl">
      <div className="mx-auto flex h-14 max-w-[1600px] items-center justify-between gap-4 px-4 sm:px-6">
        <a href="#/" className="group flex items-center gap-2.5">
          <span className="flex size-8 items-center justify-center rounded-lg bg-white text-lg leading-none transition-transform duration-300 group-hover:scale-110 group-hover:rotate-[-8deg]">
            <span className="float inline-block">🐨</span>
          </span>
          <span className="text-[17px] font-bold tracking-tight">Dubby</span>
          <span className="hidden rounded-full border border-line-strong px-2 py-0.5 text-[10px] font-medium uppercase tracking-widest text-neutral-500 sm:inline">studio</span>
        </a>

        <div className="flex items-center gap-2">
          {jobs?.current && (
            <div className="hidden items-center gap-2 rounded-full border border-line-strong px-3 py-1 text-xs text-neutral-300 md:flex">
              <Loader2 className="size-3.5 animate-spin" />
              {STAGE_NAMES[jobs.current.stage] ?? jobs.current.stage} · {jobs.current.engine}
              {jobs.queued.length > 0 && <span className="text-neutral-500">+{jobs.queued.length} queued</span>}
            </div>
          )}
          <span className="flex items-center gap-1.5 px-2 text-[11px] text-neutral-500" title={connected ? 'Live connection to the studio' : 'Reconnecting…'}>
            <span className={cls('size-1.5 rounded-full', connected ? 'pulse-ring bg-white' : 'animate-pulse bg-neutral-600')} />
            {connected ? 'live' : 'offline'}
          </span>
          <ThemeToggle />
          <button
            onClick={() => setLogsOpen(!logsOpen)}
            className={cls(
              'relative inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-xs transition-all duration-200 active:scale-95',
              logsOpen ? 'border-white bg-white text-black' : 'border-line-strong text-neutral-300 hover:border-neutral-500 hover:text-white',
            )}
          >
            <SquareTerminal className="size-3.5" /> Logs
            {errors > 0 && !logsOpen && <span className="absolute -top-1 -right-1 size-2.5 rounded-full border-2 border-black bg-white" />}
          </button>
          <button
            onClick={() => setSettingsOpen(true)}
            className="inline-flex size-8 items-center justify-center rounded-full border border-line-strong text-neutral-300 transition-all duration-300 hover:rotate-90 hover:border-neutral-500 hover:text-white"
            title="Settings"
          >
            <Settings className="size-4" />
          </button>
        </div>
      </div>
    </header>
  )
}
