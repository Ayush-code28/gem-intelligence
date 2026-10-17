import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { fakeApi, freshStatus, makeListing, pending } from '../test/fakeApi'
import { renderApp } from '../test/render'

describe('not connected (demonstration state)', () => {
  it.each(['/', '/listings', '/changes', '/admin', `/listings/${makeListing(1).id}`])(
    'shows an explicit notice and no data on %s',
    async (path) => {
      renderApp(path, null)
      expect(await screen.findByText(/no database connected/i)).toBeInTheDocument()
      expect(screen.queryByText(/Synthetic listing/)).not.toBeInTheDocument()
    },
  )
})

describe('dashboard', () => {
  it('shows loading states while data is pending', () => {
    const api = fakeApi({ getStats: () => pending(), getCollectionStatus: () => pending(), listListings: () => pending(), listChanges: () => pending() })
    renderApp('/', api)
    expect(screen.getAllByRole('status').length).toBeGreaterThan(0)
  })

  it('renders statistics from the API, recent listings and changes', async () => {
    renderApp('/', fakeApi())
    expect(await screen.findByText('1,234')).toBeInTheDocument()
    expect(screen.getByText('Live data is current')).toBeInTheDocument()
    expect(screen.getByText(/By origin:/)).toHaveTextContent('1,000 live-collected · 200 imported · 0 synthetic demo')
    expect(screen.queryByText(/Contains synthetic demonstration data/)).not.toBeInTheDocument()
    expect((await screen.findAllByText('Synthetic listing 1')).length).toBeGreaterThan(0)
    expect(screen.getByText('Deadline changed')).toBeInTheDocument()
  })

  it('renders empty states', async () => {
    renderApp('/', fakeApi({ listListings: async () => ({ rows: [], total: 0 }), listChanges: async () => ({ rows: [], total: 0 }) }))
    expect(await screen.findByText('No listings collected yet')).toBeInTheDocument()
    expect(screen.getByText('No changes detected yet')).toBeInTheDocument()
  })

  it('renders an error state with retry', async () => {
    let calls = 0
    const api = fakeApi({
      getStats: async () => {
        calls += 1
        if (calls === 1) throw new Error('network down')
        return (await fakeApi().getStats())
      },
    })
    renderApp('/', api)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('network down')
    await userEvent.click(within(alert).getByRole('button', { name: /try again/i }))
    expect(await screen.findByText('1,234')).toBeInTheDocument()
  })

  it('warns when data is stale or the last run failed', async () => {
    const old = new Date(Date.now() - 72 * 3_600_000).toISOString()
    renderApp('/', fakeApi({ getCollectionStatus: async () => freshStatus({ last_live_success_at: old, last_run_status: 'partial', sources_failed: ['b_source'] }) }))
    expect(await screen.findByText('Live data may be out of date')).toBeInTheDocument()
    expect(screen.getByText(/No successful live collection in the last 36 hours/)).toBeInTheDocument()
    expect(screen.getByText(/sources not updated: b_source/)).toBeInTheDocument()
  })

  it('never presents imports as a live collection', async () => {
    const importedAt = new Date().toISOString()
    renderApp(
      '/',
      fakeApi({
        getCollectionStatus: async () =>
          freshStatus({ last_live_success_at: null, last_success_at: importedAt, last_import_at: importedAt, last_run_status: 'skipped' }),
      }),
    )
    expect(await screen.findByText('No live collection')).toBeInTheDocument()
    expect(screen.getByText(/No live GeM collection has succeeded/)).toBeInTheDocument()
    expect(screen.getByText(/Last file import:/)).toBeInTheDocument()
    expect(screen.queryByText('Live data is current')).not.toBeInTheDocument()
  })

  it('warns prominently when synthetic data is present', async () => {
    renderApp('/', fakeApi({ getStats: async () => ({ ...(await fakeApi().getStats()), synthetic_listings: 60 }) }))
    expect(await screen.findByText(/Contains synthetic demonstration data/)).toBeInTheDocument()
    expect(screen.getByRole('note')).toHaveTextContent('60 records are invented for testing')
  })
})

describe('listings', () => {
  it('passes search, filters, sort and page to the API from the URL', async () => {
    const api = fakeApi()
    renderApp('/listings?q=chairs&category=Products&from=2030-01-01&to=2030-01-31&sort=deadline&page=2', api)
    await screen.findAllByText('Synthetic listing 1')
    expect(api.listListings).toHaveBeenCalledWith({
      search: 'chairs',
      category: 'Products',
      deadlineFrom: '2030-01-01',
      deadlineTo: '2030-01-31',
      sort: 'deadline',
      page: 2,
      pageSize: 25,
    })
  })

  it('labels each listing with its origin and filters by origin', async () => {
    const api = fakeApi({
      listListings: vi.fn(async () => ({
        rows: [makeListing(1), makeListing(2, { data_origin: 'imported' }), makeListing(3, { data_origin: 'synthetic' })],
        total: 3,
      })),
    })
    renderApp('/listings?origin=synthetic', api)
    expect((await screen.findAllByText('Synthetic demo')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('Imported').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Live-collected').length).toBeGreaterThan(0)
    expect(api.listListings).toHaveBeenCalledWith(expect.objectContaining({ origin: 'synthetic' }))
  })

  it('ignores malformed URL parameters', async () => {
    const api = fakeApi()
    renderApp('/listings?sort=evil&page=-4&from=yesterday&origin=real', api)
    await screen.findAllByText('Synthetic listing 1')
    expect(api.listListings).toHaveBeenCalledWith(
      expect.objectContaining({ sort: 'newest', page: 1, deadlineFrom: undefined, origin: undefined }),
    )
  })

  it('submits a search', async () => {
    const api = fakeApi()
    renderApp('/listings', api)
    await screen.findAllByText('Synthetic listing 1')
    await userEvent.type(screen.getByLabelText(/search title/i), 'pumps')
    await userEvent.click(screen.getByRole('button', { name: 'Search' }))
    await waitFor(() => expect(api.listListings).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'pumps', page: 1 })))
  })

  it('shows "Not available" for missing fields', async () => {
    renderApp('/listings', fakeApi({ listListings: async () => ({ rows: [makeListing(3, { organisation: null, deadline: null, bid_number: null })], total: 1 }) }))
    expect((await screen.findAllByText('Not available')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('Deadline not available').length).toBeGreaterThan(0)
  })

  it('shows an empty state', async () => {
    renderApp('/listings?q=zzz', fakeApi({ listListings: async () => ({ rows: [], total: 0 }) }))
    expect(await screen.findByText('No listings match these filters')).toBeInTheDocument()
  })

  it('shows an error state', async () => {
    renderApp('/listings', fakeApi({ listListings: async () => Promise.reject(new Error('permission denied')) }))
    expect(await screen.findByRole('alert')).toHaveTextContent('permission denied')
  })

  it('paginates', async () => {
    const api = fakeApi({ listListings: vi.fn(async () => ({ rows: [makeListing(1)], total: 60 })) })
    renderApp('/listings', api)
    await userEvent.click(await screen.findByRole('button', { name: 'Next' }))
    await waitFor(() => expect(api.listListings).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 })))
  })
})

describe('listing detail', () => {
  it('shows fields, a safe external source link and history', async () => {
    renderApp(`/listings/${makeListing(1).id}`, fakeApi())
    expect(await screen.findByRole('heading', { name: 'Synthetic listing 1' })).toBeInTheDocument()
    const link = screen.getByRole('link', { name: /verify on the official gem portal/i })
    expect(link).toHaveAttribute('href', 'https://bidplus.gem.gov.in/showbidDocument/1')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link.getAttribute('rel')).toContain('noopener')
    expect(screen.getByText('First discovered')).toBeInTheDocument()
    expect(screen.getByText('Last checked')).toBeInTheDocument()
    expect(await screen.findByText('Deadline changed')).toBeInTheDocument()
  })

  it.each([
    ['synthetic', /Synthetic demonstration record/],
    ['imported', /Imported record/],
  ] as const)('explains %s provenance', async (origin, text) => {
    renderApp(`/listings/${makeListing(1).id}`, fakeApi({ getListing: async () => makeListing(1, { data_origin: origin }) }))
    expect(await screen.findByText(text)).toBeInTheDocument()
  })

  it('flags live listings not re-observed recently', async () => {
    renderApp(`/listings/${makeListing(1).id}`, fakeApi({ getListing: async () => makeListing(1, { last_seen_at: '2020-01-01T00:00:00Z' }) }))
    expect(await screen.findByText(/Not re-observed recently/)).toBeInTheDocument()
  })

  it('never links to non-GeM or unsafe URLs', async () => {
    renderApp(`/listings/${makeListing(1).id}`, fakeApi({ getListing: async () => makeListing(1, { url: 'javascript:alert(1)' }) }))
    expect(await screen.findByText('Source link not available')).toBeInTheDocument()
  })

  it('handles unknown and malformed ids', async () => {
    renderApp('/listings/00000000-0000-4000-8000-999999999999', fakeApi())
    expect(await screen.findByText('Listing not found')).toBeInTheDocument()
    renderApp('/listings/not-a-uuid', fakeApi())
    expect((await screen.findAllByText('Listing not found')).length).toBeGreaterThan(0)
  })
})

describe('changes', () => {
  it('lists updates with old and new values', async () => {
    renderApp('/changes', fakeApi())
    expect(await screen.findByText('Deadline changed')).toBeInTheDocument()
    expect(screen.getByText('Synthetic listing 1')).toBeInTheDocument()
  })

  it('switches to newly discovered listings', async () => {
    const api = fakeApi()
    renderApp('/changes', api)
    await userEvent.click(await screen.findByRole('tab', { name: 'Newly discovered' }))
    await waitFor(() => expect(api.listListings).toHaveBeenCalledWith(expect.objectContaining({ sort: 'newest' })))
  })

  it('shows an empty state', async () => {
    renderApp('/changes', fakeApi({ listChanges: async () => ({ rows: [], total: 0 }) }))
    expect(await screen.findByText('No updates detected yet')).toBeInTheDocument()
  })
})

describe('admin monitoring', () => {
  it('asks anonymous visitors to sign in and shows no run data', async () => {
    const api = fakeApi()
    renderApp('/admin', api)
    expect(await screen.findByRole('form', { name: /operator sign-in/i })).toBeInTheDocument()
    expect(api.listRuns).not.toHaveBeenCalled()
  })

  it('refuses signed-in users who are not admins', async () => {
    const api = fakeApi({ getCurrentUser: async () => ({ email: 'viewer@example.com' }), isAdmin: async () => false })
    renderApp('/admin', api)
    expect(await screen.findByText('Not authorised')).toBeInTheDocument()
    expect(api.listRuns).not.toHaveBeenCalled()
  })

  it('shows runs and source health to admins', async () => {
    const api = fakeApi({ getCurrentUser: async () => ({ email: 'ops@example.com' }), isAdmin: async () => true })
    renderApp('/admin', api)
    expect(await screen.findByText('Recent runs')).toBeInTheDocument()
    expect(screen.getByText('a_source')).toBeInTheDocument()
    expect(screen.getAllByText(/SourceAccessBlocked/).length).toBeGreaterThan(0)
    expect(screen.getAllByText('partial').length).toBeGreaterThan(0)
  })

  it('reports sign-in errors', async () => {
    const api = fakeApi({ signIn: async () => Promise.reject(new Error('Invalid login credentials')) })
    renderApp('/admin', api)
    await userEvent.type(await screen.findByLabelText('Email'), 'a@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'wrong-password')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('Invalid login credentials')).toBeInTheDocument()
  })
})

describe('about', () => {
  it('states independence from GeM', () => {
    renderApp('/about', null)
    expect(screen.getByText(/An independent dashboard — not the GeM portal/)).toBeInTheDocument()
  })
})

