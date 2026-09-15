export type StageStatus = 'idle' | 'queued' | 'running' | 'done' | 'error' | 'cancelled'
export type StageName = 'download' | 'asr' | 'translation' | 'voice' | 'tts' | 'separation' | 'render'
export type SourceLanguage = 'en' | 'ar'
export type TargetDialect = 'arz' | 'arb'

export interface StageState {
  status: StageStatus
  progress: number
  message: string
  engine?: string | null
  started_at?: number | null
  finished_at?: number | null
  error?: string | null
}

export interface Word {
  text: string
  start: number
  end: number
  score?: number | null
}

export interface TTSState {
  status: 'pending' | 'queued' | 'running' | 'done' | 'error'
  audio?: string | null
  duration?: number | null
  text?: string | null
  engine?: string | null
  version: number
  error?: string | null
}

export interface Segment {
  id: string
  start: number
  end: number
  text: string
  words: Word[]
  translation: string
  translation_status: 'pending' | 'queued' | 'running' | 'done' | 'error'
  translation_source?: string | null
  translation_error?: string | null
  tts: TTSState
}

export interface EngineChoice {
  engine: string | null
  params: Record<string, unknown>
}

export interface MixConfig {
  background: 'original' | 'separated' | 'none'
  background_volume: number
  outside_volume: number
  dub_volume: number
  fit_mode: 'stretch' | 'trim' | 'none'
  max_speedup: number
  subtitles: boolean
}

export interface VoiceConfig {
  mode: 'preset' | 'clip' | 'upload' | 'auto'
  preset?: string | null
  clip_start?: number | null
  clip_end?: number | null
  ref_audio?: string | null
  ref_text: string
  upload_name?: string | null
}

export interface ProjectSettings {
  source_language: SourceLanguage
  target: TargetDialect
  asr: EngineChoice
  translation: EngineChoice
  tts: EngineChoice
  mix: MixConfig
  max_chunk_seconds: number
  min_chunk_seconds: number
  max_word_gap: number
}

export interface SourceInfo {
  kind: 'youtube' | 'upload'
  url?: string | null
  title?: string | null
  uploader?: string | null
  duration?: number | null
  thumbnail?: string | null
  video?: string | null
  audio16k?: string | null
  audio_hq?: string | null
  vocals?: string | null
  background?: string | null
}

export interface RenderInfo {
  video?: string | null
  mix?: string | null
  voice?: string | null
  subtitles: Record<string, string>
  version: number
  created_at?: number | null
}

export interface ExportItem {
  kind: string
  path: string
  rel?: string | null
  size: number
  created_at: number
}

export interface Project {
  id: string
  title: string
  created_at: number
  updated_at: number
  source: SourceInfo
  settings: ProjectSettings
  voice: VoiceConfig
  stages: Record<string, StageState>
  segments: Segment[]
  render: RenderInfo
  exports: ExportItem[]
}

export interface ProjectSummary {
  id: string
  title: string
  created_at: number
  updated_at: number
  source: SourceInfo
  settings: { source_language: SourceLanguage; target: TargetDialect }
  stages: Record<string, StageState>
  segments: number
  translated: number
  voiced: number
  render: RenderInfo
}

export interface ParamSpec {
  key: string
  label: string
  type: 'select' | 'number' | 'bool' | 'text'
  default: unknown
  options?: { value: unknown; label: string }[] | null
  min?: number | null
  max?: number | null
  step?: number | null
  help: string
}

export interface EngineInfo {
  id: string
  kind: 'asr' | 'translation' | 'tts' | 'separation'
  name: string
  family: string
  description: string
  source_languages: string[]
  targets: string[]
  requires: string[]
  install: string
  params: ParamSpec[]
  links: Record<string, string>
  gated: boolean
  badges: string[]
  available: boolean
  missing: string[]
  family_error?: string | null
}

export interface LogEvent {
  type: 'log'
  level: 'debug' | 'info' | 'warning' | 'error'
  message: string
  source: string
  project_id?: string | null
  ts: number
}

export interface Preset {
  id: string
  name: string
  gender: string
  text: string
  filename: string
}

export interface JobDesc {
  id: string
  project_id: string
  stage: string
  engine: string
  status: string
  created_at: number
}

export interface JobsSnapshot {
  current: JobDesc | null
  queued: JobDesc[]
  workers: Record<string, { alive: boolean; device?: string | null; python?: string | null; pid?: number | null }>
}

export interface AsrPreviewSegment {
  start: number
  end: number
  text: string
}
