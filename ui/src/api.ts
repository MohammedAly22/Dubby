import type { EngineChoice, EngineInfo, ExportItem, JobsSnapshot, LanguagesPayload, LogEvent, Preset, Project, ProjectSummary, Segment } from './types'

const BASE = 'api'

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
  if (!res.ok) {
    let detail: unknown = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      /* not json */
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return res.json() as Promise<T>
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
  engines: (refresh = false) => req<{ engines: EngineInfo[]; families: Record<string, any> }>(`/engines${refresh ? '?refresh=true' : ''}`),
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
