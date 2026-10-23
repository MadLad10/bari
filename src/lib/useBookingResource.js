import { useCallback, useEffect, useRef, useState } from "react";

export default function useBookingResource(fetcher, accountId) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const generation = useRef(0);
  const refreshRef = useRef(null);

  useEffect(() => {
    const version = ++generation.current;
    let alive = true;
    setData(null); setLoading(true); setError(null); setRefreshing(false);
    if (!accountId) return;
    let inFlight = null;
    const load = () => {
      if (inFlight) return inFlight;
      if (alive) setRefreshing(true);
      inFlight = (async () => {
        try {
          const result = await fetcher();
          if (alive && generation.current === version) { setData(result); setError(null); }
        } catch (e) { if (alive && generation.current === version) setError(e); }
        finally { inFlight = null; if (alive && generation.current === version) { setLoading(false); setRefreshing(false); } }
      })();
      return inFlight;
    };
    // A post-mutation refresh must fetch after any earlier poll, not reuse its stale response.
    refreshRef.current = async () => { if (inFlight) await inFlight; if (alive) await load(); };
    load();
    const onFocus = () => load();
    window.addEventListener("focus", onFocus);
    const timer = setInterval(() => { if (!document.hidden) load(); }, 15000);
    return () => { alive = false; clearInterval(timer); window.removeEventListener("focus", onFocus); refreshRef.current = null; };
  }, [fetcher, accountId]);
  const refresh = useCallback(() => refreshRef.current?.(), []);
  return { data, loading, refreshing, error, refresh };
}
