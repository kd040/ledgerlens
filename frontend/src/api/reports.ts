import { apiGet } from "./client";
import type { ApiReportSummary } from "./types";

export const reportsApi = {
  summary: (start?: string, end?: string) => {
    const params = new URLSearchParams();
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    const query = params.toString();
    return apiGet<ApiReportSummary>(`/reports/summary${query ? `?${query}` : ""}`);
  },
};
