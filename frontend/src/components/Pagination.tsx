export function Pagination({
  page,
  pageSize,
  total,
  onPage,
}: {
  page: number
  pageSize: number
  total: number
  onPage: (page: number) => void
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  if (total === 0) return null
  const first = (page - 1) * pageSize + 1
  const last = Math.min(total, page * pageSize)
  return (
    <nav aria-label="Pagination" className="flex flex-wrap items-center justify-between gap-3 border-t border-rule px-4 py-3 text-sm">
      <p className="text-slate-600">
        Showing <strong>{first.toLocaleString('en-IN')}</strong>–<strong>{last.toLocaleString('en-IN')}</strong> of{' '}
        <strong>{total.toLocaleString('en-IN')}</strong>
      </p>
      <div className="flex items-center gap-2">
        <button type="button" className="btn-secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          Previous
        </button>
        <span className="tabular-nums text-slate-600" aria-current="page">
          Page {page} of {pages.toLocaleString('en-IN')}
        </span>
        <button type="button" className="btn-secondary" disabled={page >= pages} onClick={() => onPage(page + 1)}>
          Next
        </button>
      </div>
    </nav>
  )
}
