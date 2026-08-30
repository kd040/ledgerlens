import { apiGet, apiPost } from "./client";
import type {
  ApiContradiction,
  ApiCreateInvestigationResponse,
  ApiEvidence,
  ApiHypothesis,
  ApiInvestigationDailyFinancialsResponse,
  ApiInvestigationDetail,
  ApiInvestigationSummary,
  ApiRunInvestigationResponse,
  ApiToolCall,
} from "./types";

export const investigationsApi = {
  list: () => apiGet<ApiInvestigationSummary[]>("/investigations"),

  get: (investigationId: string) =>
    apiGet<ApiInvestigationDetail>(`/investigations/${investigationId}`),

  create: (exceptionId: string) =>
    apiPost<ApiCreateInvestigationResponse>("/investigations", {
      exception_id: exceptionId,
    }),

  run: (investigationId: string) =>
    apiPost<ApiRunInvestigationResponse>(
      `/investigations/${investigationId}/run`,
    ),

  evidence: (investigationId: string) =>
    apiGet<ApiEvidence[]>(`/investigations/${investigationId}/evidence`),

  hypotheses: (investigationId: string) =>
    apiGet<ApiHypothesis[]>(`/investigations/${investigationId}/hypotheses`),

  toolCalls: (investigationId: string) =>
    apiGet<ApiToolCall[]>(`/investigations/${investigationId}/tool-calls`),

  contradictions: (investigationId: string) =>
    apiGet<ApiContradiction[]>(
      `/investigations/${investigationId}/contradictions`,
    ),

  dailyFinancials: (investigationId: string, date?: string) =>
    apiGet<ApiInvestigationDailyFinancialsResponse>(
      `/investigations/${investigationId}/financials/daily${date ? `?date=${date}` : ""}`,
    ),

  resolve: (investigationId: string, note: string) =>
    apiPost<ApiInvestigationDetail>(
      `/investigations/${investigationId}/resolve`,
      { note },
    ),

  escalate: (investigationId: string, note: string) =>
    apiPost<ApiInvestigationDetail>(
      `/investigations/${investigationId}/escalate`,
      { note },
    ),

  aiInvestigate: (investigationId: string) =>
    apiPost<ApiInvestigationDetail>(
      `/investigations/${investigationId}/ai-investigate`,
    ),
};
