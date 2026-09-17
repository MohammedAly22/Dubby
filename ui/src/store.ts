import { create } from 'zustand'
import { api, fileUrl, wsUrl, type RunBody } from './api'
import { playPreview } from './player'
import type { AsrPreviewSegment, DownloadEvent, EngineChoice, EngineInfo, GpuInfo, JobsSnapshot, LanguagesPayload, LogEvent, Project, ProjectSummary, Recommendation, RequestEvent, Segment } from './types'
import { debounceByKey } from './utils'

export interface Toast {
  id: number
  kind: 'info' | 'success' | 'error'
  message: string
}

/** Options for the studio's own confirmation dialog (never window.confirm). */
export interface ConfirmOptions {
  title: string
  message?: string
  confirmLabel?: string
  cancelLabel?: string
  tone?: 'default' | 'danger'
  icon?: string
}

export interface ConfirmRequest extends ConfirmOptions {
  id: number
  resolve: (ok: boolean) => void
}

interface StudioState {
  connected: boolean
  backendReachable: boolean
  projects: ProjectSummary[]
  project: Project | null
  engines: EngineInfo[]
  enginesLoading: boolean
  languages: LanguagesPayload | null
  loadLanguages: () => Promise<void>
  families: Record<string, any>
  jobs: JobsSnapshot | null
  logs: LogEvent[]
  toasts: Toast[]
  asrPreview: { projectId: string; segments: AsrPreviewSegment[] } | null
  selectedId: string | null
  clipDraft: { start: number | null; end: number | null }
  logsOpen: boolean
  settingsOpen: boolean
  confirmRequest: ConfirmRequest | null
  /** in-flight (and just-finished) model downloads, by id */
  downloads: Record<string, DownloadEvent>
  /** GPU seen by the engine doctor (null until known) */
  gpu: GpuInfo | null
  /** tracked requests (jobs, VAD, API calls, TTS batches…), by id in arrival order */
  requests: Record<string, RequestEvent>

  connect: () => void
  loadProjects: (silent?: boolean) => Promise<void>
  openProject: (id: string, silent?: boolean) => Promise<void>
  closeProject: () => void
  loadEngines: (refresh?: boolean) => Promise<void>
  toast: (message: string, kind?: Toast['kind']) => void
  dismiss: (id: number) => void
  confirm: (options: ConfirmOptions) => Promise<boolean>
  resolveConfirm: (ok: boolean) => void
  /** regenerate one clip, then play it and notify when it lands */
  regenerateClip: (sid: string) => Promise<void>
  /** retranslate one line and notify when it lands */
  retranslateLine: (sid: string) => Promise<void>
  select: (id: string | null) => void
  setClipDraft: (draft: Partial<{ start: number | null; end: number | null }>) => void
  setLogsOpen: (open: boolean) => void
  setSettingsOpen: (open: boolean) => void

  patchSettings: (patch: Record<string, unknown>) => void
  saveChoice: (stage: 'asr' | 'translation' | 'tts', choice: EngineChoice) => void
  runStage: (stage: string, body?: RunBody) => Promise<boolean>
  cancelStage: (stage: string) => Promise<void>
  updateSegment: (sid: string, patch: Partial<Pick<Segment, 'text' | 'translation' | 'start' | 'end'>>) => Promise<void>
}

let toastId = 0
let socket: WebSocket | null = null
let retry = 0
let listTimer: ReturnType<typeof setTimeout> | null = null
let pollTimer: ReturnType<typeof setTimeout> | null = null
let pollDelay = 2500

/**
 * HTTP polling fallback for proxies that block websockets (e.g. notebook tunnels).
 * Backs off to 15 s while the backend is unreachable and never toasts.
 */
function startPolling() {
  if (pollTimer) return
  const tick = async () => {
    pollTimer = null
    const s = useStudio.getState()
    if (s.connected) {
      pollDelay = 2500
      return
    }
    try {
      const jobs = await api.jobs()
      useStudio.setState({ jobs, backendReachable: true })
      if (s.project) await s.openProject(s.project.id, true)
      else await s.loadProjects(true)
      pollDelay = 2500
    } catch {
      useStudio.setState({ backendReachable: false })
      pollDelay = Math.min(pollDelay * 2, 15000)
    }
    pollTimer = setTimeout(tick, pollDelay)
  }
  pollTimer = setTimeout(tick, pollDelay)
}

const debouncedPatch = debounceByKey((pid: string, patch: Record<string, unknown>) => {
  api.patchSettings(pid, patch).catch((e) => useStudio.getState().toast(e.message, 'error'))
}, 450)

export const useStudio = create<StudioState>((set, get) => ({
  connected: false,
  backendReachable: true,
  projects: [],
  project: null,
  engines: [],
  enginesLoading: false,
  languages: null,
  loadLanguages: async () => {
    try {
      set({ languages: await api.languages() })
    } catch {
      /* retried on reconnect */
    }
  },
  families: {},
  jobs: null,
  logs: [],
  toasts: [],
  confirmRequest: null,
  downloads: {},
  gpu: null,
  requests: {},
  asrPreview: null,
  selectedId: null,
  clipDraft: { start: null, end: null },
  logsOpen: false,
  settingsOpen: false,

  connect: () => {
    if (socket && socket.readyState <= 1) return
    socket = new WebSocket(wsUrl())
    socket.onopen = () => {
      retry = 0
      set({ connected: true, backendReachable: true })
      api.logs().then((logs) => set({ logs })).catch(() => {})
      if (!get().languages) get().loadLanguages()
      const p = get().project
      if (p) get().openProject(p.id)
    }
    socket.onclose = () => {
      set({ connected: false })
      startPolling()
      retry = Math.min(retry + 1, 5)
      setTimeout(() => get().connect(), Math.min(15000, 500 * 2 ** retry))
    }
    socket.onmessage = (msg) => handleEvent(JSON.parse(msg.data))
  },

  loadProjects: async (silent = false) => {
    try {
      set({ projects: await api.projects() })
    } catch (e: any) {
      if (silent) throw e
      get().toast(e.message, 'error')
    }
  },

  openProject: async (id, silent = false) => {
    try {
      const project = await api.project(id)
      set((s) => ({ project, asrPreview: s.asrPreview?.projectId === id ? s.asrPreview : null }))
    } catch (e: any) {
      if (silent) throw e
      get().toast(e.message, 'error')
    }
  },

  closeProject: () => set({ project: null, asrPreview: null, selectedId: null }),

  loadEngines: async (refresh = false) => {
    set({ enginesLoading: true })
    try {
      const data = await api.engines(refresh)
      set({ engines: data.engines, families: data.families, gpu: data.gpu ?? null })
    } catch (e: any) {
      get().toast(`Engines: ${e.message}`, 'error')
    } finally {
      set({ enginesLoading: false })
    }
  },

  toast: (message, kind = 'info') => {
    const id = ++toastId
    set((s) => ({ toasts: [...s.toasts, { id, kind, message }] }))
    setTimeout(() => get().dismiss(id), kind === 'error' ? 7000 : 4000)
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  confirm: (options) =>
    new Promise<boolean>((resolve) => {
      get().confirmRequest?.resolve(false) // never leave an earlier question hanging
      set({ confirmRequest: { ...options, id: ++toastId, resolve } })
    }),
  resolveConfirm: (ok) => {
    const request = get().confirmRequest
    if (!request) return
    set({ confirmRequest: null })
    request.resolve(ok)
  },
  select: (id) => set({ selectedId: id }),
  setClipDraft: (draft) => set((s) => ({ clipDraft: { ...s.clipDraft, ...draft } })),
  setLogsOpen: (logsOpen) => set({ logsOpen }),
  setSettingsOpen: (settingsOpen) => set({ settingsOpen }),

  patchSettings: (patch) => {
    const p = get().project
    if (!p) return
    const merged = deepMerge(p.settings as any, patch)
    set({ project: { ...p, settings: merged } })
    debouncedPatch(`${p.id}:${Object.keys(patch).join(',')}`, p.id, patch)
  },

  saveChoice: (stage, choice) => get().patchSettings({ [stage]: choice }),

  runStage: async (stage, body = {}) => {
    const p = get().project
    if (!p) return false
    try {
      await api.run(p.id, stage, body)
      return true
    } catch (e: any) {
      get().toast(e.message, 'error')
      return false
    }
  },

  regenerateClip: async (sid) => {
    const p = get().project
    if (!p) return
    const key = `${p.id}:${sid}`
    pendingClips.set(key, Date.now())
    if (!(await get().runStage('tts', { segment_ids: [sid] }))) pendingClips.delete(key)
  },

  retranslateLine: async (sid) => {
    const p = get().project
    if (!p) return
    const key = `${p.id}:${sid}`
    pendingLines.set(key, Date.now())
    if (!(await get().runStage('translation', { segment_ids: [sid] }))) pendingLines.delete(key)
  },

  cancelStage: async (stage) => {
    const p = get().project
    if (!p) return
    try {
      await api.cancel(p.id, stage)
      get().toast('Cancelling…')
    } catch (e: any) {
      get().toast(e.message, 'error')
    }
  },

  updateSegment: async (sid, patch) => {
    const p = get().project
    if (!p) return
    set({ project: { ...p, segments: p.segments.map((s) => (s.id === sid ? { ...s, ...patch } : s)) } })
    try {
      await api.patchSegment(p.id, sid, patch)
    } catch (e: any) {
      get().toast(e.message, 'error')
      get().openProject(p.id)
    }
  },
}))

/** Ranked engine recommendations for a stage and language pair. */
export function recommendationsFor(
  payload: LanguagesPayload | null,
  kind: EngineInfo['kind'],
  source?: string,
  target?: string,
): Recommendation[] {
  if (!payload) return []
  const r = payload.recommendations
  if (kind === 'asr') return (source && r.asr[source]) || []
  if (kind === 'tts') return (target && r.tts[target]) || []
  if (kind === 'translation') return (source && target && r.translation[`${source}>${target}`]) || []
  return []
}

function deepMerge(base: Record<string, any>, patch: Record<string, any>): any {
  const out: Record<string, any> = { ...base }
  for (const [k, v] of Object.entries(patch)) {
    if (v && typeof v === 'object' && !Array.isArray(v) && k !== 'params' && typeof out[k] === 'object') out[k] = deepMerge(out[k], v)
    else out[k] = v
  }
  return out
}

function refreshListSoon() {
  if (listTimer) return
  listTimer = setTimeout(() => {
    listTimer = null
    if (!useStudio.getState().project) useStudio.getState().loadProjects()
  }, 800)
}

// ------------------------------------------------------------- notifications
/** single-clip regenerations / single-line retranslations awaiting their result (`${project}:${segment}`) */
const pendingClips = new Map<string, number>()
const pendingLines = new Map<string, number>()
/** last status seen per `${project}:${stage}`, so each transition notifies once */
const stageSeen = new Map<string, string>()
const downloadTimers = new Map<string, ReturnType<typeof setTimeout>>()

const STAGE_DONE: Record<string, string> = {
  download: '⬇️ Video ready',
  langid: '🌍 Spoken language detected',
  asr: '🎙️ Transcription complete',
  translation: '🌍 Translation complete',
  voice: '🗣️ Reference voice transcribed',
  tts: '🔊 All clips generated',
  separation: '🎚️ Vocals and background separated',
  render: '🎬 Dub rendered',
  captions: '💬 Dub captions aligned',
  export: '📦 Captioned video exported',
}
const STAGE_LABEL: Record<string, string> = {
  download: 'Download',
  langid: 'Language detection',
  asr: 'Transcription',
  translation: 'Translation',
  voice: 'Reference voice',
  tts: 'Voice generation',
  separation: 'Separation',
  render: 'Rendering',
  captions: 'Caption alignment',
  export: 'Export',
}

const forProject = (map: Map<string, number>, projectId: string) => [...map.keys()].filter((k) => k.startsWith(`${projectId}:`))

function notifyStage(e: any, previous: string | undefined) {
  const status: string = e.state.status
  if (previous === status || (status !== 'done' && status !== 'error' && status !== 'cancelled')) return
  const pendingMap = e.stage === 'tts' ? pendingClips : e.stage === 'translation' ? pendingLines : null
  const pending = pendingMap ? forProject(pendingMap, e.project_id) : []
  if (status === 'cancelled') {
    pending.forEach((k) => pendingMap!.delete(k))
    return
  }
  const s = useStudio.getState()
  const title = s.project?.id === e.project_id ? null : s.projects.find((p) => p.id === e.project_id)?.title
  const where = title ? ` · ${title}` : ''
  if (status === 'done') {
    if (pending.length) return // the clip / line gets its own, more specific notification
    if (e.stage === 'export') return // the export event lists the saved files
    s.toast(`${STAGE_DONE[e.stage] ?? `${e.stage} finished`}${e.state.message ? ` — ${e.state.message}` : ''}${where}`, 'success')
  } else {
    pending.forEach((k) => pendingMap!.delete(k))
    s.toast(`${STAGE_LABEL[e.stage] ?? e.stage} failed${where}: ${e.state.error || e.state.message || 'unknown error'}`, 'error')
  }
}

function notifySegment(e: any) {
  const key = `${e.project_id}:${e.segment.id}`
  const s = useStudio.getState()
  const index = s.project && s.project.id === e.project_id ? s.project.segments.findIndex((x) => x.id === e.segment.id) : -1
  const label = index >= 0 ? `#${index + 1}` : ''
  if (pendingClips.has(key)) {
    const tts = e.segment.tts
    if (tts.status === 'done' && tts.audio) {
      pendingClips.delete(key)
      s.toast(`🔊 Clip ${label} generated — playing it now`, 'success')
      playPreview(fileUrl(e.project_id, tts.audio, tts.version))
    } else if (tts.status === 'error') {
      pendingClips.delete(key)
      s.toast(`Clip ${label} failed: ${tts.error ?? 'unknown error'}`, 'error')
    }
  }
  if (pendingLines.has(key)) {
    if (e.segment.translation_status === 'done') {
      pendingLines.delete(key)
      s.toast(`🌍 Line ${label} retranslated`, 'success')
    } else if (e.segment.translation_status === 'error') {
      pendingLines.delete(key)
      s.toast(`Line ${label} failed: ${e.segment.translation_error ?? 'unknown error'}`, 'error')
    }
  }
}

function handleDownload(d: DownloadEvent) {
  const timer = downloadTimers.get(d.id)
  if (timer) clearTimeout(timer)
  useStudio.setState((s) => ({ downloads: { ...s.downloads, [d.id]: d } }))
  if (d.done) {
    // keep finished rows visible briefly so people see them complete
    downloadTimers.set(
      d.id,
      setTimeout(() => {
        downloadTimers.delete(d.id)
        useStudio.setState((s) => {
          const { [d.id]: _gone, ...rest } = s.downloads
          return { downloads: rest }
        })
      }, 4000),
    )
  }
}

function handleEvent(e: any) {
  const state = useStudio.getState()
  const current = state.project
  switch (e.type) {
    case 'batch':
      // one frame carrying several events — React batches the renders
      for (const inner of e.events) handleEvent(inner)
      break
    case 'hello':
      useStudio.setState({
        jobs: e.jobs,
        downloads: Object.fromEntries(((e.downloads ?? []) as DownloadEvent[]).map((d) => [d.id, d])),
        requests: Object.fromEntries(((e.requests ?? []) as RequestEvent[]).map((r) => [r.id, r])),
      })
      break
    case 'request':
      useStudio.setState((s) => {
        const next: Record<string, RequestEvent> = { ...s.requests, [e.id]: e as RequestEvent }
        const ids = Object.keys(next)
        if (ids.length > 2000) for (const id of ids.slice(0, ids.length - 2000)) delete next[id]
        return { requests: next }
      })
      break
    case 'requests_cleared':
      useStudio.setState((s) => ({ requests: Object.fromEntries(Object.entries(s.requests).filter(([, r]) => r.status === 'running' || r.status === 'queued')) }))
      break
    case 'jobs':
      useStudio.setState({ jobs: e.jobs })
      break
    case 'download':
      handleDownload(e)
      break
    case 'project':
      if (current && e.project.id === current.id) useStudio.setState({ project: e.project })
      refreshListSoon()
      break
    case 'project_deleted':
      useStudio.setState((s) => ({ projects: s.projects.filter((p) => p.id !== e.project_id) }))
      break
    case 'stage': {
      const key = `${e.project_id}:${e.stage}`
      const previous = stageSeen.get(key) ?? (current && e.project_id === current.id ? current.stages[e.stage]?.status : undefined)
      stageSeen.set(key, e.state.status)
      if (current && e.project_id === current.id) {
        useStudio.setState({ project: { ...current, stages: { ...current.stages, [e.stage]: e.state } } })
      }
      notifyStage(e, previous)
      if (e.state.status === 'done' || e.state.status === 'error') refreshListSoon()
      break
    }
    case 'segment':
      if (current && e.project_id === current.id) {
        const segments = current.segments.slice()
        const idx = segments[e.index]?.id === e.segment.id ? e.index : segments.findIndex((s) => s.id === e.segment.id)
        if (idx >= 0) {
          segments[idx] = e.segment
          useStudio.setState({ project: { ...current, segments } })
        }
      }
      notifySegment(e)
      break
    case 'segments':
      if (e.partial) {
        useStudio.setState({ asrPreview: { projectId: e.project_id, segments: e.segments } })
      } else if (e.final) {
        useStudio.setState({ asrPreview: null })
        if (current && e.project_id === current.id) useStudio.setState({ project: { ...current, segments: e.segments } })
      }
      break
    case 'log':
      useStudio.setState((s) => ({ logs: s.logs.length > 1500 ? [...s.logs.slice(-1000), e] : [...s.logs, e] }))
      break
    case 'engines':
      state.loadEngines(false)
      break
    case 'export':
      state.toast(`📦 Exported ${e.items.length} files to disk`, 'success')
      break
  }
}
