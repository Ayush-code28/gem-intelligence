import { createContext, useContext, type ReactNode } from 'react'
import type { DataApi } from './types'

const ApiContext = createContext<DataApi | null>(null)

export function ApiProvider({ api, children }: { api: DataApi | null; children: ReactNode }) {
  return <ApiContext.Provider value={api}>{children}</ApiContext.Provider>
}

/** The configured API, or null when the site is not connected to a database. */
export function useApi(): DataApi | null {
  return useContext(ApiContext)
}

/** For components rendered only after the caller has checked that an API exists. */
export function useRequiredApi(): DataApi {
  const api = useContext(ApiContext)
  if (!api) throw new Error('Data API is not configured')
  return api
}
