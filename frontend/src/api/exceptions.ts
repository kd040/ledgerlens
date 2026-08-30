import { apiGet } from "./client";
import type { ApiDuplicateSettlementsResponse, ApiException } from "./types";

export const exceptionsApi = {
  list: () => apiGet<ApiException[]>("/exceptions"),
  get: (exceptionId: string) =>
    apiGet<ApiException>(`/exceptions/${exceptionId}`),
  duplicateSettlements: (exceptionId: string) =>
    apiGet<ApiDuplicateSettlementsResponse>(
      `/exceptions/${exceptionId}/duplicate-settlements`,
    ),
};
