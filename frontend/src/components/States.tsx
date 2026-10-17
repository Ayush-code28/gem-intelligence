import type { ReactNode } from 'react'

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="flex items-center gap-3 px-4 py-10 text-sm text-slate-600">
      <span className="size-4 animate-spin rounded-full border-2 border-slate-300 border-t-navy-700" aria-hidden />
      {label}
    </div>
  )
}

export function SkeletonRows({ rows = 5 }: { rows?: number }) {
  return (
    <div role="status" aria-label="Loading" className="space-y-3 p-4">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="h-12 animate-pulse rounded bg-slate-100" />
      ))}
    </div>
  )
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="px-4 py-12 text-center">
      <p className="font-semibold text-ink">{title}</p>
      {children && <div className="mx-auto mt-2 max-w-md text-sm text-slate-600">{children}</div>}
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <div role="alert" className="m-4 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-900">
      <p className="font-semibold">Could not load data</p>
      <p className="mt-1 break-words text-red-800">{error.message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="btn-secondary mt-3">
          Try again
        </button>
      )}
    </div>
  )
}

export function NotConfiguredNotice() {
  return (
    <div role="note" className="rounded-lg border-2 border-dashed border-saffron-500 bg-saffron-100 p-5 text-sm">
      <p className="font-semibold text-ink">Demonstration state — no database connected</p>
      <p className="mt-1 text-slate-700">
        This deployment has no Supabase connection configured, so <strong>no GeM data is shown</strong> and nothing
        on this page represents real listings. Set <code className="font-mono">VITE_SUPABASE_URL</code> and{' '}
        <code className="font-mono">VITE_SUPABASE_ANON_KEY</code> to connect it.
      </p>
    </div>
  )
}

/** Renders a value or an explicit "Not available" marker — never a guessed value. */
export function Field({ value, children }: { value: unknown; children?: ReactNode }) {
  if (value === null || value === undefined || value === '') {
    return <span className="italic text-slate-400">Not available</span>
  }
  return <>{children ?? String(value)}</>
}
