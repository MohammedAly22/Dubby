const MARKS: [string, string][] = [
  ['َ', 'fatha'],
  ['ُ', 'damma'],
  ['ِ', 'kasra'],
  ['ْ', 'sukun'],
  ['ّ', 'shadda'],
  ['ً', 'tanween fath'],
  ['ٌ', 'tanween damm'],
  ['ٍ', 'tanween kasr'],
]

/** Inserts tashkeel into the focused textarea without stealing focus. */
export function DiacriticsBar() {
  const insert = (mark: string) => {
    const el = document.activeElement
    if (!(el instanceof HTMLTextAreaElement)) return
    const start = el.selectionStart
    const end = el.selectionEnd
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set
    setter?.call(el, el.value.slice(0, start) + mark + el.value.slice(end))
    el.dispatchEvent(new Event('input', { bubbles: true }))
    el.selectionStart = el.selectionEnd = start + mark.length
  }
  return (
    <div className="flex flex-wrap items-center gap-1 rounded-2xl border border-line px-2 py-1.5">
      <span className="px-1 text-[11px] text-neutral-500">Tashkeel</span>
      {MARKS.map(([m, name]) => (
        <button
          key={name}
          title={`${name} — click while editing an Arabic line`}
          onMouseDown={(e) => {
            e.preventDefault()
            insert(m)
          }}
          className="arabic flex h-7 w-8 items-center justify-center rounded-lg border border-line text-lg text-neutral-300 transition hover:border-white hover:text-white"
        >
          {'ـ' + m}
        </button>
      ))}
      <span className="px-1 text-[11px] text-neutral-600">diacritics help OmniVoice pronounce names & ambiguous words</span>
    </div>
  )
}
