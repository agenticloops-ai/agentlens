import { useEffect } from "react";
import { useLiveStore } from "../stores/liveStore";
import { queryClient } from "./queryClient";
import type { LiveEvent } from "../types";

/**
 * React hook that subscribes to the live WebSocket event stream and
 * invalidates the relevant React Query caches so UI stays in sync.
 *
 * Mount this once at a high level (e.g. in Layout) so it is always active.
 */
export function useLiveUpdates() {
  useEffect(() => {
    const unsubscribe = useLiveStore.getState().subscribe((event: LiveEvent) => {
      switch (event.type) {
        case "new_request":
          // Invalidate the session requests list so the timeline refreshes
          queryClient.invalidateQueries({
            queryKey: ["requests", event.data.session_id],
          });
          // Also refresh the individual session detail (request_count, tokens, etc.)
          queryClient.invalidateQueries({
            queryKey: ["sessions", event.data.session_id],
          });
          break;

        case "session_updated":
          // Invalidate both the sessions list and the specific session detail
          queryClient.invalidateQueries({ queryKey: ["sessions"] });
          break;
      }
    });

    return unsubscribe;
  }, []);
}
