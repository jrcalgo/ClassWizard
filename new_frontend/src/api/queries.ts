import { useInfiniteQuery, useQuery, type QueryClient } from "@tanstack/react-query";

import * as endpoints from "./endpoints";

export const keys = {
  config: ["config"] as const,
  me: ["me"] as const,
  occupations: ["occupations"] as const,
  conceptCourses: ["concept-maps"] as const,
  conceptMap: (code: string) => ["concept-maps", code] as const,
  searches: ["me", "searches"] as const,
  audits: ["me", "audits"] as const,
  activity: ["me", "activity"] as const,
};

export function useConfig() {
  return useQuery({ queryKey: keys.config, queryFn: endpoints.getConfig, staleTime: Infinity, retry: 1 });
}

export function useMe() {
  return useQuery({
    queryKey: keys.me,
    queryFn: endpoints.getMe,
    staleTime: 60_000,
    select: (data) => data.user,
  });
}

export function useOccupations() {
  return useQuery({ queryKey: keys.occupations, queryFn: endpoints.getOccupations, staleTime: 300_000 });
}

export function useConceptMapCourses() {
  return useQuery({
    queryKey: keys.conceptCourses,
    queryFn: endpoints.getConceptMapCourses,
    staleTime: Infinity,
    select: (data) => data.courses,
  });
}

export function useConceptMap(code: string | null) {
  return useQuery({
    queryKey: keys.conceptMap(code ?? ""),
    queryFn: () => endpoints.getConceptMap(code as string),
    enabled: Boolean(code),
    staleTime: Infinity,
  });
}

export function useSearches(enabled: boolean, limit = 30) {
  return useQuery({
    queryKey: [...keys.searches, limit],
    queryFn: () => endpoints.listSearches(limit),
    enabled,
    select: (data) => data.searches,
  });
}

export function useSavedAudits(enabled: boolean) {
  return useQuery({
    queryKey: keys.audits,
    queryFn: endpoints.listSavedAudits,
    enabled,
    select: (data) => data.audits,
  });
}

export function useActivity(enabled: boolean) {
  return useInfiniteQuery({
    queryKey: keys.activity,
    queryFn: ({ pageParam }) => endpoints.listActivity(pageParam),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (last) => last.next_before ?? undefined,
    enabled,
  });
}

/**
 * Forget the signed-in user without detaching mounted components: removing
 * queries that still have observers leaves those components on a stale copy.
 */
export function markSignedOut(queryClient: QueryClient) {
  queryClient.setQueryData(keys.me, { user: null });
  void queryClient.resetQueries({ predicate: (q) => q.queryKey[0] === "me" && q.queryKey.length > 1 });
}
