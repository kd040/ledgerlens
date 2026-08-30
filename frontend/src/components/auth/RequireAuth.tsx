import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useMe } from "../../api/queries";
import { LoadingState } from "../ui/AsyncState";

/** Gates every route behind AppShell on a valid session. This is a UX
 * convenience only -- the real enforcement is server-side (see
 * app/auth/dependencies.py's router-level get_current_user), so a
 * request this component never sees would still 401 on the backend. */
export function RequireAuth() {
  const me = useMe();
  const location = useLocation();

  if (me.isLoading) {
    return <LoadingState message="Loading…" />;
  }

  if (!me.data) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <Outlet />;
}
