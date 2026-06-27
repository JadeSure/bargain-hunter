import type { Env } from "../types";

// FRONTEND_URL holds a comma-separated list of allowed frontend origins
// (e.g. the custom domain plus the *.pages.dev fallback). The full list is
// used for CORS; the first entry is the canonical origin for redirects.

export function allowedOrigins(env: Env): string[] {
  return (env.FRONTEND_URL ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export function primaryFrontendUrl(env: Env): string {
  return allowedOrigins(env)[0] ?? "";
}
