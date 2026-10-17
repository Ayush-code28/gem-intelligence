import { useCallback, useEffect, useState } from 'react'

export type AsyncState<T> =
  | { status: 'loading'; data: undefined; error: undefined }
  | { status: 'success'; data: T; error: undefined }
  | { status: 'error'; data: undefined; error: Error }

type Settled<T> = { key: string } & ({ ok: true; data: T } | { ok: false; error: Error })

/** Runs `fn` whenever `key` changes. While the result for the current key is pending the state
 *  is "loading"; results from superseded calls are ignored. */
export function useAsync<T>(fn: () => Promise<T>, key: string): AsyncState<T> & { reload: () => void } {
  const [nonce, setNonce] = useState(0)
  const [settled, setSettled] = useState<Settled<T> | null>(null)
  const fullKey = `${key}#${nonce}`

  useEffect(() => {
    let active = true
    fn().then(
      (data) => active && setSettled({ key: fullKey, ok: true, data }),
      (err: unknown) =>
        active && setSettled({ key: fullKey, ok: false, error: err instanceof Error ? err : new Error(String(err)) }),
    )
    return () => {
      active = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` captures fn's inputs
  }, [fullKey])

  const reload = useCallback(() => setNonce((n) => n + 1), [])
  if (!settled || settled.key !== fullKey) return { status: 'loading', data: undefined, error: undefined, reload }
  return settled.ok
    ? { status: 'success', data: settled.data, error: undefined, reload }
    : { status: 'error', data: undefined, error: settled.error, reload }
}
