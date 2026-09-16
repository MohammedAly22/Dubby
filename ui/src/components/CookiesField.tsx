import { useRef, useState } from 'react'
import { Cookie, Trash2, Upload } from 'lucide-react'
import { api } from '../api'
import { useStudio } from '../store'
import { Button } from './ui'

/** Upload / remove the Netscape cookies.txt that yt-dlp uses for YouTube. */
export function CookiesField({ configured, onChange, compact }: { configured: boolean; onChange?: (settings: Record<string, any>) => void; compact?: boolean }) {
  const toast = useStudio((s) => s.toast)
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)

  const upload = async (file: File) => {
    setBusy(true)
    try {
      const settings = await api.uploadCookies(file)
      toast('YouTube cookies saved', 'success')
      onChange?.(settings)
    } catch (e: any) {
      toast(e.message, 'error')
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <input ref={input} type="file" accept=".txt,text/plain" hidden onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex h-9 items-center gap-2 rounded-xl border border-line-strong px-3 text-sm">
          <Cookie className="size-4" />
          {configured ? 'cookies.txt configured' : 'No cookies'}
        </span>
        <Button icon={<Upload className="size-4" />} loading={busy} onClick={() => input.current?.click()}>
          {configured ? 'Replace' : 'Upload cookies.txt'}
        </Button>
        {configured && (
          <Button
            icon={<Trash2 className="size-4" />}
            onClick={() =>
              api
                .deleteCookies()
                .then((s) => {
                  toast('YouTube cookies removed')
                  onChange?.(s)
                })
                .catch((e) => toast(e.message, 'error'))
            }
          >
            Remove
          </Button>
        )}
      </div>
      {!compact && (
        <p className="text-xs leading-relaxed text-neutral-500">
          Not required — downloads work without sign-in. Only for members-only/age-restricted videos: export <b>youtube.com</b> cookies (Netscape
          cookies.txt) from a private window. Stored only on the studio machine.
        </p>
      )}
    </div>
  )
}
