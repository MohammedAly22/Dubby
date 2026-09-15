import egyptFlag from '../../../assets/egypt.jpg'
import ksaFlag from '../../../assets/KSA.jpg'
import usaFlag from '../../../assets/USA.jpg'
import { cls } from '../utils'
import type { SelectOption } from './Select'

export type FlagCode = 'eg' | 'sa' | 'us'

const FLAGS: Record<FlagCode, { src: string; name: string; position: string }> = {
  eg: { src: egyptFlag, name: 'Egypt', position: 'center' },
  sa: { src: ksaFlag, name: 'Saudi Arabia', position: 'center' },
  // The US flag is wider than 3:2 — anchor left so the canton stays visible.
  us: { src: usaFlag, name: 'United States', position: 'left center' },
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

export const LANGS = {
  en: { flag: 'us', name: 'English', native: 'English', short: 'EN' },
  ar: { flag: 'eg', name: 'Arabic', native: 'العربية', short: 'AR' },
  arz: { flag: 'eg', name: 'Egyptian Arabic', native: 'مصري', short: 'EGY' },
  arb: { flag: 'sa', name: 'Modern Standard Arabic', native: 'فصحى', short: 'MSA' },
} as const satisfies Record<string, { flag: FlagCode; name: string; native: string; short: string }>

export type LangCode = keyof typeof LANGS

export function LangLabel({ code, variant = 'full', size = 12 }: { code: LangCode; variant?: 'full' | 'short' | 'name'; size?: number }) {
  const l = LANGS[code]
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
          {code !== 'en' && (
            <span className="font-arabic opacity-60" style={{ lineHeight: 1 }}>
              · {l.native}
            </span>
          )}
        </>
      )}
    </span>
  )
}

export const SOURCE_OPTIONS: SelectOption<'en' | 'ar'>[] = [
  { value: 'en', label: 'English', icon: <Flag code="us" />, description: 'Transcribe English speech' },
  { value: 'ar', label: 'Arabic', icon: <Flag code="eg" />, description: 'Egyptian or MSA speech' },
]

export const TARGET_OPTIONS: SelectOption<'arz' | 'arb'>[] = [
  {
    value: 'arz',
    label: (
      <span>
        Egyptian Arabic <span className="font-arabic opacity-60">· مصري</span>
      </span>
    ),
    icon: <Flag code="eg" />,
    description: 'Everyday spoken Egyptian dialect',
  },
  {
    value: 'arb',
    label: (
      <span>
        MSA <span className="font-arabic opacity-60">· فصحى</span>
      </span>
    ),
    icon: <Flag code="sa" />,
    description: 'Modern Standard Arabic',
  },
]
