/**
 * Caption look shared by the player overlay and the exported video.
 * CSS px for a 760 px wide video, scaled to the displayed width.
 * Keep in sync with STYLE in dubby/pipeline/captions.py (the exporter draws the same boxes).
 */
export const CAPTION_STYLE = {
  refWidth: 760,
  bottom: 56,
  gap: 4,
  side: 24,
  maxWidth: 0.92,
  radius: 8,
  original: {
    size: 14,
    lineHeight: 1.625,
    padX: 12,
    padY: 6,
    background: 'rgba(0, 0, 0, 0.75)',
    plain: { color: '#ffffff', weight: 400 },
    spoken: { color: '#e5e5e5', weight: 400 },
    current: { color: '#c8ec6f', weight: 600 },
    upcoming: { color: '#8a8a8a', weight: 400 },
  },
  dub: {
    size: 15,
    lineHeight: 1.5,
    padX: 12,
    padY: 4,
    ink: '#0f1a05',
    plain: 600,
    spoken: 500,
    current: 800,
    upcoming: 500,
    upcomingOpacity: 0.5,
    shadow: { y: 6, blur: 20, spread: -6, color: 'rgba(155, 210, 60, 0.7)' },
  },
  arabicLineHeight: 1.9,
  dubLinger: 0.15,
  /** players narrower than this keep a readable size (the export always scales exactly) */
  minScale: 0.62,
  /** px kept free for the browser's own video controls in the preview */
  controlsClearance: 54,
} as const

const UNSPACED = new Set(['zh', 'ja'])
export const isSpaced = (language: string) => !UNSPACED.has(language)

/** The font stack the exporter mirrors for each caption language. */
export function captionFont(language: string, rtl: boolean): string {
  if (rtl) return '"IBM Plex Sans Arabic", "Inter", sans-serif'
  if (language === 'ja') return '"Inter", "Noto Sans JP", "IBM Plex Sans Arabic", sans-serif'
  if (language === 'zh') return '"Inter", "Noto Sans SC", "IBM Plex Sans Arabic", sans-serif'
  if (language === 'hi') return '"Inter", "Noto Sans Devanagari", "IBM Plex Sans Arabic", sans-serif'
  return '"Inter", "IBM Plex Sans Arabic", "Noto Sans Devanagari", "Noto Sans SC", "Noto Sans JP", sans-serif'
}
