/**
 * The canonical "gross processed" definition, asserted on the frontend
 * side. The matching backend assertions live in
 * backend/tests/test_reports.py (test_gross_processed_counts_only_captured_payments)
 * -- between them they pin both halves of the rule that Overview,
 * Reconciliation and Reports all mean the same thing by "gross".
 */
import { describe, expect, it } from "vitest";
import { computeFinancials } from "./reconciliationMetrics";
import { countsTowardGrossProcessed } from "./status";
import type { ReconciliationResult } from "../domain/types";

function row(
  overrides: Partial<ReconciliationResult> = {},
): ReconciliationResult {
  return {
    payment: "PAY-001",
    status: "RECONCILED",
    category: null,
    grossAmount: 1000,
    feeAmount: 20,
    taxAmount: 3.6,
    adjustmentAmount: 0,
    expectedAmount: 976.4,
    observedAmount: 976.4,
    difference: 0,
    settlementCount: null,
    paymentDate: "2026-08-24",
    paymentCreatedAt: new Date("2026-08-24T18:11:02.000Z"),
    paymentStatus: "CAPTURED",
    ...overrides,
  };
}

/** A row with no settlement arithmetic -- what the engine emits for a
 * payment it never reconciled. */
function unsettledRow(
  status: ReconciliationResult["status"],
  gross: number,
  paymentStatus: string,
): ReconciliationResult {
  return row({
    status,
    paymentStatus,
    grossAmount: gross,
    feeAmount: null,
    taxAmount: null,
    adjustmentAmount: null,
    expectedAmount: null,
    observedAmount: null,
    difference: null,
  });
}

describe("countsTowardGrossProcessed", () => {
  it("counts every outcome that reached settlement evaluation", () => {
    for (const status of [
      "RECONCILED",
      "SETTLEMENT_PENDING",
      "EX01",
      "EX02",
      "EX03",
    ]) {
      expect(countsTowardGrossProcessed(status)).toBe(true);
    }
  });

  it("excludes payments that never became money owed", () => {
    expect(countsTowardGrossProcessed("NOT_CAPTURED")).toBe(false);
    expect(countsTowardGrossProcessed("UNKNOWN_STATUS")).toBe(false);
  });
});

describe("computeFinancials gross", () => {
  it("counts captured payments", () => {
    const financials = computeFinancials([row({ grossAmount: 1000 })]);
    expect(financials.gross).toBe(1000);
  });

  it("excludes never-captured payments", () => {
    const financials = computeFinancials([
      row({ grossAmount: 1000 }),
      unsettledRow("NOT_CAPTURED", 100, "created"),
    ]);
    expect(financials.gross).toBe(1000);
  });

  it("excludes authorized and failed payments", () => {
    for (const paymentStatus of ["authorized", "failed"]) {
      const financials = computeFinancials([
        row({ grossAmount: 1000 }),
        unsettledRow("NOT_CAPTURED", 250, paymentStatus),
      ]);
      expect(financials.gross).toBe(1000);
    }
  });

  it("excludes payments with an unsupported provider status", () => {
    const financials = computeFinancials([
      row({ grossAmount: 1000 }),
      unsettledRow("UNKNOWN_STATUS", 9999, "disputed"),
    ]);
    expect(financials.gross).toBe(1000);
  });

  it("still counts a payment that is merely awaiting settlement", () => {
    const financials = computeFinancials([
      row({ grossAmount: 1000 }),
      unsettledRow("SETTLEMENT_PENDING", 10000, "captured"),
    ]);
    expect(financials.gross).toBe(11000);
  });

  it("reproduces the reported Overview-vs-Reports mismatch as agreement", () => {
    // The exact shape that previously read 10,200 on Overview and
    // 10,100 in Reports: one EX02, one never-captured, one pending.
    const financials = computeFinancials([
      unsettledRow("EX02", 100, "captured"),
      unsettledRow("NOT_CAPTURED", 100, "created"),
      unsettledRow("SETTLEMENT_PENDING", 10000, "captured"),
    ]);
    expect(financials.gross).toBe(10100);
  });

  it("leaves the settlement gap untouched", () => {
    // Excluding a never-captured row must not disturb expected/observed:
    // it contributes neither, so the gap is unchanged.
    const withoutUncaptured = computeFinancials([row()]);
    const withUncaptured = computeFinancials([
      row(),
      unsettledRow("NOT_CAPTURED", 100, "created"),
    ]);
    expect(withUncaptured.gap).toBe(withoutUncaptured.gap);
    expect(withUncaptured.expected).toBe(withoutUncaptured.expected);
    expect(withUncaptured.observed).toBe(withoutUncaptured.observed);
  });
});
