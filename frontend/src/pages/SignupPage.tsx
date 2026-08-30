import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useMe, useRegister } from "../api/queries";
import { ApiError } from "../api/client";

const MIN_PASSWORD_LENGTH = 8;

/** The one other unauthenticated route, alongside /login. Always creates
 * an Analyst account (see backend/app/auth/router.py) -- there is no
 * role selector here because there is nothing on the backend for one to
 * control. Does not auto-login: redirects to /login on success so the
 * existing session/cookie flow stays the single place a session is
 * created. */
export function SignupPage() {
  const me = useMe();
  const register = useRegister();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  if (me.data) {
    return <Navigate to="/overview" replace />;
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setValidationError(null);

    if (password.length < MIN_PASSWORD_LENGTH) {
      setValidationError(
        `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`,
      );
      return;
    }
    if (password !== confirmPassword) {
      setValidationError("Passwords do not match.");
      return;
    }

    register.mutate(
      { email, password },
      {
        onSuccess: () =>
          navigate("/login", {
            replace: true,
            state: { signupSuccess: true },
          }),
      },
    );
  }

  const errorMessage =
    validationError ??
    (register.error instanceof ApiError
      ? register.error.message
      : register.isError
        ? "Could not create account. Try again."
        : null);

  return (
    <div className="flex min-h-screen items-center justify-center bg-navy px-4">
      <div className="w-full max-w-sm rounded-lg border border-navy-border bg-surface p-8 shadow-xl">
        <div className="mb-8 text-center">
          <div className="font-mono text-lg font-medium tracking-tight text-ink">
            Ledger<span className="text-accent">Lens</span>
          </div>
          <p className="mt-2 text-sm text-ink-muted">
            Create your LedgerLens account
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
              autoComplete="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-accent"
            />
          </label>

          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-ink">Confirm password</span>
            <input
              type="password"
              required
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-accent"
            />
          </label>

          {errorMessage && (
            <p className="text-sm text-danger">{errorMessage}</p>
          )}

          <button
            type="submit"
            disabled={register.isPending}
            className="mt-2 rounded-md bg-accent px-3.5 py-2.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            {register.isPending ? "Creating account…" : "Create Account"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-ink-muted">
          Already have an account?{" "}
          <Link to="/login" className="font-medium text-accent hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
