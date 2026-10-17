import { isSafeSourceUrl } from '../lib/format'

/** Opens the official listing in a new window (GeM does not permit framing). */
export function SourceLink({ url, label = 'View on GeM' }: { url: string | null; label?: string }) {
  if (!isSafeSourceUrl(url)) return <span className="italic text-slate-400">Source link not available</span>
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer external"
      className="inline-flex items-center gap-1 font-medium text-navy-700 underline decoration-navy-100 underline-offset-4 hover:decoration-navy-700"
    >
      {label}
      <span aria-hidden>↗</span>
      <span className="sr-only">(opens the official GeM site in a new tab)</span>
    </a>
  )
}
