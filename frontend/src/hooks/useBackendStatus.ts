import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { HealthResponse, PublicConfig } from "../types/api";

export type BackendState =
  | { phase: "loading" }
  | { phase: "ready"; health: HealthResponse; config: PublicConfig }
  | { phase: "error"; message: string };

/** Loads backend health and the centralised public config once on mount. */
export function useBackendStatus(): BackendState {
  const [state, setState] = useState<BackendState>({ phase: "loading" });

  useEffect(() => {
    const ctrl = new AbortController();
    Promise.all([api.health(ctrl.signal), api.publicConfig(ctrl.signal)])
      .then(([health, config]) => setState({ phase: "ready", health, config }))
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        setState({ phase: "error", message: err instanceof Error ? err.message : "Backend unreachable" });
      });
    return () => ctrl.abort();
  }, []);

  return state;
}
