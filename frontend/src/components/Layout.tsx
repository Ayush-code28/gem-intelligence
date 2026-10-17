import { NavLink, Outlet } from 'react-router'

const NAV = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/listings', label: 'Listings', end: false },
  { to: '/changes', label: 'Changes', end: false },
  { to: '/about', label: 'About & data policy', end: false },
]

export function Layout() {
  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2">
        Skip to content
      </a>
      <header className="bg-navy-900 text-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
          <NavLink to="/" className="flex items-center gap-3">
            <span className="grid size-9 place-items-center rounded-md bg-navy-700 font-mono text-sm font-bold text-saffron-500" aria-hidden>
              GI
            </span>
            <span>
              <span className="block text-base font-semibold leading-tight">GeM Intelligence</span>
              <span className="block text-xs text-navy-100/80">Independent procurement dashboard · not an official GeM site</span>
            </span>
          </NavLink>
          <nav aria-label="Main">
            <ul className="flex flex-wrap gap-1 text-sm">
              {NAV.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.end}
                    className={({ isActive }) =>
                      `block rounded-md px-3 py-1.5 font-medium transition ${
                        isActive ? 'bg-white/15 text-white' : 'text-navy-100 hover:bg-white/10 hover:text-white'
                      }`
                    }
                  >
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
        </div>
      </header>
      <main id="main" className="mx-auto w-full max-w-7xl flex-1 px-4 py-8">
        <Outlet />
      </main>
      <footer className="border-t border-rule bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-6 text-xs text-slate-600 sm:flex-row sm:justify-between">
          <p>
            Independent dashboard. Not affiliated with, endorsed by or operated by Government e-Marketplace (GeM) or the
            Government of India. Always verify details on the official portal.
          </p>
          <NavLink to="/admin" className="shrink-0 text-slate-500 hover:text-ink">
            Operator sign-in
          </NavLink>
        </div>
      </footer>
    </div>
  )
}

export function PageHeader({ title, description }: { title: string; description?: string }) {
  return (
    <div className="mb-6">
      <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">{title}</h1>
      {description && <p className="mt-1 max-w-3xl text-slate-600">{description}</p>}
    </div>
  )
}
