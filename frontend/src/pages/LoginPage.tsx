import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import {
  GitCompareArrows,
  SearchCheck,
  UserCheck,
  type LucideIcon,
} from "lucide-react";
import { useLogin, useMe } from "../api/queries";
import { ApiError } from "../api/client";

const DEMO_ACCOUNTS = [
  { role: "Analyst", email: "analyst@ledgerlens.dev" },
  { role: "Reviewer", email: "reviewer@ledgerlens.dev" },
];

/** The three capability items, icon-matched to the nav destinations they
 * correspond to once signed in (Reconciliation, Investigations, and the
 * reviewer-owned resolution step) so the intro previews the real product
 * rather than inventing a separate marketing vocabulary. */
const CAPABILITIES: { label: string; body: string; icon: LucideIcon }[] = [
  {
    label: "Detect",
    body: "Find discrepancies across payment, settlement, and bank records.",
    icon: GitCompareArrows,
  },
  {
    label: "Investigate",
    body: "Use AI to analyze financial evidence and identify likely causes.",
    icon: SearchCheck,
  },
  {
    label: "Decide",
    body: "Keep final financial decisions with human reviewers.",
    icon: UserCheck,
  },
];

const WORKFLOW = ["Detect", "Investigate", "Explain", "Decide", "Audit"];

function CapabilityList() {
  return (
    <ul className="flex flex-col gap-5 sm:gap-6">
      {CAPABILITIES.map(({ label, body, icon: Icon }) => (
        <li key={label} className="flex gap-3.5">
          <Icon
            size={18}
            strokeWidth={2}
            aria-hidden="true"
            className="mt-0.5 shrink-0 text-navy-ink"
          />
          <div>
            <div className="font-mono text-[11px] font-medium uppercase tracking-wider text-white">
              {label}
            </div>
            <p className="mt-1 text-sm leading-relaxed text-navy-ink">{body}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

function WorkflowStrip() {
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[11px] font-medium uppercase tracking-wider text-navy-ink/75">
      {WORKFLOW.map((step, index) => (
        <span key={step} className="flex items-center gap-2">
          {index > 0 && (
            <span aria-hidden="true" className="text-navy-ink/40">
              &rarr;
            </span>
          )}
          {step}
        </span>
      ))}
    </div>
  );
}

/** The one unauthenticated route. A real login screen, not a stub --
 * POSTs to /auth/login and relies on the server to set the session
 * cookie (see backend/app/auth/router.py); this component never
 * touches a token itself.
 *
 * The product introduction alongside the form is presentational only. It
 * is split into two sections (brand/headline, then capabilities) rather
 * than one block so the page can order itself differently per breakpoint:
 * on desktop both sit in the left grid column, but on mobile the form is
 * placed between them, keeping the sign-in button reachable without
 * scrolling past the whole introduction. */
export function LoginPage() {
  const me = useMe();
  const login = useLogin();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const signupSuccess = Boolean(
    (location.state as { signupSuccess?: boolean } | null)?.signupSuccess,
  );

  if (me.data) {
    const redirectTo =
      (location.state as { from?: string } | null)?.from ?? "/overview";
    return <Navigate to={redirectTo} replace />;
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    login.mutate(
      { email, password },
      {
        onSuccess: () => navigate("/overview", { replace: true }),
      },
    );
  }

  const errorMessage =
    login.error instanceof ApiError
      ? login.error.message
      : login.isError
        ? "Could not sign in. Try again."
        : null;

  return (
    <div className="min-h-screen bg-navy px-6 py-8 sm:px-8 sm:py-12 lg:grid lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)] lg:content-center lg:gap-x-14 lg:px-12 lg:py-14 xl:gap-x-20 xl:px-20">
      {/* Brand + positioning. First on every breakpoint. */}
      <section className="lg:col-start-1 lg:row-start-1 lg:max-w-xl">
        <div className="font-mono text-sm font-medium tracking-tight text-white sm:text-base">
          Ledger<span className="text-navy-ink">Lens</span>
        </div>
        <h1 className="mt-5 text-2xl font-semibold leading-[1.15] tracking-tight text-white sm:mt-6 sm:text-3xl lg:mt-8 lg:text-[2.6rem]">
          Financial reconciliation that explains the why.
        </h1>
        <p className="mt-4 max-w-xl text-sm leading-relaxed text-navy-ink lg:mt-5 lg:text-base">
          LedgerLens detects reconciliation exceptions, investigates them using
          financial evidence, and helps finance teams resolve discrepancies with
          human oversight.
        </p>
      </section>

      {/* Authentication. The primary action -- right column on desktop,
          directly under the headline on mobile. */}
      <div className="mt-8 lg:col-start-2 lg:row-span-2 lg:row-start-1 lg:mt-0 lg:self-center lg:justify-self-end">
        <div className="mx-auto w-full max-w-sm rounded-lg border border-navy-border bg-surface p-8 shadow-xl">
          <div className="mb-6">
            <h2 className="font-mono text-base font-medium tracking-tight text-ink">
              Sign in
            </h2>
            <p className="mt-1.5 text-sm text-ink-muted">
              Use your LedgerLens account to continue.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="font-medium text-ink">Email</span>
              <input
                type="email"
                required
                autoFocus
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-accent"
              />
            </label>

            <label className="flex flex-col gap-1.5 text-sm">
              <span className="font-medium text-ink">Password</span>
              <input
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-accent"
              />
            </label>

            {signupSuccess && !errorMessage && (
              <p className="text-sm text-accent">
                Account created. You can now sign in.
              </p>
            )}

            {errorMessage && (
              <p className="text-sm text-danger">{errorMessage}</p>
            )}

            <button
              type="submit"
              disabled={login.isPending}
              className="mt-2 rounded-md bg-accent px-3.5 py-2.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
            >
              {login.isPending ? "Signing in…" : "Sign In"}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-ink-muted">
            Don&apos;t have an account?{" "}
            <Link
              to="/signup"
              className="font-medium text-accent hover:underline"
            >
              Sign up
            </Link>
          </p>

          <div className="mt-6 border-t border-border pt-4">
            <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
              Demo access
            </p>
            <ul className="mt-2 flex flex-col gap-1 text-sm text-ink-muted">
              {DEMO_ACCOUNTS.map((account) => (
                <li key={account.email}>
                  <span className="font-medium text-ink">{account.role}:</span>{" "}
                  {account.email}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      {/* Capabilities + workflow. Below the form on mobile, below the
          headline in the left column on desktop. */}
      <section className="mt-10 border-t border-navy-border pt-8 lg:col-start-1 lg:row-start-2 lg:mt-10 lg:max-w-xl lg:pt-9">
        <CapabilityList />
        <div className="mt-8">
          <WorkflowStrip />
          <p className="mt-4 text-xs text-navy-ink/60">
            AI-assisted investigation · Human-authorized resolution
          </p>
        </div>
      </section>
    </div>
  );
}
