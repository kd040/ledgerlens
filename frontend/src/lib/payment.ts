/**
 * The exception `description` field is real backend-generated text (see
 * backend/app/reconciliation/engine.py) that always embeds the payment
 * reference, e.g. "Payment PAY-005 expected ...". Extracting it here
 * mirrors the same parsing the backend's own investigation runner does
 * (_extract_payment_reference) -- one shared implementation, not
 * duplicated per component.
 */
export function extractPaymentReference(description: string): string | null {
  const match = description.match(/PAY-\d+|pay_[A-Za-z0-9]+/);
  return match ? match[0] : null;
}

/** For a "Duplicate Record" exception, pulls the settlement count out of
 * "Payment PAY-004 has 2 matching settlements." Real backend-computed
 * data rendered as a sentence -- this just reads the number back out. */
export function extractDuplicateSettlementCount(
  description: string,
): number | null {
  const match = description.match(/has (\d+) matching settlements/);
  return match ? Number(match[1]) : null;
}
