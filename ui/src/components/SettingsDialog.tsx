import { useEffect, useState } from 'react'
import { Cpu, Power, RefreshCw, Save } from 'lucide-react'
import { api } from '../api'
import { useStudio } from '../store'
import { CookiesField } from './CookiesField'
import { GeminiKeyField } from './GeminiKeyField'
import { Select } from './Select'
import { Button, Field, Modal, Switch, inputCls } from './ui'

const FAMILIES = ['core', 'qwen', 'nemo'] as const

export function SettingsDialog() {
  const open = useStudio((s) => s.settingsOpen)
  const setOpen = useStudio((s) => s.setSettingsOpen)
  const toast = useStudio((s) => s.toast)
  const loadEngines = useStudio((s) => s.loadEngines)
  const enginesLoading = useStudio((s) => s.enginesLoading)
  const [settings, setSettings] = useState<Record<string, any> | null>(null)
  const [system, setSystem] = useState<Record<string, any> | null>(null)
  const [token, setToken] = useState('')
  const [saving, setSaving] = useState(false)

  const refresh = () => {
    api.getSettings().then(setSettings).catch((e) => toast(e.message, 'error'))
    api.system().then(setSystem).catch(() => {})
  }

  useEffect(() => {
    if (open) refresh()
  }, [open])

  const save = async () => {
    if (!settings) return
    setSaving(true)
    try {
      const body: Record<string, unknown> = {
        device: settings.device,
        exclusive_gpu: settings.exclusive_gpu,
        worker_python: settings.worker_python,
        proxy: settings.proxy || null,
        node_path: settings.node_path || null,
        export_dir: settings.export_dir || null,
      }
      if (token.trim()) body.hf_token = token.trim()
      setSettings(await api.putSettings(body))
      setToken('')
      toast('Settings saved — re-checking engines…', 'success')
      setTimeout(() => loadEngines(true), 300)
    } catch (e: any) {
      toast(e.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  const set = (k: string, v: unknown) => setSettings((s) => (s ? { ...s, [k]: v } : s))

  return (
    <Modal open={open} onClose={() => setOpen(false)} title="⚙️  Studio settings" wide>
      {!settings ? (
        <div className="shimmer h-64 rounded-2xl" />
      ) : (
        <div className="flex flex-col gap-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field
              label="Hugging Face token"
              hint={
                settings.hf_token
                  ? `Configured: ${settings.hf_token_preview}${settings.hf_token_source === 'environment' ? ' (from the environment / Colab)' : ''}. Paste a new one to replace it.`
                  : 'Needed for gated models (Cohere Transcribe, IndicF5).'
              }
            >
              <input type="password" className={inputCls} placeholder={settings.hf_token ? settings.hf_token_preview : 'hf_…'} value={token} onChange={(e) => setToken(e.target.value)} />
            </Field>
            <Field label="Device" hint={`Resolved: ${settings.device_resolved}`}>
              <Select
                value={settings.device}
                onChange={(v) => set('device', v)}
                options={[
                  { value: 'auto', label: 'Auto', description: 'CUDA when available, otherwise CPU' },
                  { value: 'cuda', label: 'CUDA GPU', description: 'Fastest — requires an NVIDIA GPU' },
                  { value: 'cpu', label: 'CPU', description: 'Slow, but works everywhere' },
                ]}
              />
            </Field>
            <Field label="Export directory" hint="Where exported videos are saved on the studio machine.">
              <input className={inputCls} placeholder={`${settings.home}/exports`} value={settings.export_dir ?? ''} onChange={(e) => set('export_dir', e.target.value)} />
            </Field>
            <Field label="Download proxy (optional)" hint="Not needed normally — YouTube downloads use automatic PO tokens. e.g. socks5://host:1080">
              <input className={inputCls} placeholder="none" value={settings.proxy ?? ''} onChange={(e) => set('proxy', e.target.value)} />
            </Field>
            <Field label="Gemini API key" className="sm:col-span-2">
              <GeminiKeyField settings={settings} onChange={setSettings} />
            </Field>
            <Field label="YouTube cookies (optional)" className="sm:col-span-2">
              <CookiesField configured={!!settings.cookies_configured} onChange={(s) => setSettings(s)} />
            </Field>
            <Field label="Node.js path" hint={`Resolved: ${settings.node_resolved ?? 'not found'} (used by yt-dlp)`}>
              <input className={inputCls} placeholder="auto" value={settings.node_path ?? ''} onChange={(e) => set('node_path', e.target.value)} />
            </Field>
            <div className="flex items-end pb-2">
              <Switch checked={!!settings.exclusive_gpu} onChange={(v) => set('exclusive_gpu', v)} label="Stop other engine families before starting one (frees VRAM)" />
            </div>
          </div>

          <div>
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-neutral-500">Engine family interpreters</div>
            <div className="overflow-hidden rounded-2xl border border-line">
              {FAMILIES.map((f) => {
                const fam = system?.families?.[f] ?? {}
                return (
                  <div key={f} className="grid gap-2 border-b border-line p-3 last:border-0 sm:grid-cols-[90px_1fr_220px] sm:items-center">
                    <div className="font-mono text-sm">{f}</div>
                    <input
                      className={`${inputCls} font-mono text-xs`}
                      placeholder={settings.worker_python_resolved?.[f]}
                      value={settings.worker_python?.[f] ?? ''}
                      onChange={(e) => set('worker_python', { ...settings.worker_python, [f]: e.target.value })}
                    />
                    <div className="flex items-center gap-2 text-xs text-neutral-400">
                      <Cpu className="size-3.5" />
                      {fam.error ? <span className="truncate text-neutral-500" title={fam.error}>{fam.error}</span> : fam.torch ? `py ${fam.python_version} · torch ${fam.torch.version} · ${fam.torch.device}` : `py ${fam.python_version ?? '?'} · no torch`}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="flex flex-wrap justify-between gap-2">
            <div className="flex gap-2">
              <Button icon={<RefreshCw className="size-4" />} loading={enginesLoading} onClick={() => loadEngines(true).then(refresh)}>
                Re-check engines
              </Button>
              <Button icon={<Power className="size-4" />} onClick={() => api.stopWorkers().then(() => toast('Workers stopped — GPU memory released', 'success'))}>
                Stop workers
              </Button>
            </div>
            <Button variant="primary" icon={<Save className="size-4" />} loading={saving} onClick={save}>
              Save settings
            </Button>
          </div>
        </div>
      )}
    </Modal>
  )
}
