import type { CSSProperties } from 'react'
import { CAPTION_STYLE as S, captionFont, isSpaced } from '../captionStyle'
import type { Segment, Word } from '../types'
import { isRtl } from './Flags'

export interface ContentRect {
  left: number
  top: number
  width: number
  height: number
}

type State = 'plain' | 'spoken' | 'current' | 'upcoming'

/**
 * The caption boxes over the video picture, sized from its displayed width.
 * The exported video draws the very same boxes (dubby/pipeline/captions.py).
 */
export function CaptionOverlay({
  rect,
  time,
  original,
  dub,
  dubWords,
  source,
  target,
}: {
  rect: ContentRect
  time: number
  original: Segment | null
  dub: Segment | null
  dubWords: Word[]
  source: string
  target: string
}) {
  if (!rect.width || (!original && !dub?.translation)) return null
  const s = Math.max(S.minScale, rect.width / S.refWidth)
  const px = (v: number) => `${v * s}px`

  const box = (kind: 'original' | 'dub', language: string): CSSProperties => {
    const spec = S[kind]
    const rtl = isRtl(language)
    return {
      maxWidth: '92%',
      borderRadius: px(S.radius),
      padding: `${px(spec.padY)} ${px(spec.padX)}`,
      fontSize: px(spec.size),
      lineHeight: rtl ? S.arabicLineHeight : spec.lineHeight,
      fontFamily: captionFont(language, rtl),
      direction: rtl ? 'rtl' : undefined,
      unicodeBidi: 'plaintext',
      textAlign: 'center',
      fontKerning: 'normal',
    }
  }

  const words = (list: { text: string; state: State }[], language: string, style: (state: State) => CSSProperties) => {
    const joiner = isSpaced(language) ? ' ' : ''
    return list.map((w, i) => (
      <span key={i} style={style(w.state)}>
        {w.text}
        {joiner}
      </span>
    ))
  }

  const originalWords = original
    ? original.words.length
      ? original.words.filter((w) => w.text.trim()).map((w) => ({ text: w.text, state: (time >= w.start && time < w.end ? 'current' : time >= w.end ? 'spoken' : 'upcoming') as State }))
      : tokens(original.text, source).map((text) => ({ text, state: 'plain' as State }))
    : []
  const dubList = dub?.translation
    ? dubWords.length
      ? dubWords
          .map((w, i) => {
            const next = dubWords[i + 1]?.start ?? w.end
            return { text: w.text, state: (time >= w.start && time < Math.max(w.end, next) ? 'current' : time >= w.start ? 'spoken' : 'upcoming') as State }
          })
          .filter((w) => w.text.trim())
      : tokens(dub.translation, target).map((text) => ({ text, state: 'plain' as State }))
    : []

  return (
    <div
      className="pointer-events-none absolute flex flex-col items-center justify-end"
      // small players keep the lines above the browser's video controls (the export uses the exact offset)
      style={{ left: rect.left, top: rect.top, width: rect.width, height: rect.height, paddingLeft: px(S.side), paddingRight: px(S.side), paddingBottom: Math.max(S.bottom * s, S.controlsClearance), gap: px(S.gap) }}
    >
      {originalWords.length > 0 && (
        <div style={{ ...box('original', source), background: S.original.background, color: S.original.plain.color }}>
          {words(originalWords, source, (state) => ({ color: S.original[state].color, fontWeight: S.original[state].weight }))}
        </div>
      )}
      {dubList.length > 0 && (
        <div
          className="bg-accent-gradient"
          style={{
            ...box('dub', target),
            color: S.dub.ink,
            boxShadow: `0 ${px(S.dub.shadow.y)} ${px(S.dub.shadow.blur)} ${px(S.dub.shadow.spread)} ${S.dub.shadow.color}`,
          }}
        >
          {words(dubList, target, (state) => ({ fontWeight: S.dub[state], opacity: state === 'upcoming' ? S.dub.upcomingOpacity : 1 }))}
        </div>
      )}
    </div>
  )
}

function tokens(text: string, language: string): string[] {
  return isSpaced(language) ? text.split(/\s+/).filter(Boolean) : [...text].filter((c) => c.trim())
}
