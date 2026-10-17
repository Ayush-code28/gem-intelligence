import { Link } from 'react-router'
import { EmptyState } from '../components/States'

export function NotFoundPage() {
  return (
    <EmptyState title="Page not found">
      <Link to="/" className="text-navy-700 underline">
        Go to the dashboard
      </Link>
    </EmptyState>
  )
}
