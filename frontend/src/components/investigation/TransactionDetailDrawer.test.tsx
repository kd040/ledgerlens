/**
 * Render checks for the transaction detail drawer -- the one surface a
 * judge looks at to tell a live Razorpay payment apart from a
 * deterministic benchmark one, and the place the "Start Investigation"
 * action is offered.
 *
 * The drawer reads from react-query and react-router, so each render is
 * wrapped in both. No network: the queries it makes are only enabled for
 * EX03 rows, and nothing here asserts on them.
 */
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { TransactionDetailDrawer } from "./TransactionDetailDrawer";
import type {
  DataSource,
  ExceptionRecord,
  ReconciliationResult,
} from "../../domain/types";

function makeResult(
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

function makeException(
  overrides: Partial<ExceptionRecord> = {},
): ExceptionRecord {
  return {
    id: "exc-1",
    exceptionCode: "EX02",
    category: "Missing Record",
    description: "No settlement found for payment pay_TESTflow01.",
    financialImpact: 100,
    status: "OPEN",
    createdAt: new Date("2026-08-30T00:00:00.000Z"),
    updatedAt: new Date("2026-08-30T00:00:00.000Z"),
    investigationId: null,
    investigationStatus: null,
    investigationRecommendation: null,
    ...overrides,
  };
}

function renderDrawer(
  result: ReconciliationResult,
  source: DataSource,
  exceptions: [string, ExceptionRecord][] = [],
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <TransactionDetailDrawer
          open
          onClose={() => {}}
          result={result}
          exceptionByPayment={new Map(exceptions)}
          source={source}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** The Drawer ships its own Close control, so "no action offered" has to
 * mean the investigation buttons specifically, not the absence of any
 * button at all. */
function expectNoInvestigationAction() {
  expect(
    screen.queryByRole("button", { name: "Start Investigation" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "View Investigation" }),
  ).not.toBeInTheDocument();
}

describe("payment identity", () => {
  it("renders the real payment date and time, not just the day", () => {
    renderDrawer(
      makeResult({
        payment: "pay_TESTflow01",
        status: "SETTLEMENT_PENDING",
        category: "Settlement Pending",
        expectedAmount: null,
        observedAmount: null,
        difference: null,
        paymentCreatedAt: new Date("2026-08-31T10:08:13.000Z"),
        paymentStatus: "captured",
      }),
      "razorpay_test",
    );

    expect(screen.getByText("Payment date")).toBeInTheDocument();

    // Rendered through the app's shared en-IN formatter, so the assertion
    // is on the formatted output rather than a hand-written string.
    const formatted = new Intl.DateTimeFormat("en-IN", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date("2026-08-31T10:08:13.000Z"));
    expect(screen.getByText(formatted)).toBeInTheDocument();

    // A time component must actually be present -- a bare date would
    // have been the old behaviour.
    expect(formatted).toMatch(/\d/);
    expect(screen.queryByText("2026-08-31")).not.toBeInTheDocument();
  });

  it("names Razorpay Test Mode as the source", () => {
    renderDrawer(
      makeResult({ payment: "pay_TESTflow01", status: "SETTLEMENT_PENDING" }),
      "razorpay_test",
    );

    expect(screen.getByText("Source")).toBeInTheDocument();
    expect(screen.getByText("Razorpay Test Mode")).toBeInTheDocument();
  });

  it("names the Demo Dataset for a deterministic payment", () => {
    renderDrawer(makeResult(), "demo");

    expect(screen.getByText("Demo Dataset")).toBeInTheDocument();
    expect(screen.queryByText("Razorpay Test Mode")).not.toBeInTheDocument();
  });

  it("shows the provider payment status alongside the settlement status", () => {
    renderDrawer(
      makeResult({
        payment: "pay_TESTflow02",
        status: "NOT_CAPTURED",
        category: "Not Captured",
        expectedAmount: null,
        observedAmount: null,
        difference: null,
        paymentStatus: "created",
      }),
      "razorpay_test",
    );

    expect(screen.getByText("Payment status")).toBeInTheDocument();
    expect(screen.getByText("created")).toBeInTheDocument();
    // The settlement outcome is the status badge under the heading.
    expect(screen.getByText("Not Captured")).toBeInTheDocument();
  });

  it("still renders an existing deterministic transaction in full", () => {
    renderDrawer(
      makeResult({ status: "EX01", category: "Amount Mismatch", difference: 50 }),
      "demo",
    );

    expect(screen.getByText("PAY-001")).toBeInTheDocument();
    expect(screen.getByText("Amount Mismatch")).toBeInTheDocument();
    expect(screen.getByText("Demo Dataset")).toBeInTheDocument();
    expect(screen.getByText("Expected")).toBeInTheDocument();
    expect(screen.getByText("Observed")).toBeInTheDocument();
    expect(screen.getByText("Difference")).toBeInTheDocument();
  });
});

describe("investigation action visibility", () => {
  it("offers Start Investigation for a genuine exception with no investigation yet", () => {
    const exception = makeException();
    renderDrawer(
      makeResult({
        payment: "pay_TESTflow01",
        status: "EX02",
        category: "Missing Record",
        expectedAmount: null,
        observedAmount: null,
        difference: null,
      }),
      "razorpay_test",
      [["pay_TESTflow01", exception]],
    );

    expect(
      screen.getByRole("button", { name: "Start Investigation" }),
    ).toBeInTheDocument();
  });

  it("offers View Investigation instead once one already exists", () => {
    const exception = makeException({ investigationId: "inv-1" });
    renderDrawer(
      makeResult({
        payment: "pay_TESTflow01",
        status: "EX02",
        category: "Missing Record",
        expectedAmount: null,
        observedAmount: null,
        difference: null,
      }),
      "razorpay_test",
      [["pay_TESTflow01", exception]],
    );

    expect(
      screen.getByRole("button", { name: "View Investigation" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Start Investigation" }),
    ).not.toBeInTheDocument();
  });

  it("offers no investigation action for normal settlement lag", () => {
    renderDrawer(
      makeResult({
        payment: "pay_TESTflow01",
        status: "SETTLEMENT_PENDING",
        category: "Settlement Pending",
        expectedAmount: null,
        observedAmount: null,
        difference: null,
      }),
      "razorpay_test",
    );

    expectNoInvestigationAction();
    expect(screen.getByText(/normal lag, not a missing record/)).toBeInTheDocument();
  });

  it("offers no investigation action for a payment that was never captured", () => {
    renderDrawer(
      makeResult({
        payment: "pay_TESTflow02",
        status: "NOT_CAPTURED",
        category: "Not Captured",
        expectedAmount: null,
        observedAmount: null,
        difference: null,
        paymentStatus: "created",
      }),
      "razorpay_test",
    );

    expectNoInvestigationAction();
    expect(screen.getByText(/never captured/)).toBeInTheDocument();
  });

  it("offers no investigation action for a reconciled payment", () => {
    renderDrawer(makeResult(), "demo");

    expectNoInvestigationAction();
  });
});
