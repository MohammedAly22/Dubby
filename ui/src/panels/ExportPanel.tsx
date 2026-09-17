import { useState } from 'react'
import { Captions, Clapperboard, Copy, Download, FolderDown, HardDriveDownload, RefreshCw } from 'lucide-react'
import { api, fileUrl } from '../api'
import { Select } from '../components/Select'
import { StageHeader } from '../components/StageHeader'
import { Button, Empty, Field, Progress, Segmented, Slider, Switch, inputCls } from '../components/ui'
import { usePlayer } from '../player'
import { useStudio } from '../store'
import type { CaptionMode, MixConfig, Project } from '../types'
import { fmtBytes, isBusy, timeAgo } from '../utils'

export function ExportPanel({ project }: { project: Project }) {
  const st = project.stages.render
  const busy = isBusy(st)
  const patchSettings = useStudio((s) => s.patchSettings)
  const toast = useStudio((s) => s.toast)
  const cancelStage = useStudio((s) => s.cancelStage)
  const setMode = usePlayer((s) => s.setMode)
  const mix = project.settings.mix
  const [dir, setDir] = useState('')
  const [exporting, setExporting] = useState(false)
  const captionMode: CaptionMode = mix.burn_captions ?? 'none'
  const exportSt = project.stages.export
  const captionSt = project.stages.captions
  const burning = isBusy(exportSt)
  const aligning = isBusy(captionSt)
  const voiced = project.segments.filter((s) => s.tts.status === 'done').length

  const setMix = (patch: Partial<MixConfig>) => patchSettings({ mix: patch })

  const render = async () => {
    try {
      await api.render(project.id, mix as unknown as Record<string, unknown>)
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }

  const exportNow = async () => {
    setExporting(true)
    try {
      const res = await api.export(project.id, dir.trim() || undefined, captionMode)
      if (res.queued) toast(`Burning ${captionMode === 'both' ? 'both captions' : `${captionMode} captions`} into the video — the files are saved when it finishes`)
    } catch (e: any) {
      toast(e.message, 'error')
    } finally {
      setExporting(false)
    }
  }

  if (!voiced) {
    return <Empty icon={<Clapperboard className="size-8" />} title="No dubbed clips yet">Generate voices first, then render the final video here.</Empty>
  }

  const r = project.render
  return (
    <div className="flex flex-col gap-6">
      <StageHeader
        icon="🎬"
        title="Mix, render & export"
        subtitle="Clips are placed on the original timeline, sped up gently when they overflow their slot, mixed with the background and muxed with the video."
        state={st}
        actions={
          busy ? (
            <Button onClick={() => cancelStage('render')}>Cancel</Button>
          ) : (
            <Button variant="primary" icon={<Clapperboard className="size-4" />} onClick={render}>
              {r.video ? 'Render again' : 'Render dubbed video'}
            </Button>
          )
        }
      />

      <div className="flex flex-col gap-4 rounded-2xl border border-line p-4">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-neutral-500">Mix</div>
        <div className="flex flex-wrap items-center gap-3 text-sm text-neutral-400">
          Background
          <Segmented<MixConfig['background']>
            size="sm"
            value={mix.background}
            onChange={(v) => setMix({ background: v })}
            options={[
              { value: 'original', label: 'Original (ducked)' },
              { value: 'separated', label: 'Music only', disabled: !project.source.background, title: project.source.background ? 'Demucs background stem' : 'Run vocal separation in the Voice step' },
              { value: 'none', label: 'Silent' },
            ]}
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          {mix.background === 'original' && (
            <Field label="Original under the dub">
              <Slider value={mix.background_volume} min={0} max={1} step={0.01} onChange={(v) => setMix({ background_volume: v })} format={(v) => `${Math.round(v * 100)}%`} />
            </Field>
          )}
          {mix.background !== 'none' && (
            <Field label={mix.background === 'separated' ? 'Music level' : 'Original between lines'}>
              <Slider value={mix.outside_volume} min={0} max={1} step={0.01} onChange={(v) => setMix({ outside_volume: v })} format={(v) => `${Math.round(v * 100)}%`} />
            </Field>
          )}
          <Field label="Dub level">
            <Slider value={mix.dub_volume} min={0} max={2} step={0.01} onChange={(v) => setMix({ dub_volume: v })} format={(v) => `${Math.round(v * 100)}%`} />
          </Field>
          <Field label="Max speed-up for long clips">
            <Slider value={mix.max_speedup} min={1} max={1.8} step={0.05} onChange={(v) => setMix({ max_speedup: v })} format={(v) => `×${v.toFixed(2)}`} />
          </Field>
          <Field label="When a clip overflows its slot">
            <Select<MixConfig['fit_mode']>
              value={mix.fit_mode}
              onChange={(v) => setMix({ fit_mode: v })}
              options={[
                { value: 'stretch', label: 'Speed up, then trim', description: 'Pitch-preserving atempo up to the max speed-up' },
                { value: 'trim', label: 'Trim with fade-out', description: 'Keeps natural pace, cuts the tail' },
                { value: 'none', label: 'Let it overlap', description: 'Clips may run into the next line' },
              ]}
            />
          </Field>
          <div className="flex items-end pb-1">
            <Switch checked={mix.subtitles} onChange={(v) => setMix({ subtitles: v })} label="Embed dub + source subtitle tracks" />
          </div>
        </div>
      </div>

      {r.video && (
        <div className="fade-in flex flex-col gap-4 rounded-2xl border border-white/40 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="text-sm font-semibold">Render v{r.version}</div>
              <div className="text-xs text-neutral-500">{r.created_at ? timeAgo(r.created_at) : ''}</div>
            </div>
            <Button icon={<Clapperboard className="size-4" />} onClick={() => setMode('render')}>
              Watch in player
            </Button>
          </div>
          <div className="flex flex-wrap gap-2">
            <DownloadLink href={fileUrl(project.id, r.video, r.version, true)} label="Video (.mp4)" />
            {r.mix && <DownloadLink href={fileUrl(project.id, r.mix, r.version, true)} label="Mix (.wav)" />}
            {r.voice && <DownloadLink href={fileUrl(project.id, r.voice, r.version, true)} label="Voice only (.wav)" />}
            {r.subtitles.ar_srt && <DownloadLink href={fileUrl(project.id, r.subtitles.ar_srt, r.version, true)} label={`Dub .srt (${project.settings.target})`} />}
            {r.subtitles.src_srt && <DownloadLink href={fileUrl(project.id, r.subtitles.src_srt, r.version, true)} label={`Source .srt (${project.settings.source_language})`} />}
          </div>
          <CaptionsSection project={project} mode={captionMode} onMode={(v) => setMix({ burn_captions: v })} aligning={aligning} />
          {burning && (
            <div className="fade-in flex flex-col gap-1.5">
              <div className="flex items-center justify-between gap-2 text-xs text-neutral-400">
                <span>{exportSt?.message || 'Exporting…'}</span>
                <button className="underline-offset-4 hover:text-white hover:underline" onClick={() => cancelStage('export')}>
                  Cancel
                </button>
              </div>
              <Progress value={exportSt?.progress ?? 0} active />
            </div>
          )}
          {exportSt?.status === 'error' && !burning && <div className="text-xs text-neutral-400">Export failed: {exportSt.error}</div>}
          <div className="flex flex-col gap-2 border-t border-line pt-4">
            <Field label="Save to disk on the studio machine" hint="Leave empty to use the export directory from Settings.">
              <div className="flex gap-2">
                <input className={inputCls} placeholder="e.g. D:\Videos\Dubbed  or  /content/drive/MyDrive/Dubby" value={dir} onChange={(e) => setDir(e.target.value)} />
                <Button variant="primary" icon={<HardDriveDownload className="size-4" />} loading={exporting || burning} onClick={exportNow}>
                  Export
                </Button>
              </div>
            </Field>
          </div>
        </div>
      )}

      {project.exports.length > 0 && (
        <div className="flex flex-col gap-2">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-neutral-500">Exported files</div>
          {project.exports.map((e, i) => (
            <div key={i} className="flex items-center justify-between gap-3 rounded-xl border border-line px-3 py-2">
              <div className="min-w-0">
                <div className="text-xs text-neutral-400">
                  {e.kind} · {fmtBytes(e.size)} · {timeAgo(e.created_at)}
                </div>
                <div className="truncate font-mono text-xs" title={e.path}>
                  {e.path}
                </div>
              </div>
              <button
                title="Copy path"
                className="rounded-full p-1.5 text-neutral-400 hover:bg-white/10 hover:text-white"
                onClick={() => navigator.clipboard?.writeText(e.path).then(() => toast('Path copied'))}
              >
                <Copy className="size-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const CAPTION_OPTIONS: { value: CaptionMode; label: string; title: string }[] = [
  { value: 'none', label: 'None', title: 'Clean video, no captions drawn on the frames' },
  { value: 'original', label: 'Original', title: 'Source-language captions with per-word highlighting' },
  { value: 'dub', label: 'Dub', title: 'Dub-language captions timed to the dubbed speech' },
  { value: 'both', label: 'Both', title: 'Original line above the dub line' },
]

/** Captions burned into the exported video, styled like the player overlay. */
function CaptionsSection({ project, mode, onMode, aligning }: { project: Project; mode: CaptionMode; onMode: (v: CaptionMode) => void; aligning: boolean }) {
  const toast = useStudio((s) => s.toast)
  const r = project.render
  const st = project.stages.captions
  const info = r.captions ?? {}
  const current = info.version === r.version
  const burned = Object.entries(r.burned ?? {})
  const status = aligning
    ? st?.message || 'Aligning the dubbed speech…'
    : !current
      ? 'Dub caption timing not computed for this render yet'
      : info.method === 'aligned'
        ? `Word-aligned on the rendered dub · ${info.aligned ?? 0}/${info.total ?? 0} clips`
        : `Estimated from clip placement${info.total ? ` · ${info.total} clips` : ''} — word alignment unavailable`

  return (
    <div className="flex flex-col gap-3 border-t border-line pt-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Captions className="size-4" /> Captions in the video
        </div>
        <Segmented<CaptionMode> size="sm" value={mode} onChange={onMode} options={CAPTION_OPTIONS} />
      </div>
      <p className="text-xs text-neutral-500">
        Burned into the frames with the same per-word highlighting as the player. Preview it with <b className="text-neutral-300">Rendered</b> mode and captions on.
      </p>
      <div className="flex flex-col gap-1.5 rounded-xl border border-line-strong bg-white/[.02] px-3 py-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
          <span className={aligning ? 'text-neutral-300' : 'text-neutral-400'}>💬 {status}</span>
          <Button
            size="sm"
            icon={<RefreshCw className="size-3.5" />}
            disabled={aligning}
            onClick={() =>
              api
                .alignCaptions(project.id)
                .then(() => toast('Re-aligning dub captions'))
                .catch((e) => toast(e.message, 'error'))
            }
          >
            Re-align
          </Button>
        </div>
        {aligning && <Progress value={st?.progress ?? 0} active />}
        {st?.status === 'error' && !aligning && <span className="text-xs text-neutral-500">Alignment failed: {st.error} — captions use estimated timing.</span>}
      </div>
      {burned.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {burned.map(([m, rel]) => (
            <DownloadLink key={m} href={fileUrl(project.id, rel, r.version, true)} label={`Video + ${m === 'both' ? 'both' : m} captions`} />
          ))}
        </div>
      )}
    </div>
  )
}

function DownloadLink({ href, label }: { href: string; label: string }) {
  return (
    <a href={href} className="inline-flex h-8 items-center gap-1.5 rounded-full border border-line-strong px-3 text-xs text-neutral-200 transition hover:border-white hover:text-white">
      {label.startsWith('Video') ? <Download className="size-3.5" /> : <FolderDown className="size-3.5" />} {label}
    </a>
  )
}
