/** Subtle monochrome background: slow glows, a panning dot grid and a few floating doodles. */
export function AnimatedBackground() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
      <div className="blob blob-1" />
      <div className="blob blob-2" />
      <div className="blob blob-3" />
      <div className="app-bg-grid absolute inset-0" />

      <Sparkle className="drift absolute top-[14%] left-[6%] size-7 text-white opacity-15" delay="-2s" />
      <Sparkle className="drift absolute top-[62%] right-[5%] size-9 text-white opacity-10" delay="-6s" />
      <Sparkle className="drift absolute bottom-[10%] left-[42%] size-5 text-white opacity-10" delay="-9s" />
      <Squiggle className="drift absolute top-[28%] right-[12%] w-24 text-white opacity-10" delay="-4s" />
      <Squiggle className="drift absolute bottom-[22%] left-[9%] w-20 text-white opacity-10" delay="-11s" />

      {[
        ['12%', '38%', '0s'],
        ['22%', '82%', '-1.4s'],
        ['48%', '18%', '-2.1s'],
        ['71%', '63%', '-3.3s'],
        ['86%', '30%', '-0.7s'],
        ['35%', '93%', '-2.8s'],
      ].map(([top, left, delay], i) => (
        <span key={i} className="twinkle absolute size-1 rounded-full bg-white" style={{ top, left, animationDelay: delay }} />
      ))}
    </div>
  )
}

function Sparkle({ className, delay }: { className?: string; delay?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} style={{ animationDelay: delay }} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round">
      <path d="M12 2.5l2.4 6.1 6.1 2.4-6.1 2.4L12 19.5l-2.4-6.1-6.1-2.4 6.1-2.4z" />
    </svg>
  )
}

function Squiggle({ className, delay }: { className?: string; delay?: string }) {
  return (
    <svg viewBox="0 0 100 24" className={className} style={{ animationDelay: delay }} fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round">
      <path d="M4 14c8-12 16 8 24-4s16 8 24-4 16 8 24-4 14 6 20-2" />
    </svg>
  )
}
