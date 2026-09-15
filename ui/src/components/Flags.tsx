import { Globe2 } from 'lucide-react'
import egyptFlag from '../../../assets/egypt.jpg'
import ksaFlag from '../../../assets/KSA.jpg'
import usaFlag from '../../../assets/USA.jpg'
import spainFlag from '../../../assets/Spain.png'
import franceFlag from '../../../assets/France.png'
import italyFlag from '../../../assets/Italy.png'
import indiaFlag from '../../../assets/India.png'
import chinaFlag from '../../../assets/China.jpg'
import japanFlag from '../../../assets/Japan.png'
import { cls } from '../utils'
import type { SelectOption } from './Select'

export type FlagCode = 'eg' | 'sa' | 'us' | 'es' | 'fr' | 'it' | 'in' | 'cn' | 'jp'

const FLAGS: Record<FlagCode, { src: string; name: string; position: string }> = {
  eg: { src: egyptFlag, name: 'Egypt', position: 'center' },
  sa: { src: ksaFlag, name: 'Saudi Arabia', position: 'center' },
  // The US flag is wider than 3:2 — anchor left so the canton stays visible.
  us: { src: usaFlag, name: 'United States', position: 'left center' },
  es: { src: spainFlag, name: 'Spain', position: 'center' },
  fr: { src: franceFlag, name: 'France', position: 'center' },
  it: { src: italyFlag, name: 'Italy', position: 'center' },
  in: { src: indiaFlag, name: 'India', position: 'center' },
  cn: { src: chinaFlag, name: 'China', position: 'left center' },
  jp: { src: japanFlag, name: 'Japan', position: 'center' },
}

/** Real flag images from /assets, shown in a consistent 3:2 frame. */
export function Flag({ code, size = 14, className }: { code: FlagCode; size?: number; className?: string }) {
  const flag = FLAGS[code]
  return (
    <img
      src={flag.src}
      alt={flag.name}
      title={flag.name}
      width={Math.round(size * 1.5)}
      height={size}
      draggable={false}
      loading="lazy"
      decoding="async"
      style={{ width: size * 1.5, height: size, objectPosition: flag.position }}
      className={cls('inline-block shrink-0 select-none rounded-[3px] object-cover shadow-[0_0_0_1px_rgba(255,255,255,.2)]', className)}
    />
  )
}

export interface LangMeta {
  flag: FlagCode
  name: string
  native: string
  short: string
  rtl?: boolean
  arabic?: boolean
  hint: string
}

export const LANGS: Record<string, LangMeta> = {
  en: { flag: 'us', name: 'English', native: 'English', short: 'EN', hint: 'English' },
  ar: { flag: 'eg', name: 'Arabic', native: 'العربية', short: 'AR', rtl: true, arabic: true, hint: 'Egyptian or MSA speech' },
  arz: { flag: 'eg', name: 'Egyptian Arabic', native: 'مصري', short: 'EGY', rtl: true, arabic: true, hint: 'Everyday spoken Egyptian dialect' },
  arb: { flag: 'sa', name: 'Modern Standard Arabic', native: 'فصحى', short: 'MSA', rtl: true, arabic: true, hint: 'Formal fusha for documentaries & news' },
  es: { flag: 'es', name: 'Spanish', native: 'Español', short: 'ES', hint: 'Spanish' },
  fr: { flag: 'fr', name: 'French', native: 'Français', short: 'FR', hint: 'French' },
  it: { flag: 'it', name: 'Italian', native: 'Italiano', short: 'IT', hint: 'Italian' },
  hi: { flag: 'in', name: 'Hindi', native: 'हिन्दी', short: 'HI', hint: 'Hindi (Devanagari)' },
  zh: { flag: 'cn', name: 'Chinese', native: '中文', short: 'ZH', hint: 'Mandarin, Simplified Chinese' },
  ja: { flag: 'jp', name: 'Japanese', native: '日本語', short: 'JA', hint: 'Japanese' },
}

export const SOURCE_CODES = ['en', 'ar', 'es', 'fr', 'it', 'hi', 'zh', 'ja'] as const
export const TARGET_CODES = ['arz', 'arb', 'en', 'es', 'fr', 'it', 'hi', 'zh', 'ja'] as const
export type LangCode = keyof typeof LANGS

export const lang = (code: string): LangMeta => LANGS[code] ?? { flag: 'us', name: code, native: code, short: code.toUpperCase(), hint: code }
export const isRtl = (code: string) => !!LANGS[code]?.rtl
export const isArabic = (code: string) => !!LANGS[code]?.arabic

export function LangLabel({ code, variant = 'full', size = 12 }: { code: string; variant?: 'full' | 'short' | 'name'; size?: number }) {
  const l = lang(code)
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <Flag code={l.flag} size={size} />
      {variant === 'short' ? (
        l.short
      ) : variant === 'name' ? (
        l.name
      ) : (
        <>
          {code === 'arb' ? 'MSA' : l.name}
          {l.native !== l.name && (
            <span className={cls('opacity-60', l.arabic && 'font-arabic')} style={{ lineHeight: 1 }}>
              · {l.native}
            </span>
          )}
        </>
      )}
    </span>
  )
}

const label = (code: string) => {
  const l = lang(code)
  return (
    <span>
      {code === 'arb' ? 'MSA' : l.name}
      {l.native !== l.name && <span className={cls('opacity-60', l.arabic && 'font-arabic')}> · {l.native}</span>}
    </span>
  )
}

export const AUTO_OPTION: SelectOption<string> = {
  value: 'auto',
  label: 'Auto-detect',
  icon: <Globe2 className="size-4 text-neutral-400" />,
  description: 'Detect the spoken language after download',
}

export const SOURCE_OPTIONS: SelectOption<string>[] = SOURCE_CODES.map((code) => ({
  value: code,
  label: label(code),
  icon: <Flag code={lang(code).flag} />,
  description: lang(code).hint,
}))

export const SOURCE_OPTIONS_WITH_AUTO: SelectOption<string>[] = [AUTO_OPTION, ...SOURCE_OPTIONS]

export const TARGET_OPTIONS: SelectOption<string>[] = TARGET_CODES.map((code) => ({
  value: code,
  label: label(code),
  icon: <Flag code={lang(code).flag} />,
  description: lang(code).hint,
}))
