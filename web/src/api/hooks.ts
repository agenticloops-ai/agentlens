import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export function useSessions() {
  return useQuery({
    queryKey: ["sessions"],
    queryFn: api.sessions.list,
    refetchInterval: 5000,
  });
}

export function useSession(id: string) {
  return useQuery({
    queryKey: ["sessions", id],
    queryFn: () => api.sessions.get(id),
    enabled: !!id,
  });
}

export function useSessionRequests(
  sessionId: string,
  params?: Parameters<typeof api.requests.listBySession>[1],
) {
  return useQuery({
    queryKey: ["requests", sessionId, params],
    queryFn: () => api.requests.listBySession(sessionId, params),
    enabled: !!sessionId,
  });
}

export function useRequest(id: string) {
  return useQuery({
    queryKey: ["request", id],
    queryFn: () => api.requests.get(id),
    enabled: !!id,
  });
}

export function useRawCapture(id: string) {
  return useQuery({
    queryKey: ["raw", id],
    queryFn: () => api.requests.getRaw(id),
    enabled: !!id,
  });
}

export function useDeleteSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.sessions.delete,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  });
}

export function useProviders() {
  return useQuery({
    queryKey: ["providers"],
    queryFn: api.providers.list,
    staleTime: 60 * 60 * 1000, // 1 hour — provider metadata rarely changes
  });
}

export function useDeleteAllSessions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.sessions.deleteAll,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  });
}
