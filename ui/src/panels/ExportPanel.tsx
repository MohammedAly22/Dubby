import { useState } from 'react'
import { Clapperboard, Copy, Download, FolderDown, HardDriveDownload } from 'lucide-react'
import { api, fileUrl } from '../api'
import { Select } from '../components/Select'
import { StageHeader } from '../components/StageHeader'
import { Button, Empty, Field, Segmented, Slider, Switch, inputCls } from '../components/ui'
import { usePlayer } from '../player'
import { useStudio } from '../store'
import type { MixConfig, Project } from '../types'
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
      const items = await api.export(project.id, dir.trim() || undefined)
      toast(`Saved ${items.length} files to disk`, 'success')
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
            <Switch checked={mix.subtitles} onChange={(v) => setMix({ subtitles: v })} label="Embed Arabic + source subtitles" />
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
            {r.subtitles.ar_srt && <DownloadLink href={fileUrl(project.id, r.subtitles.ar_srt, r.version, true)} label="Arabic .srt" />}
            {r.subtitles.src_srt && <DownloadLink href={fileUrl(project.id, r.subtitles.src_srt, r.version, true)} label="Source .srt" />}
          </div>
          <div className="flex flex-col gap-2 border-t border-line pt-4">
            <Field label="Save to disk on the studio machine" hint="Leave empty to use the export directory from Settings.">
              <div className="flex gap-2">
                <input className={inputCls} placeholder="e.g. D:\Videos\Dubbed  or  /content/drive/MyDrive/Dubby" value={dir} onChange={(e) => setDir(e.target.value)} />
                <Button variant="primary" icon={<HardDriveDownload className="size-4" />} loading={exporting} onClick={exportNow}>
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

function DownloadLink({ href, label }: { href: string; label: string }) {
  return (
    <a href={href} className="inline-flex h-8 items-center gap-1.5 rounded-full border border-line-strong px-3 text-xs text-neutral-200 transition hover:border-white hover:text-white">
      {label.includes('Video') ? <Download className="size-3.5" /> : <FolderDown className="size-3.5" />} {label}
    </a>
  )
}
