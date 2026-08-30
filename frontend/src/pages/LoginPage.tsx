import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useLogin, useMe } from "../api/queries";
import { ApiError } from "../api/client";

const DEMO_ACCOUNTS = [
  { role: "Analyst", email: "analyst@ledgerlens.dev" },
  { role: "Reviewer", email: "reviewer@ledgerlens.dev" },
];

/** The one unauthenticated route. A real login screen, not a stub --
 * POSTs to /auth/login and relies on the server to set the session
 * cookie (see backend/app/auth/router.py); this component never
 * touches a token itself. */
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
    <div className="flex min-h-screen items-center justify-center bg-navy px-4">
      <div className="w-full max-w-sm rounded-lg border border-navy-border bg-surface p-8 shadow-xl">
        <div className="mb-8 text-center">
          <div className="font-mono text-lg font-medium tracking-tight text-ink">
            Ledger<span className="text-accent">Lens</span>
          </div>
          <p className="mt-2 text-sm text-ink-muted">
            Financial Reconciliation
            <br />
            &amp; Investigation
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
          <Link to="/signup" className="font-medium text-accent hover:underline">
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
  );
}
