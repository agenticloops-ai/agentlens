import { useCallback } from "react";
import { useProviders } from "../api/hooks";
import type { ProviderMeta } from "../api/client";

const DEFAULT_META: ProviderMeta = {
  name: "unknown",
  display_name: "Unknown",
  color: "#6b7280",
};

/**
 * Returns a lookup function that maps a provider name to its metadata.
 * Provider colors come from the backend /api/providers endpoint.
 */
export function useProviderMeta() {
  const { data: providers } = useProviders();

  return useCallback(
    (providerName: string): ProviderMeta => {
      if (!providers) return DEFAULT_META;
      return providers.find((p) => p.name === providerName) ?? DEFAULT_META;
    },
    [providers],
  );
}
