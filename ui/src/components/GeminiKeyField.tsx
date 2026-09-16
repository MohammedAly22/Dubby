import { useState } from 'react'
import { CheckCircle2, ExternalLink, KeyRound, Trash2 } from 'lucide-react'
import { api } from '../api'
import { useStudio } from '../store'
import { Button, inputCls } from './ui'

/** Paste a Gemini API key, verify it with one tiny request, and save it only when it works. */
export function GeminiKeyField({ settings, onChange }: { settings: Record<string, any>; onChange: (s: Record<string, any>) => void }) {
  const toast = useStudio((s) => s.toast)
  const loadEngines = useStudio((s) => s.loadEngines)
  const loadLanguages = useStudio((s) => s.loadLanguages)
  const [key, setKey] = useState('')
  const [testing, setTesting] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null)
  const configured = !!settings.gemini_api_key

  const refreshEngines = () => {
    loadEngines(true)
    loadLanguages()
  }

  const test = async () => {
    setTesting(true)
    setResult(null)
    try {
      const r = await api.saveGeminiKey(key.trim())
      onChange(r.settings)
      if (r.ok) {
        setKey('')
        setResult({ ok: true, text: `Key works — ${r.model} answered in ${r.latency_ms} ms. Saved.` })
        toast('Gemini API key verified and saved', 'success')
        refreshEngines()
      } else {
        setResult({ ok: false, text: r.error ?? 'The key did not work.' })
      }
    } catch (e: any) {
      setResult({ ok: false, text: e.message })
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex h-9 items-center gap-2 rounded-xl border border-line-strong px-3 text-sm">
          {configured ? <CheckCircle2 className="size-4" /> : <KeyRound className="size-4" />}
          {configured ? <span className="font-mono text-xs">{settings.gemini_key_preview}</span> : 'Not configured'}
        </span>
        <input
          type="password"
          autoComplete="off"
          className={`${inputCls} min-w-52 flex-1 font-mono text-xs`}
          placeholder={configured ? 'Paste a new key to replace it' : 'Paste your Gemini API key'}
          value={key}
          onChange={(e) => setKey(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && key.trim() && test()}
        />
        <Button variant="primary" loading={testing} disabled={!key.trim()} onClick={test}>
          Test &amp; save
        </Button>
        {configured && (
          <Button
            icon={<Trash2 className="size-4" />}
            onClick={() =>
              api
                .removeGeminiKey()
                .then((s) => {
                  onChange(s)
                  setResult(null)
                  toast('Gemini API key removed')
                  refreshEngines()
                })
                .catch((e) => toast(e.message, 'error'))
            }
          >
            Remove
          </Button>
        )}
      </div>
      {result && <p className={`fade-in text-xs ${result.ok ? 'text-neutral-200' : 'text-neutral-400'}`}>{result.ok ? '✓ ' : '✖ '}{result.text}</p>}
      <p className="text-xs leading-relaxed text-neutral-500">
        Enables Gemini for transcription, translation (the default translator while a key is set) and speech with 30 preset voices — no GPU needed.{' '}
        <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 underline-offset-2 hover:text-white hover:underline">
          Get a key <ExternalLink className="size-3" />
        </a>
      </p>
    </div>
  )
}
