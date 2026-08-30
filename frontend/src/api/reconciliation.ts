import { apiPost } from "./client";
import type { ApiRunSourceResponse } from "./types";
import type { DataSource } from "../domain/types";

export interface RunSourceParams {
  source: DataSource;
  from: Date;
  to: Date;
}

export const reconciliationApi = {
  /** The daily workflow's one call: fetch -> normalize -> persist ->
   * scoped reconcile for the given source and period. */
  runSource: ({ source, from, to }: RunSourceParams) =>
    apiPost<ApiRunSourceResponse>("/reconciliation/sources/run", {
      source,
      from: from.toISOString(),
      to: to.toISOString(),
    }),
};
