import type { DataOrigin } from '../lib/types'

const META: Record<DataOrigin, { label: string; className: string; title: string }> = {
  live: {
    label: 'Live-collected',
    className: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
    title: 'Collected automatically from the official source by this site’s collector',
  },
  imported: {
    label: 'Imported',
    className: 'bg-sky-50 text-sky-900 ring-sky-200',
    title: 'Loaded from a file by the site operator; not collected or verified by this site',
  },
  synthetic: {
    label: 'Synthetic demo',
    className: 'bg-fuchsia-50 text-fuchsia-900 ring-fuchsia-300',
    title: 'Invented demonstration data — not a real GeM listing',
  },
}

export const ORIGIN_OPTIONS: { value: DataOrigin; label: string }[] = [
  { value: 'live', label: META.live.label },
  { value: 'imported', label: META.imported.label },
  { value: 'synthetic', label: META.synthetic.label },
]

export function OriginBadge({ origin }: { origin: DataOrigin }) {
  const meta = META[origin] ?? META.imported
  return (
    <span title={meta.title} className={`inline-flex rounded px-1.5 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${meta.className}`}>
      {meta.label}
    </span>
  )
}

export function SyntheticNotice({ count }: { count: number }) {
  if (count <= 0) return null
  return (
    <div role="note" className="mb-6 rounded-lg border-2 border-fuchsia-300 bg-fuchsia-50 px-4 py-3 text-sm text-fuchsia-950">
      <strong>Contains synthetic demonstration data.</strong> {count.toLocaleString('en-IN')} record
      {count === 1 ? ' is' : 's are'} invented for testing (marked “Synthetic demo” and titled “[SYNTHETIC]”). They are not
      real GeM listings.
    </div>
  )
}
