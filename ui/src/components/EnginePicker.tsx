import { useMemo, useState } from 'react'
import { ChevronDown, ExternalLink, Lock, SlidersHorizontal, Sparkles, Star } from 'lucide-react'
import { recommendationsFor, useStudio } from '../store'
import type { EngineChoice, EngineInfo, ParamSpec, Recommendation } from '../types'
import { cls } from '../utils'
import { LangLabel } from './Flags'
import { Select } from './Select'
import { Badge, Button, Switch, inputCls } from './ui'

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
  const [showParams, setShowParams] = useState(false)

  const recs = useMemo(() => recommendationsFor(languages, kind, source, target), [languages, kind, source, target])
  const rank = useMemo(() => new Map(recs.map((r, i) => [r.engine, { index: i, rec: r }])), [recs])

  const engines = useMemo(() => {
    const ok = (e: EngineInfo) =>
      (kind === 'tts' || !source || e.source_languages.length === 0 || e.source_languages.includes(source)) &&
      (kind === 'asr' || !target || e.targets.length === 0 || e.targets.includes(target))
    const score = (e: EngineInfo) => rank.get(e.id)?.index ?? 99
    return all
      .filter((e) => e.kind === kind)
      .map((e) => ({ e, compatible: ok(e) }))
      .sort((a, b) => Number(b.compatible) - Number(a.compatible) || score(a.e) - score(b.e) || Number(b.e.available) - Number(a.e.available))
  }, [all, kind, source, target, rank])

  const selected = all.find((e) => e.id === choice.engine)
  const topAvailable: Recommendation | undefined = recs.find((r) => all.find((e) => e.id === r.engine)?.available) ?? recs[0]
  const topEngine = topAvailable ? all.find((e) => e.id === topAvailable.engine) : undefined
  const langCode = kind === 'asr' ? source : target

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

      <div className="stagger grid gap-2 sm:grid-cols-2">
        {engines.map(({ e, compatible }, i) => {
          const active = e.id === choice.engine
          const r = rank.get(e.id)
          return (
            <button
              key={e.id}
              style={{ ['--i' as string]: Math.min(i, 10) }}
              type="button"
              disabled={disabled || !compatible}
              onClick={() => onChange({ engine: e.id, params: e.id === choice.engine ? choice.params : { ...(r?.rec.params ?? {}) } })}
              className={cls(
                'lift group flex flex-col gap-1.5 rounded-2xl border p-3 text-left',
                active ? 'border-white bg-white/[.06]' : 'border-line bg-black/30 hover:border-neutral-600',
                !compatible && 'opacity-35',
              )}
              title={!compatible ? 'Not compatible with the selected languages' : r ? `Recommended: ${r.rec.reason}` : e.description}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <span className={cls('size-2 shrink-0 rounded-full transition-all duration-300', active ? 'pulse-ring bg-white' : 'bg-neutral-700 group-hover:bg-neutral-500')} />
                  <span className="truncate text-sm font-semibold">{e.name}</span>
                  {e.gated && <Lock className="size-3 shrink-0 text-neutral-500" aria-label="gated model" />}
                </div>
                {e.available ? (
                  <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wider text-neutral-300">ready</span>
                ) : (
                  <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wider text-neutral-600" title={`missing: ${e.missing.join(', ')}\n${e.install}`}>
                    not installed
                  </span>
                )}
              </div>
              {r && compatible && (
                <span className="flex items-center gap-1 text-[11px] text-neutral-300">
                  <Star className={cls('size-3', r.index === 0 && 'fill-current')} />
                  {r.index === 0 ? 'Top pick' : `Recommended #${r.index + 1}`}
                  <span className="truncate text-neutral-500">· {r.rec.reason}</span>
                </span>
              )}
              <p className="line-clamp-2 text-xs leading-relaxed text-neutral-500">{e.description}</p>
              <div className="flex flex-wrap gap-1">
                <Badge tone="muted">{e.family}</Badge>
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

      {selected && (
        <div className="rounded-2xl border border-line">
          <button type="button" onClick={() => setShowParams(!showParams)} className="flex w-full items-center justify-between px-3 py-2 text-xs text-neutral-400 hover:text-white">
            <span className="flex items-center gap-2">
              <SlidersHorizontal className="size-3.5" /> {selected.name} parameters
            </span>
            <span className="flex items-center gap-3">
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
                  onChange={(v) => onChange({ engine: choice.engine, params: { ...choice.params, [p.key]: v } })}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ParamInput({ spec, value, onChange, disabled }: { spec: ParamSpec; value: unknown; onChange: (v: unknown) => void; disabled?: boolean }) {
  const label = (
    <span className="text-[11px] font-semibold uppercase tracking-wider text-neutral-500" title={spec.help}>
      {spec.label}
    </span>
  )
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
          options={spec.options.map((o) => ({ value: String(o.value), label: o.label, description: String(o.value) !== o.label ? String(o.value) : undefined }))}
        />
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
