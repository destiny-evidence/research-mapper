import { useEffect, useRef, useState } from "preact/hooks";

const POLL_INTERVAL_MS = 1000;

/**
 * Run `load` now, then every `interval` ms for as long as `active` says so.
 */
export function usePoll(
  load,
  {
    interval = POLL_INTERVAL_MS,
    active = () => true,
    deps = [],
    skip = false,
  } = {},
) {
  const [state, setState] = useState({
    data: null,
    error: null,
    loading: true,
  });
  const [nudge, setNudge] = useState(0);
  const timer = useRef(null);

  useEffect(() => {
    if (skip) return;
    let live = true;
    const tick = async () => {
      try {
        const data = await load();
        if (!live) return;
        setState({ data, error: null, loading: false });
        if (active(data)) timer.current = setTimeout(tick, interval);
      } catch (error) {
        if (!live) return;
        setState((previous) => ({ ...previous, error, loading: false }));
        timer.current = setTimeout(tick, interval * 3);
      }
    };
    tick();
    return () => {
      live = false;
      clearTimeout(timer.current);
    };
  }, [...deps, nudge, skip]);

  return { ...state, refresh: () => setNudge((n) => n + 1) };
}
