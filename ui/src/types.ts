/** paused: stopped by an API quota, with the results so far kept */
export type StageStatus = 'idle' | 'queued' | 'running' | 'done' | 'error' | 'cancelled' | 'paused'
export type StageName = 'download' | 'asr' | 'translation' | 'voice' | 'tts' | 'separation' | 'render'
/** Spoken language code: en · ar · es · fr · it · hi · zh · ja */
export type SourceLanguage = string
/** Dub language code: arz · arb · en · es · fr · it · hi · zh · ja */
export type TargetDialect = string

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
  /** what the TTS model actually received after normalization (null when normalization was off) */
  normalized?: string | null
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
  /** word timings of the dubbed speech on the rendered timeline */
  dub_words?: Word[]
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
  /** captions drawn into the exported video frames */
  burn_captions?: CaptionMode
}

export interface VoiceConfig {
  mode: 'preset' | 'clip' | 'upload' | 'auto'
  preset?: string | null
  clip_start?: number | null
  clip_end?: number | null
  ref_audio?: string | null
  ref_text: string
  ref_language?: string | null
  ref_text_status: 'idle' | 'queued' | 'running' | 'done' | 'error'
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
  auto_detect?: boolean
  detected_language?: string | null
  detected_probability?: number | null
  detected_candidates?: [string, number][]
}

export interface Recommendation {
  engine: string
  reason: string
  params: Record<string, unknown>
}

export interface LanguagesPayload {
  languages: { code: string; name: string; native: string; flag: string; rtl: boolean; source: boolean; target: boolean; omnivoice_hours: number }[]
  sources: string[]
  targets: string[]
  recommendations: {
    asr: Record<string, Recommendation[]>
    tts: Record<string, Recommendation[]>
    translation: Record<string, Recommendation[]>
  }
}

export interface RenderInfo {
  video?: string | null
  mix?: string | null
  voice?: string | null
  subtitles: Record<string, string>
  version: number
  created_at?: number | null
  /** where each dubbed clip sits in the render */
  clips?: { id: string; start: number; end: number; rate: number }[]
  /** dub caption timing: estimated from clip placement, or aligned with wav2vec2 */
  captions?: { method?: 'estimated' | 'aligned'; aligned?: number; total?: number; version?: number }
  /** rendered videos with burned-in captions, by mode */
  burned?: Record<string, string>
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
  type: 'select' | 'number' | 'bool' | 'text' | 'textarea'
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
  /** approximate VRAM (GB) at default params / cheapest configuration */
  vram_default_gb?: number | null
  vram_min_gb?: number | null
  /** false when no configuration of this engine can run on the detected hardware */
  fits_any?: boolean
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

export interface GpuInfo {
  cuda: boolean
  name: string
  vram_gb: number | null
}

export interface OptionFit {
  required_gb: number | null
  fits: boolean
}

/** Result of POST /api/engines/{id}/check */
export interface EngineCheck {
  engine: string
  gpu: GpuInfo | null
  required_gb: number | null
  needs_cuda: boolean
  fits: boolean
  message: string | null
  suggestion: string | null
  fix: { key: string; value: unknown } | null
  options: Record<string, Record<string, OptionFit>>
  preview: Record<string, string>
}

/** Live model download reported by a worker */
export interface DownloadEvent {
  type: 'download'
  id: string
  name: string
  /** xet transfers report "downloading" then "reconstructing" */
  phase?: 'downloading' | 'reconstructing'
  downloaded: number
  total: number | null
  rate: number
  elapsed: number
  done: boolean
  failed?: boolean
  family?: string
  project_id?: string | null
  stage?: string | null
  engine?: string | null
}

export type CaptionMode = 'none' | 'original' | 'dub' | 'both'

/** One tracked unit of work: a job, a VAD pass, an API call, a TTS batch, a model load… */
export interface RequestEvent {
  type: 'request'
  id: string
  kind: string
  label: string
  level: 'job' | 'call'
  status: 'queued' | 'running' | 'done' | 'error' | 'cancelled'
  project_id?: string | null
  stage?: string | null
  engine?: string | null
  family?: string | null
  queued?: number
  started?: number
  ended?: number
  duration?: number
  error?: string | null
  detail?: Record<string, unknown>
}

/** A span of terminal text: its colour name (rich) and weight */
export interface ConsoleSpan {
  t: string
  c: string | null
  b: boolean
}

/** One line of the studio terminal, mirrored into the Logs drawer */
export interface ConsoleRecord {
  type: 'console'
  id: string
  ts: number
  kind: 'line' | 'rule' | 'panel' | 'table'
  project_id?: string | null
  tone?: string | null
  spans?: ConsoleSpan[]
  title?: string
  lines?: ConsoleSpan[][]
  columns?: string[]
  rows?: string[][]
}

/** A Gemini daily quota stopped a stage */
export interface QuotaEvent {
  type: 'quota'
  project_id: string
  stage: string
  model: string
  limit?: string | null
  generated: number
  remaining: number
  voiced_total: number
  message: string
}
