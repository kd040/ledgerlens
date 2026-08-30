import { apiGet, apiPost } from "./client";
import type { ApiCurrentUser } from "./types";

export const authApi = {
  login: (email: string, password: string) =>
    apiPost<ApiCurrentUser>("/auth/login", { email, password }),

  logout: () => apiPost<{ status: string }>("/auth/logout"),

  me: () => apiGet<ApiCurrentUser>("/auth/me"),

  /** Always creates an Analyst account -- there is no `role` field to
   * send (see backend/app/auth/router.py's RegisterRequest). */
  register: (email: string, password: string) =>
    apiPost<ApiCurrentUser>("/auth/register", { email, password }),
};
