import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { AppRoutes } from '../App'
import { ApiProvider } from '../lib/api'
import type { DataApi } from '../lib/types'

export function renderApp(path: string, api: DataApi | null) {
  return render(
    <ApiProvider api={api}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </ApiProvider>,
  )
}
