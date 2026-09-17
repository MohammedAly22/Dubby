import { useEffect, useMemo, useState } from 'react'
import { Check, Loader2, Pause, Play } from 'lucide-react'
import { api, geminiVoicePreviewUrl } from '../api'
import { Segmented } from '../components/ui'
import { playPreview, stopPreview } from '../player'
import { useStudio } from '../store'
import type { Project } from '../types'
import { cls } from '../utils'

type Voice = { name: string; style: string; gender: 'female' | 'male' }

/** Gemini TTS doesn't clone voices: pick one of its 30 preset voices, with a sample in the dub language. */
export function GeminiVoicePicker({ project }: { project: Project }) {
  const toast = useStudio((s) => s.toast)
  const saveChoice = useStudio((s) => s.saveChoice)
  const [voices, setVoices] = useState<Voice[] | null>(null)
  const [gender, setGender] = useState<'all' | 'female' | 'male'>('all')
  const [loading, setLoading] = useState<string | null>(null)
  const [playing, setPlaying] = useState<string | null>(null)
  const choice = project.settings.tts
  const current = String(choice.params.voice ?? 'Kore')

  useEffect(() => {
    api.geminiVoices().then(setVoices).catch((e) => toast(e.message, 'error'))
    return () => stopPreview()
  }, [toast])

  const shown = useMemo(() => (voices ?? []).filter((v) => gender === 'all' || v.gender === gender), [voices, gender])

  const preview = (voice: string) => {
    if (playing === voice) {
      stopPreview()
      setPlaying(null)
      return
    }
    const url = geminiVoicePreviewUrl(voice, project.settings.target)
    setLoading(voice)
    const audio = playPreview(url, () => setPlaying(null))
    audio.onplaying = () => {
      setLoading(null)
      setPlaying(voice)
    }
    audio.onerror = () => {
      setLoading(null)
      setPlaying(null)
      // the endpoint explains what went wrong (no key, quota…) as JSON
      fetch(url)
        .then((r) => r.json())
        .then((d) => toast(d.detail ?? 'Could not preview this voice', 'error'))
        .catch(() => toast('Could not preview this voice', 'error'))
    }
  }

  const select = (voice: string) => {
    saveChoice('tts', { engine: choice.engine, params: { ...choice.params, voice } })
    toast(`Gemini voice: ${voice}`, 'success')
  }

  if (!voices) return <div className="shimmer h-48 rounded-2xl" />

  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-line p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-sm font-semibold">Gemini preset voices</div>
          <div className="text-xs text-neutral-500">Gemini TTS speaks with a preset voice, so no reference clip is needed. Samples are generated once in the dub language, then cached.</div>
        </div>
        <Segmented<'all' | 'female' | 'male'>
          size="sm"
          value={gender}
          onChange={setGender}
          options={[
            { value: 'all', label: 'all' },
            { value: 'female', label: 'female' },
            { value: 'male', label: 'male' },
          ]}
        />
      </div>
      <div className="stagger grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {shown.map((v, i) => {
          const active = v.name === current
          return (
            <div
              key={v.name}
              style={{ ['--i' as string]: Math.min(i, 12) }}
              className={cls('lift flex items-center gap-3 rounded-2xl border p-2.5', active ? 'border-white bg-white/[.06]' : 'border-line hover:border-neutral-600')}
            >
              <button
                type="button"
                onClick={() => preview(v.name)}
                title={`Listen to ${v.name}`}
                className={cls(
                  'flex size-9 shrink-0 items-center justify-center rounded-full transition-all duration-200 active:scale-90',
                  playing === v.name ? 'pulse-ring bg-white text-black' : 'border border-line-strong hover:bg-white hover:text-black',
                )}
              >
                {loading === v.name ? <Loader2 className="size-4 animate-spin" /> : playing === v.name ? <Pause className="size-4" /> : <Play className="ml-0.5 size-4" />}
              </button>
              <button type="button" onClick={() => select(v.name)} className="flex min-w-0 flex-1 items-center justify-between gap-2 text-left">
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold">{v.name}</span>
                  <span className="block text-[11px] text-neutral-500">
                    {v.style} · {v.gender}
                  </span>
                </span>
                {active && <Check className="size-4 shrink-0" />}
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
