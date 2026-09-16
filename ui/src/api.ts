import type { EngineCheck, EngineChoice, EngineInfo, ExportItem, GpuInfo, JobsSnapshot, LanguagesPayload, LogEvent, Preset, Project, ProjectSummary, Segment } from './types'

const BASE = 'api'

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, init)
  } catch {
    throw new Error('Can’t reach the Dubby studio — check that it is still running, then try again.')
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`.trim()
    const text = await res.text().catch(() => '')
    if (text) {
      try {
        const body = JSON.parse(text)
        const d = body.detail ?? body.message
        if (typeof d === 'string') detail = d
        else if (Array.isArray(d)) detail = d.map((x: any) => x?.msg ?? JSON.stringify(x)).join('; ') // FastAPI validation errors
      } catch {
        if (!text.trimStart().startsWith('<')) detail = text.slice(0, 300) // plain-text error, not an HTML error page
      }
    }
    if (res.status === 502 || res.status === 503 || res.status === 504) detail = `The studio is not responding (${res.status}) — it may be restarting. ${detail}`
    throw new Error(detail || 'Request failed')
  }
  const type = res.headers.get('content-type') ?? ''
  return (type.includes('json') ? res.json() : res.text()) as Promise<T>
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
})

export interface RunBody {
  engine?: string | null
  params?: Record<string, unknown>
  segment_ids?: string[]
}

export const api = {
  system: () => req<Record<string, any>>('/system'),
  getSettings: () => req<Record<string, any>>('/settings'),
  putSettings: (body: Record<string, unknown>) => req<Record<string, any>>('/settings', json('PUT', body)),
  uploadCookies: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return req<Record<string, any>>('/settings/cookies', { method: 'POST', body: fd })
  },
  deleteCookies: () => req<Record<string, any>>('/settings/cookies', json('DELETE')),
  replaceSource: (id: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return req<Project>(`/projects/${id}/source/upload`, { method: 'POST', body: fd })
  },
  engines: (refresh = false) => req<{ engines: EngineInfo[]; families: Record<string, any>; gpu: GpuInfo | null }>(`/engines${refresh ? '?refresh=true' : ''}`),
  checkEngine: (engine: string, params: Record<string, unknown>, source?: string | null, target?: string | null) =>
    req<EngineCheck>(`/engines/${encodeURIComponent(engine)}/check`, json('POST', { params, source: source ?? null, target: target ?? null })),
  jobs: () => req<JobsSnapshot>('/jobs'),
  stopWorkers: () => req<JobsSnapshot>('/workers/stop', json('POST')),
  logs: (limit = 400) => req<LogEvent[]>(`/logs?limit=${limit}`),
  presets: () => req<Preset[]>('/voices/presets'),
  languages: () => req<LanguagesPayload>('/languages'),
  detectLanguage: (id: string, engine?: string, params?: Record<string, unknown>) => req<{ ok: boolean }>(`/projects/${id}/detect-language`, json('POST', { engine, params })),
  applyRecommendations: (id: string, stages?: string[]) => req<Project>(`/projects/${id}/recommendations/apply`, json('POST', { stages })),
  transcribeVoice: (id: string, body: { engine?: string | null; language?: string | null }) => req<{ ok: boolean }>(`/projects/${id}/voice/transcribe`, json('POST', body)),

  projects: () => req<ProjectSummary[]>('/projects'),
  project: (id: string) => req<Project>(`/projects/${id}`),
  create: (url: string, source_language: string, target: string) => req<Project>('/projects', json('POST', { url, source_language, target })),
  upload: (file: File, source_language: string, target: string) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('source_language', source_language)
    fd.append('target', target)
    return req<Project>('/projects/upload', { method: 'POST', body: fd })
  },
  remove: (id: string) => req<{ ok: boolean }>(`/projects/${id}`, json('DELETE')),
  patchSettings: (id: string, patch: Record<string, unknown>) => req<Project>(`/projects/${id}/settings`, json('PATCH', patch)),
  patchSegment: (id: string, sid: string, patch: Partial<Pick<Segment, 'text' | 'translation' | 'start' | 'end'>>) =>
    req<Segment>(`/projects/${id}/segments/${sid}`, json('PATCH', patch)),
  merge: (id: string, sid: string) => req<Project>(`/projects/${id}/segments/${sid}/merge`, json('POST')),
  split: (id: string, sid: string, word_index: number) => req<Project>(`/projects/${id}/segments/${sid}/split`, json('POST', { word_index })),
  deleteSegment: (id: string, sid: string) => req<Project>(`/projects/${id}/segments/${sid}`, json('DELETE')),
  run: (id: string, stage: string, body: RunBody = {}) => req<{ ok: boolean }>(`/projects/${id}/stages/${stage}/run`, json('POST', body)),
  cancel: (id: string, stage: string) => req<{ cancelled: number }>(`/projects/${id}/stages/${stage}/cancel`, json('POST')),
  setVoice: (id: string, body: Record<string, unknown>) => req<Project>(`/projects/${id}/voice`, json('PUT', body)),
  uploadVoice: (id: string, file: File, ref_text: string, opts: { autoTranscribe?: boolean; engine?: string | null; language?: string | null } = {}) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('ref_text', ref_text)
    fd.append('auto_transcribe', String(opts.autoTranscribe ?? true))
    fd.append('asr_engine', opts.engine ?? '')
    fd.append('language', opts.language ?? '')
    return req<Project>(`/projects/${id}/voice/upload`, { method: 'POST', body: fd })
  },
  render: (id: string, mix?: Record<string, unknown>) => req<{ ok: boolean }>(`/projects/${id}/render`, json('POST', { mix })),
  export: (id: string, directory?: string) => req<ExportItem[]>(`/projects/${id}/export`, json('POST', { directory: directory || null })),
}

export type { EngineChoice }

export const fileUrl = (projectId: string, rel: string, version?: number | string | null, download = false) => {
  const q = new URLSearchParams()
  if (version !== undefined && version !== null) q.set('v', String(version))
  if (download) q.set('download', 'true')
  const qs = q.toString()
  return `${BASE}/projects/${projectId}/files/${rel}${qs ? `?${qs}` : ''}`
}

export const presetAudioUrl = (name: string) => `${BASE}/voices/presets/${encodeURIComponent(name)}/audio`

export function wsUrl() {
  const { protocol, host, pathname } = window.location
  const base = pathname.endsWith('/') ? pathname : pathname.replace(/[^/]*$/, '')
  return `${protocol === 'https:' ? 'wss' : 'ws'}://${host}${base}${BASE}/ws`
}
