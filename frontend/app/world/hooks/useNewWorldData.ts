import { useCallback, useEffect, useRef, useState } from "react";
import { fetchApiClient } from "../../../lib/api";
import { normalizePayload } from "../constants";
import { NewWorldPayload } from "../types";

export function useNewWorldData() {
  const [payload, setPayload] = useState<NewWorldPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const initialLoadStarted = useRef(false);

  const load = useCallback(async (force = false) => {
    setLoading(true);
    setError("");
    try {
      const nextPayload = await fetchApiClient<Partial<NewWorldPayload>>(`/api/new-world${force ? "?force=true" : ""}`, { retries: 1, timeoutMs: 70000 });
      setPayload(normalizePayload(nextPayload));
    } catch {
      setError("新世界情报暂时无法到达。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (initialLoadStarted.current) return;
    initialLoadStarted.current = true;
    void load();
  }, [load]);

  return { error, load, loading, payload };
}
