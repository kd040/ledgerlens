/**
 * React Query hooks. These are the only data-access surface components
 * should use -- each hook calls the raw API function and normalizes the
 * result before returning it, so components never see Api* shapes.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { authApi } from "./auth";
import { exceptionsApi } from "./exceptions";
import { investigationsApi } from "./investigations";
import { reconciliationApi, type RunSourceParams } from "./reconciliation";
import { reportsApi } from "./reports";
import { ApiError } from "./client";
import {
  normalizeContradiction,
  normalizeCurrentUser,
  normalizeDuplicateSettlements,
  normalizeEvidence,
  normalizeException,
  normalizeHypothesis,
  normalizeInvestigationDailyFinancials,
  normalizeInvestigationDetail,
  normalizeInvestigationSummary,
  normalizeReportSummary,
  normalizeRunSourceResponse,
  normalizeToolCall,
} from "../domain/normalize";

export const authKeys = {
  me: ["auth", "me"] as const,
};

/** The current session's identity, or `null` if unauthenticated (a 401
 * is the expected "logged out" response, not an error to retry/surface). */
export function useMe() {
  return useQuery({
    queryKey: authKeys.me,
    queryFn: async () => {
      try {
        return normalizeCurrentUser(await authApi.me());
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    retry: false,
    staleTime: 60_000,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      authApi.login(email, password),
    onSuccess: (user) => {
      queryClient.setQueryData(authKeys.me, normalizeCurrentUser(user));
    },
  });
}

/** Does not touch the me-query cache -- registration never auto-logs-in
 * (see SignupPage), the caller redirects to /login on success instead. */
export function useRegister() {
  return useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      authApi.register(email, password),
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => authApi.logout(),
    onSuccess: () => {
      queryClient.setQueryData(authKeys.me, null);
      queryClient.clear();
    },
  });
}

export const exceptionKeys = {
  all: ["exceptions"] as const,
  detail: (id: string) => ["exceptions", id] as const,
  duplicateSettlements: (id: string) =>
    ["exceptions", id, "duplicate-settlements"] as const,
};

export function useExceptions() {
  return useQuery({
    queryKey: exceptionKeys.all,
    queryFn: async () => (await exceptionsApi.list()).map(normalizeException),
  });
}

export function useException(exceptionId: string | undefined) {
  return useQuery({
    queryKey: exceptionKeys.detail(exceptionId ?? ""),
    queryFn: async () =>
      normalizeException(await exceptionsApi.get(exceptionId as string)),
    enabled: Boolean(exceptionId),
  });
}

export function useDuplicateSettlements(exceptionId: string | undefined) {
  return useQuery({
    queryKey: exceptionKeys.duplicateSettlements(exceptionId ?? ""),
    queryFn: async () =>
      normalizeDuplicateSettlements(
        await exceptionsApi.duplicateSettlements(exceptionId as string),
      ),
    enabled: Boolean(exceptionId),
  });
}

export const investigationKeys = {
  all: ["investigations"] as const,
  detail: (id: string) => ["investigations", id] as const,
  evidence: (id: string) => ["investigations", id, "evidence"] as const,
  hypotheses: (id: string) => ["investigations", id, "hypotheses"] as const,
  toolCalls: (id: string) => ["investigations", id, "tool-calls"] as const,
  contradictions: (id: string) =>
    ["investigations", id, "contradictions"] as const,
  dailyFinancials: (id: string, date: string | undefined) =>
    ["investigations", id, "financials-daily", date ?? null] as const,
};

export function useInvestigations() {
  return useQuery({
    queryKey: investigationKeys.all,
    queryFn: async () =>
      (await investigationsApi.list()).map(normalizeInvestigationSummary),
  });
}

export function useInvestigation(investigationId: string | undefined) {
  return useQuery({
    queryKey: investigationKeys.detail(investigationId ?? ""),
    queryFn: async () =>
      normalizeInvestigationDetail(
        await investigationsApi.get(investigationId as string),
      ),
    enabled: Boolean(investigationId),
  });
}

export function useInvestigationEvidence(investigationId: string | undefined) {
  return useQuery({
    queryKey: investigationKeys.evidence(investigationId ?? ""),
    queryFn: async () =>
      (await investigationsApi.evidence(investigationId as string)).map(
        normalizeEvidence,
      ),
    enabled: Boolean(investigationId),
  });
}

export function useInvestigationHypotheses(
  investigationId: string | undefined,
) {
  return useQuery({
    queryKey: investigationKeys.hypotheses(investigationId ?? ""),
    queryFn: async () =>
      (await investigationsApi.hypotheses(investigationId as string)).map(
        normalizeHypothesis,
      ),
    enabled: Boolean(investigationId),
  });
}

export function useInvestigationToolCalls(
  investigationId: string | undefined,
) {
  return useQuery({
    queryKey: investigationKeys.toolCalls(investigationId ?? ""),
    queryFn: async () =>
      (await investigationsApi.toolCalls(investigationId as string)).map(
        normalizeToolCall,
      ),
    enabled: Boolean(investigationId),
  });
}

export function useInvestigationContradictions(
  investigationId: string | undefined,
) {
  return useQuery({
    queryKey: investigationKeys.contradictions(investigationId ?? ""),
    queryFn: async () =>
      (
        await investigationsApi.contradictions(investigationId as string)
      ).map(normalizeContradiction),
    enabled: Boolean(investigationId),
  });
}

export function useInvestigationDailyFinancials(
  investigationId: string | undefined,
  date: string | undefined,
) {
  return useQuery({
    queryKey: investigationKeys.dailyFinancials(investigationId ?? "", date),
    queryFn: async () =>
      normalizeInvestigationDailyFinancials(
        await investigationsApi.dailyFinancials(investigationId as string, date),
      ),
    enabled: Boolean(investigationId),
  });
}

export function useResolveInvestigation(investigationId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (note: string) =>
      investigationsApi.resolve(investigationId as string, note),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: investigationKeys.all });
      if (investigationId) {
        queryClient.invalidateQueries({
          queryKey: investigationKeys.detail(investigationId),
        });
      }
      queryClient.invalidateQueries({ queryKey: exceptionKeys.all });
    },
  });
}

export function useEscalateInvestigation(investigationId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (note: string) =>
      investigationsApi.escalate(investigationId as string, note),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: investigationKeys.all });
      if (investigationId) {
        queryClient.invalidateQueries({
          queryKey: investigationKeys.detail(investigationId),
        });
      }
      queryClient.invalidateQueries({ queryKey: exceptionKeys.all });
    },
  });
}

/** Runs the additive AI Investigator pass on an already-run
 * investigation -- see backend/app/ai/investigator.py. Same
 * invalidation set as useRunInvestigation: the AI writes evidence,
 * hypotheses, contradictions, and tool-call records exactly like the
 * deterministic runner does, alongside the investigation's own
 * root_cause_assessment/confidence/recommendation. */
export function useRunAiInvestigation(investigationId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => investigationsApi.aiInvestigate(investigationId as string),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: investigationKeys.all });
      if (investigationId) {
        queryClient.invalidateQueries({
          queryKey: investigationKeys.detail(investigationId),
        });
        queryClient.invalidateQueries({
          queryKey: investigationKeys.evidence(investigationId),
        });
        queryClient.invalidateQueries({
          queryKey: investigationKeys.hypotheses(investigationId),
        });
        queryClient.invalidateQueries({
          queryKey: investigationKeys.toolCalls(investigationId),
        });
        queryClient.invalidateQueries({
          queryKey: investigationKeys.contradictions(investigationId),
        });
      }
    },
  });
}

export function useCreateInvestigation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (exceptionId: string) =>
      investigationsApi.create(exceptionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: investigationKeys.all });
    },
  });
}

export function useRunInvestigation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (investigationId: string) =>
      investigationsApi.run(investigationId),
    onSuccess: (_data, investigationId) => {
      queryClient.invalidateQueries({ queryKey: investigationKeys.all });
      queryClient.invalidateQueries({
        queryKey: investigationKeys.detail(investigationId),
      });
      queryClient.invalidateQueries({
        queryKey: investigationKeys.evidence(investigationId),
      });
      queryClient.invalidateQueries({
        queryKey: investigationKeys.hypotheses(investigationId),
      });
      queryClient.invalidateQueries({
        queryKey: investigationKeys.toolCalls(investigationId),
      });
      queryClient.invalidateQueries({
        queryKey: investigationKeys.contradictions(investigationId),
      });
    },
  });
}

/** Creates (if needed) and immediately runs an investigation for an
 * exception -- the "Start Investigation" action on the Exception Center. */
export function useStartInvestigation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (exceptionId: string) => {
      const investigation = await investigationsApi.create(exceptionId);
      return investigationsApi.run(investigation.id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: exceptionKeys.all });
      queryClient.invalidateQueries({ queryKey: investigationKeys.all });
    },
  });
}

export const reportKeys = {
  summary: (start: string | null, end: string | null) =>
    ["reports", "summary", start, end] as const,
};

/** The whole Reports page in one request -- read-only aggregates over
 * data the reconciliation and investigation flows already persisted, so
 * it never triggers a reconciliation run of its own. */
export function useReportSummary(
  start: string | null,
  end: string | null,
) {
  return useQuery({
    queryKey: reportKeys.summary(start, end),
    queryFn: async () =>
      normalizeReportSummary(
        await reportsApi.summary(start ?? undefined, end ?? undefined),
      ),
  });
}

/** The daily workflow's primary action: fetch, normalize, persist, and
 * scoped-reconcile one data source over one period, in one call. */
export function useRunReconciliationSource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (params: RunSourceParams) =>
      normalizeRunSourceResponse(await reconciliationApi.runSource(params)),
    onSuccess: () => {
      // A run can create new EX01/EX02 exceptions (never for
      // SETTLEMENT_PENDING) -- refresh the Exception Center / the
      // results table's exception cross-reference.
      queryClient.invalidateQueries({ queryKey: exceptionKeys.all });
    },
  });
}
