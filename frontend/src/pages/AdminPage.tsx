import { useState, type FormEvent } from 'react'
import { PageHeader } from '../components/Layout'
import { EmptyState, ErrorState, LoadingState, NotConfiguredNotice } from '../components/States'
import { useApi, useRequiredApi } from '../lib/api'
import { formatDateTime, formatRelative } from '../lib/format'
import type { RunStatus, ScrapeRun } from '../lib/types'
import { useAsync } from '../lib/useAsync'

const STATUS_STYLE: Record<RunStatus, string> = {
  success: 'bg-emerald-100 text-emerald-900',
  partial: 'bg-amber-100 text-amber-900',
  failed: 'bg-red-100 text-red-900',
  running: 'bg-sky-100 text-sky-900',
  skipped: 'bg-slate-200 text-slate-700',
}

function StatusPill({ status }: { status: string }) {
  const style = STATUS_STYLE[status as RunStatus] ?? 'bg-slate-100 text-slate-700'
  return <span className={`inline-flex rounded px-2 py-0.5 text-xs font-semibold ${style}`}>{status}</span>
}

/** Admin access is enforced by the database (RLS on scrape_runs + public.admins), not by this UI. */
export function AdminPage() {
  const api = useApi()
  return (
    <>
      <PageHeader title="Collection monitoring" description="Operator view of collection runs, errors and source health." />
      {api ? <AdminGate /> : <NotConfiguredNotice />}
    </>
  )
}

function AdminGate() {
  const api = useRequiredApi()
  const [version, setVersion] = useState(0)
  const session = useAsync(async () => {
    const user = await api.getCurrentUser()
    return { user, admin: user ? await api.isAdmin() : false }
  }, `session:${version}`)
  const refresh = () => setVersion((v) => v + 1)

  if (session.status === 'loading') return <LoadingState label="Checking access…" />
  if (session.status === 'error') return <ErrorState error={session.error} onRetry={session.reload} />
  if (!session.data.user) return <SignInForm onSignedIn={refresh} />
  if (!session.data.admin) {
    return (
      <div role="alert" className="card p-5">
        <p className="font-semibold">Not authorised</p>
        <p className="mt-1 text-sm text-slate-600">
          You are signed in as {session.data.user.email ?? 'this user'}, but this account is not an operator.
        </p>
        <button type="button" className="btn-secondary mt-3" onClick={() => api.signOut().then(refresh)}>
          Sign out
        </button>
      </div>
    )
  }
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2 text-sm text-slate-600">
        <span>Signed in as {session.data.user.email}</span>
        <button type="button" className="btn-secondary" onClick={() => api.signOut().then(refresh)}>
          Sign out
        </button>
      </div>
      <RunsView />
    </>
  )
}

function SignInForm({ onSignedIn }: { onSignedIn: () => void }) {
  const api = useRequiredApi()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.signIn(email, password)
      onSignedIn()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="card max-w-sm space-y-4 p-5" aria-label="Operator sign-in">
      <p className="text-sm text-slate-600">Operators sign in with their Supabase Auth account.</p>
      <div>
        <label htmlFor="email" className="eyebrow mb-1 block">
          Email
        </label>
        <input id="email" type="email" autoComplete="username" required className="input" value={email} onChange={(e) => setEmail(e.target.value)} />
      </div>
      <div>
        <label htmlFor="password" className="eyebrow mb-1 block">
          Password
        </label>
        <input id="password" type="password" autoComplete="current-password" required className="input" value={password} onChange={(e) => setPassword(e.target.value)} />
      </div>
      {error && (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      )}
      <button type="submit" className="btn-primary w-full" disabled={busy}>
        {busy ? 'Signing in…' : 'Sign in'}
      </button>
    </form>
  )
}

interface SourceHealth {
  name: string
  lastStatus: string
  lastRunAt: string
  lastSuccessAt: string | null
  lastError: string | null
  origin: string
}

export function sourceHealth(runs: ScrapeRun[]): SourceHealth[] {
  const health = new Map<string, SourceHealth>()
  for (const run of runs) {
    for (const [name, result] of Object.entries(run.source_results ?? {})) {
      const entry = health.get(name)
      if (!entry) {
        health.set(name, {
          name,
          lastStatus: result.status,
          lastRunAt: run.started_at,
          lastSuccessAt: result.status === 'success' ? run.started_at : null,
          lastError: result.error ?? null,
          origin: result.origin ?? 'live',
        })
      } else if (!entry.lastSuccessAt && result.status === 'success') {
        entry.lastSuccessAt = run.started_at
      }
    }
  }
  return [...health.values()].sort((a, b) => a.name.localeCompare(b.name))
}

function RunsView() {
  const api = useRequiredApi()
  const runs = useAsync(() => api.listRuns(50), 'runs')
  if (runs.status === 'loading') return <LoadingState label="Loading runs…" />
  if (runs.status === 'error') return <ErrorState error={runs.error} onRetry={runs.reload} />
  if (runs.data.length === 0) return <EmptyState title="No collection runs recorded yet" />

  const health = sourceHealth(runs.data)
  return (
    <div className="space-y-6">
      <section className="card" aria-labelledby="health-h">
        <h2 id="health-h" className="border-b border-rule px-4 py-3 font-semibold">
          Source health <span className="font-normal text-slate-500">(last 50 runs)</span>
        </h2>
        {health.length === 0 ? (
          <EmptyState title="No sources have run yet">Runs so far were skipped because no source is enabled.</EmptyState>
        ) : (
          <ul className="divide-y divide-rule">
            {health.map((h) => (
              <li key={h.name} className="grid gap-1 px-4 py-3 text-sm sm:grid-cols-4">
                <span className="font-mono">
                  {h.name} <span className="text-xs text-slate-500">({h.origin})</span>
                </span>
                <span>
                  <StatusPill status={h.lastStatus} /> <span className="text-slate-500">{formatRelative(h.lastRunAt)}</span>
                </span>
                <span className="text-slate-600">Last success: {h.lastSuccessAt ? formatDateTime(h.lastSuccessAt) : 'never'}</span>
                <span className="break-words text-red-800">{h.lastError}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card overflow-x-auto" aria-labelledby="runs-h">
        <h2 id="runs-h" className="border-b border-rule px-4 py-3 font-semibold">
          Recent runs
        </h2>
        <table className="w-full text-left text-sm">
          <thead className="bg-navy-50 text-xs uppercase tracking-wide text-slate-600">
            <tr>
              {['Started', 'Status', 'Trigger', 'Found', 'New', 'Updated', 'Rejected', 'Errors'].map((h) => (
                <th key={h} scope="col" className="px-3 py-2 font-semibold">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-rule">
            {runs.data.map((r) => (
              <tr key={r.id} className="align-top">
                <td className="whitespace-nowrap px-3 py-2">{formatDateTime(r.started_at)}</td>
                <td className="px-3 py-2">
                  <StatusPill status={r.status} />
                </td>
                <td className="px-3 py-2">{r.trigger}</td>
                <td className="px-3 py-2 tabular-nums">{r.records_found}</td>
                <td className="px-3 py-2 tabular-nums">{r.records_inserted}</td>
                <td className="px-3 py-2 tabular-nums">{r.records_updated}</td>
                <td className="px-3 py-2 tabular-nums">{r.records_rejected}</td>
                <td className="max-w-md break-words px-3 py-2 text-red-800">{r.error_summary}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}
