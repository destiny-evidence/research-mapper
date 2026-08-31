import { useEffect, useRef, useState } from 'preact/hooks'

/**
 * Run `load` now, then every `interval` ms for as long as `active` says so.
 * Keeps the last good value on a failed refresh rather than blanking the page.
 *
 * `refresh` restarts the loop as well as reloading, because polling stops while
 * a session is parked on a question — answering it has to wake the loop back up.
 */
export function usePoll(load, { interval = 2000, active = () => true, deps = [] } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const [nudge, setNudge] = useState(0)
  const timer = useRef(null)

  useEffect(() => {
    let live = true
    const tick = async () => {
      try {
        const data = await load()
        if (!live) return
        setState({ data, error: null, loading: false })
        if (active(data)) timer.current = setTimeout(tick, interval)
      } catch (error) {
        if (!live) return
        setState((previous) => ({ ...previous, error, loading: false }))
        timer.current = setTimeout(tick, interval * 3)
      }
    }
    tick()
    return () => {
      live = false
      clearTimeout(timer.current)
    }
  }, [...deps, nudge])

  return { ...state, refresh: () => setNudge((n) => n + 1) }
}
