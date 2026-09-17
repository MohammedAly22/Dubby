import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { AlertTriangle, ChevronDown, Cpu, ExternalLink, Lock, RotateCcw, SlidersHorizontal, Sparkles, Star, Wand2 } from 'lucide-react'
import { api } from '../api'
import { recommendationsFor, useStudio } from '../store'
import type { EngineCheck, EngineChoice, EngineInfo, GpuInfo, OptionFit, ParamSpec, Recommendation } from '../types'
import { cls } from '../utils'
import { LangLabel } from './Flags'
import { Select } from './Select'
import { Badge, Button, Switch, inputCls } from './ui'

const gb = (v?: number | null) => (v == null ? '?' : `${Number(v.toFixed(1))} GB`)
const textareaCls = inputCls.replace('h-9 ', '')

/** Asks the studio whether the selected engine + params fit the detected GPU (debounced). */
function useEngineCheck(engineId: string | null, params: Record<string, unknown>, source?: string, target?: string) {
  const gpu = useStudio((s) => s.gpu)
  const [check, setCheck] = useState<EngineCheck | null>(null)
  const key = JSON.stringify([engineId, params, source, target, gpu])
  useEffect(() => {
    if (!engineId) {
      setCheck(null)
      return
    }
    let alive = true
    const timer = setTimeout(() => {
      api
        .checkEngine(engineId, params, source, target)
        .then((c) => alive && setCheck(c))
        .catch(() => alive && setCheck(null)) // the check is advisory; the server still guards runs
    }, 250)
    return () => {
      alive = false
      clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  return check?.engine === engineId ? check : null
}

export function EnginePicker({
  kind,
  choice,
  onChange,
  source,
  target,
  disabled,
}: {
  kind: EngineInfo['kind']
  choice: EngineChoice
  onChange: (c: EngineChoice) => void
  source?: string
  target?: string
  disabled?: boolean
}) {
  const all = useStudio((s) => s.engines)
  const loading = useStudio((s) => s.enginesLoading)
  const languages = useStudio((s) => s.languages)
  const gpu = useStudio((s) => s.gpu)
  const [showParams, setShowParams] = useState(false)
  const check = useEngineCheck(choice.engine, choice.params, source, target)

  const recs = useMemo(() => recommendationsFor(languages, kind, source, target), [languages, kind, source, target])
  const rank = useMemo(() => new Map(recs.map((r, i) => [r.engine, { index: i, rec: r }])), [recs])

  const engines = useMemo(() => {
    const ok = (e: EngineInfo) =>
      (kind === 'tts' || !source || e.source_languages.length === 0 || e.source_languages.includes(source)) &&
      (kind === 'asr' || !target || e.targets.length === 0 || e.targets.includes(target))
    const score = (e: EngineInfo) => rank.get(e.id)?.index ?? 99
    return all
      .filter((e) => e.kind === kind)
      .map((e) => ({ e, compatible: ok(e), fits: !gpu || e.fits_any !== false }))
      .sort(
        (a, b) =>
          Number(b.compatible) - Number(a.compatible) ||
          Number(b.fits) - Number(a.fits) ||
          score(a.e) - score(b.e) ||
          Number(b.e.available) - Number(a.e.available),
      )
  }, [all, kind, source, target, rank, gpu])

  const selected = all.find((e) => e.id === choice.engine)
  const fitting = (id: string) => !gpu || all.find((e) => e.id === id)?.fits_any !== false
  const topAvailable: Recommendation | undefined =
    recs.find((r) => all.find((e) => e.id === r.engine)?.available && fitting(r.engine)) ?? recs.find((r) => fitting(r.engine)) ?? recs[0]
  const topEngine = topAvailable ? all.find((e) => e.id === topAvailable.engine) : undefined
  const langCode = kind === 'asr' ? source : target
  const setParam = (key: string, value: unknown) => onChange({ engine: choice.engine, params: { ...choice.params, [key]: value } })

  if (!all.length) {
    return <div className="shimmer h-24 rounded-2xl" title={loading ? 'Checking engines…' : 'No engines'} />
  }

  return (
    <div className="flex flex-col gap-3">
      {topAvailable && topEngine && topAvailable.engine !== choice.engine && (
        <div className="fade-in flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line-strong bg-white/[.03] px-3 py-2.5">
          <div className="flex min-w-0 items-start gap-2 text-xs text-neutral-300">
            <Sparkles className="mt-0.5 size-3.5 shrink-0" />
            <span className="min-w-0">
              Recommended {langCode && <>for <LangLabel code={kind === 'translation' ? `${target}` : langCode} size={10} /></>}:{' '}
              <b className="text-white">{topEngine.name}</b>
              <span className="block text-neutral-500">{topAvailable.reason}</span>
            </span>
          </div>
          <Button size="sm" variant="primary" disabled={disabled} onClick={() => onChange({ engine: topAvailable.engine, params: { ...topAvailable.params } })}>
            Use recommended
          </Button>
        </div>
      )}

      <div className="stagger grid grid-cols-1 gap-2 sm:grid-cols-2">
        {engines.map(({ e, compatible, fits }, i) => {
          const active = e.id === choice.engine
          const r = rank.get(e.id)
          const tooBig = !fits
          const why = !compatible
            ? 'Not compatible with the selected languages'
            : tooBig
              ? gpu?.cuda
                ? `Needs at least ${gb(e.vram_min_gb)} of VRAM — cannot run on ${gpu.name} (${gb(gpu.vram_gb)})`
                : 'Needs an NVIDIA GPU, and none was detected'
              : r
                ? `Recommended: ${r.rec.reason}`
                : e.description
          return (
            <button
              key={e.id}
              style={{ ['--i' as string]: Math.min(i, 10) }}
              type="button"
              disabled={disabled || !compatible || (tooBig && !active)}
              onClick={() => onChange({ engine: e.id, params: e.id === choice.engine ? choice.params : { ...(r?.rec.params ?? {}) } })}
              className={cls(
                'lift group flex min-w-0 flex-col gap-1.5 rounded-2xl border p-3 text-left',
                active ? 'border-white bg-white/[.06]' : 'border-line bg-black/30 hover:border-neutral-600',
                (!compatible || tooBig) && 'opacity-35',
              )}
              title={why}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <span className={cls('size-2 shrink-0 rounded-full transition-all duration-300', active ? 'pulse-ring bg-white' : 'bg-neutral-700 group-hover:bg-neutral-500')} />
                  <span className="truncate text-sm font-semibold">{e.name}</span>
                  {e.gated && <Lock className="size-3 shrink-0 text-neutral-500" aria-label="gated model" />}
                </div>
                {tooBig ? (
                  <span className="flex shrink-0 items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-neutral-300">
                    <AlertTriangle className="size-3" /> {gpu?.cuda ? `needs ${gb(e.vram_min_gb)}` : 'needs GPU'}
                  </span>
                ) : e.available ? (
                  <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wider text-neutral-300">ready</span>
                ) : (
                  <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wider text-neutral-600" title={`missing: ${e.missing.join(', ')}\n${e.install}`}>
                    not installed
                  </span>
                )}
              </div>
              {tooBig && compatible ? (
                <span className="text-[11px] text-neutral-400">{why}</span>
              ) : (
                r &&
                compatible && (
                  <span className="flex min-w-0 items-center gap-1 text-[11px] text-neutral-300">
                    <Star className={cls('size-3 shrink-0', r.index === 0 && 'fill-current')} />
                    <span className="shrink-0 whitespace-nowrap">{r.index === 0 ? 'Top pick' : `Recommended #${r.index + 1}`}</span>
                    <span className="truncate text-neutral-500">· {r.rec.reason}</span>
                  </span>
                )
              )}
              <p className="line-clamp-2 text-xs leading-relaxed text-neutral-500">{e.description}</p>
              <div className="flex flex-wrap gap-1">
                <Badge tone="muted">{e.family}</Badge>
                {e.vram_default_gb != null && <Badge tone="muted">≈{gb(e.vram_default_gb)} VRAM</Badge>}
                {e.badges.slice(0, 3).map((b) => (
                  <Badge key={b} tone="muted">
                    {b}
                  </Badge>
                ))}
              </div>
            </button>
          )
        })}
      </div>

      {check && !check.fits && check.message && (
        <div role="alert" className="fade-in flex flex-wrap items-start justify-between gap-3 rounded-2xl border border-white/50 bg-white/[.05] px-3 py-2.5 text-xs">
          <div className="flex min-w-0 items-start gap-2">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <span className="min-w-0">
              <b className="text-white">{check.message}</b>
              <span className="block text-neutral-400">{check.suggestion ?? 'Pick a smaller model or configuration.'} Runs with these settings are blocked.</span>
            </span>
          </div>
          {check.fix && (
            <Button size="sm" variant="primary" icon={<Wand2 className="size-3.5" />} disabled={disabled} onClick={() => setParam(check.fix!.key, check.fix!.value)}>
              Apply fix
            </Button>
          )}
        </div>
      )}

      {selected && (
        <div className="rounded-2xl border border-line">
          <button type="button" onClick={() => setShowParams(!showParams)} className="flex w-full items-center justify-between gap-3 px-3 py-2 text-xs text-neutral-400 hover:text-white">
            <span className="flex min-w-0 items-center gap-2">
              <SlidersHorizontal className="size-3.5 shrink-0" /> {selected.name} parameters
              {check?.required_gb != null && check.gpu?.cuda && (
                <span className="hidden items-center gap-1 text-neutral-500 sm:inline-flex">
                  <Cpu className="size-3" /> ≈{gb(check.required_gb)} of {gb(check.gpu.vram_gb)} on {check.gpu.name}
                </span>
              )}
            </span>
            <span className="flex shrink-0 items-center gap-3">
              {Object.entries(selected.links).map(([k, url]) => (
                <a key={k} href={url} target="_blank" rel="noreferrer" onClick={(ev) => ev.stopPropagation()} className="inline-flex items-center gap-1 hover:text-white">
                  {k} <ExternalLink className="size-3" />
                </a>
              ))}
              <ChevronDown className={cls('size-4 transition', showParams && 'rotate-180')} />
            </span>
          </button>
          {showParams && (
            <div className="grid gap-3 border-t border-line p-3 sm:grid-cols-2">
              {!selected.available && (
                <div className="col-span-full rounded-xl border border-neutral-700 p-2.5 font-mono text-[11px] text-neutral-300">
                  Not installed in the <b>{selected.family}</b> interpreter · missing {selected.missing.join(', ')}
                  <div className="mt-1 text-neutral-500">$ {selected.install}</div>
                </div>
              )}
              {selected.params.map((p) => (
                <ParamInput
                  key={p.key}
                  spec={p}
                  value={choice.params[p.key] ?? p.default}
                  disabled={disabled}
                  fits={check?.options[p.key]}
                  gpu={check?.gpu ?? gpu}
                  preview={check?.preview[p.key]}
                  pair={
                    source && target ? (
                      <>
                        <LangLabel code={source} size={9} /> → <LangLabel code={target} size={9} />
                      </>
                    ) : null
                  }
                  onChange={(v) => setParam(p.key, v)}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ParamInput({
  spec,
  value,
  onChange,
  disabled,
  fits,
  gpu,
  preview,
  pair,
}: {
  spec: ParamSpec
  value: unknown
  onChange: (v: unknown) => void
  disabled?: boolean
  fits?: Record<string, OptionFit>
  gpu?: GpuInfo | null
  preview?: string
  pair?: ReactNode
}) {
  const label = (
    <span className="text-[11px] font-semibold uppercase tracking-wider text-neutral-500" title={spec.help}>
      {spec.label}
    </span>
  )
  if (spec.type === 'textarea') {
    return <PromptInput spec={spec} value={value} onChange={onChange} disabled={disabled} preview={preview} pair={pair} label={label} />
  }
  if (spec.type === 'bool') {
    return (
      <div className="flex flex-col gap-1.5">
        {label}
        <Switch checked={Boolean(value)} onChange={onChange} disabled={disabled} label={<span className="text-xs text-neutral-500">{spec.help}</span>} />
      </div>
    )
  }
  if (spec.type === 'select' && spec.options) {
    return (
      <div className="flex flex-col gap-1.5">
        {label}
        <Select
          value={String(value)}
          disabled={disabled}
          onChange={(v) => onChange(spec.options!.find((o) => String(o.value) === v)?.value ?? v)}
          options={spec.options.map((o) => {
            const fit = fits?.[String(o.value)]
            const tooBig = fit ? !fit.fits : false
            const id = String(o.value) !== o.label ? String(o.value) : undefined
            return {
              value: String(o.value),
              label: o.label,
              disabled: tooBig,
              description: tooBig
                ? gpu?.cuda
                  ? `Needs ≈${gb(fit?.required_gb)} — too big for ${gpu.name}`
                  : 'Needs an NVIDIA GPU'
                : fit?.required_gb != null && gpu?.cuda
                  ? `≈${gb(fit.required_gb)} VRAM${id ? ` · ${id}` : ''}`
                  : id,
            }
          })}
        />
        {spec.help && <span className="text-[11px] leading-snug text-neutral-600">{spec.help}</span>}
      </div>
    )
  }
  if (spec.type === 'number') {
    return (
      <label className="flex flex-col gap-1.5">
        {label}
        <input
          type="number"
          className={cls(inputCls, 'font-mono')}
          disabled={disabled}
          min={spec.min ?? undefined}
          max={spec.max ?? undefined}
          step={spec.step ?? undefined}
          value={Number(value)}
          onChange={(e) => onChange(e.target.value === '' ? spec.default : Number(e.target.value))}
        />
        {spec.help && <span className="text-[11px] leading-snug text-neutral-600">{spec.help}</span>}
      </label>
    )
  }
  return (
    <label className="flex flex-col gap-1.5">
      {label}
      <input className={cls(inputCls, 'font-mono text-xs')} disabled={disabled} value={String(value ?? '')} placeholder={spec.help} onChange={(e) => onChange(e.target.value)} />
    </label>
  )
}

/** Multi-line template editor: placeholder chips, reset to the default template, live preview. */
function PromptInput({
  spec,
  value,
  onChange,
  disabled,
  preview,
  pair,
  label,
}: {
  spec: ParamSpec
  value: unknown
  onChange: (v: unknown) => void
  disabled?: boolean
  preview?: string
  pair?: ReactNode
  label: ReactNode
}) {
  const ref = useRef<HTMLTextAreaElement>(null)
  const [local, setLocal] = useState(String(value ?? ''))
  const [showPreview, setShowPreview] = useState(false)
  const placeholders = spec.help.match(/\{\w+\}/g) ?? []
  const template = String(spec.default ?? '')

  // follow outside changes, but never while typing (a late save echo would eat keystrokes)
  useEffect(() => {
    if (document.activeElement !== ref.current) setLocal(String(value ?? ''))
  }, [value])

  const commit = (text: string) => {
    setLocal(text)
    onChange(text)
  }
  const insert = (token: string) => {
    const el = ref.current
    if (!el) return commit(local + token)
    const start = el.selectionStart ?? local.length
    const end = el.selectionEnd ?? local.length
    commit(local.slice(0, start) + token + local.slice(end))
    requestAnimationFrame(() => {
      el.focus()
      el.setSelectionRange(start + token.length, start + token.length)
    })
  }

  return (
    <div className="flex flex-col gap-1.5 sm:col-span-2">
      <div className="flex items-center justify-between gap-2">
        {label}
        {local !== template && (
          <Button size="sm" variant="ghost" icon={<RotateCcw className="size-3" />} disabled={disabled} onClick={() => commit(template)}>
            Reset to template
          </Button>
        )}
      </div>
      <textarea
        ref={ref}
        dir="auto"
        rows={10}
        spellCheck={false}
        disabled={disabled}
        value={local}
        onChange={(e) => commit(e.target.value)}
        className={cls(textareaCls, 'min-h-40 resize-y py-2 font-mono text-xs leading-relaxed')}
      />
      <div className="flex flex-wrap items-center gap-1.5">
        {placeholders.length > 0 && <span className="text-[11px] text-neutral-500">Insert</span>}
        {placeholders.map((p) => (
          <button
            key={p}
            type="button"
            disabled={disabled}
            onClick={() => insert(p)}
            className="rounded-full border border-line-strong px-2 py-0.5 font-mono text-[10px] text-neutral-300 transition hover:border-white hover:text-white active:scale-95"
          >
            {p}
          </button>
        ))}
        {preview && (
          <button type="button" onClick={() => setShowPreview(!showPreview)} className="ml-auto inline-flex items-center gap-1.5 text-[11px] text-neutral-400 hover:text-white">
            {showPreview ? 'Hide preview' : 'Preview'} {pair && <span className="inline-flex items-center gap-1">for {pair}</span>}
            <ChevronDown className={cls('size-3 transition', showPreview && 'rotate-180')} />
          </button>
        )}
      </div>
      {showPreview && preview && (
        <pre dir="auto" className="fade-in max-h-72 overflow-auto whitespace-pre-wrap rounded-xl border border-line bg-black/40 p-3 font-mono text-[11px] leading-relaxed text-neutral-300">
          {preview}
        </pre>
      )}
    </div>
  )
}
