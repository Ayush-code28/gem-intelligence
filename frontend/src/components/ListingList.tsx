import { Link } from 'react-router'
import { formatDateTime } from '../lib/format'
import type { Listing } from '../lib/types'
import { DeadlineBadge, DeadlineText } from './DeadlineBadge'
import { OriginBadge } from './OriginBadge'
import { Field } from './States'

/** Table on wide screens, stacked cards on narrow ones. `compact` drops secondary columns. */
export function ListingList({ listings, compact = false }: { listings: Listing[]; compact?: boolean }) {
  return (
    <>
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-rule bg-navy-50 text-xs uppercase tracking-wide text-slate-600">
            <tr>
              <th scope="col" className="px-4 py-3 font-semibold">Listing</th>
              <th scope="col" className="px-4 py-3 font-semibold">Organisation</th>
              {!compact && <th scope="col" className="px-4 py-3 font-semibold">Category</th>}
              <th scope="col" className="px-4 py-3 font-semibold">Deadline</th>
              {!compact && <th scope="col" className="px-4 py-3 font-semibold">First seen</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-rule">
            {listings.map((l) => (
              <tr key={l.id} className="align-top hover:bg-navy-50/60">
                <td className="max-w-md px-4 py-3">
                  <Link to={`/listings/${l.id}`} className="font-medium text-navy-800 hover:underline">
                    {l.title}
                  </Link>
                  <div className="mt-1 flex flex-wrap items-center gap-2 font-mono text-xs text-slate-500">
                    <OriginBadge origin={l.data_origin} />
                    <Field value={l.bid_number} />
                  </div>
                </td>
                <td className="max-w-xs px-4 py-3 text-slate-700">
                  <Field value={l.organisation} />
                </td>
                {!compact && (
                  <td className="px-4 py-3 text-slate-700">
                    <Field value={l.category} />
                  </td>
                )}
                <td className="px-4 py-3">
                  <div className="whitespace-nowrap text-slate-700">
                    <DeadlineText deadline={l.deadline} />
                  </div>
                  <DeadlineBadge deadline={l.deadline} />
                </td>
                {!compact && <td className="whitespace-nowrap px-4 py-3 text-slate-600">{formatDateTime(l.first_seen_at)}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="divide-y divide-rule md:hidden">
        {listings.map((l) => (
          <li key={l.id} className="space-y-1.5 px-4 py-4">
            <Link to={`/listings/${l.id}`} className="block font-medium text-navy-800 hover:underline">
              {l.title}
            </Link>
            <p className="text-sm text-slate-700">
              <Field value={l.organisation} />
            </p>
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
              <OriginBadge origin={l.data_origin} />
              <DeadlineBadge deadline={l.deadline} />
              <span>
                Deadline: <DeadlineText deadline={l.deadline} />
              </span>
            </div>
          </li>
        ))}
      </ul>
    </>
  )
}
