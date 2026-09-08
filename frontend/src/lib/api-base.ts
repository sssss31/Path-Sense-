/** Single source of truth for the API base URL.
 *  1. NEXT_PUBLIC_API_BASE_URL when set and usable from the current page (a localhost value is ignored on a deployed host);
 *  2. otherwise, on a deployed host, the same-origin "/api/v1" which next.config.ts proxies to the backend
 *     (no CORS, no env vars needed on Vercel);
 *  3. otherwise the local backend. */
export function apiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL || "";
  const onLocalhost = typeof window === "undefined" || ["localhost", "127.0.0.1"].includes(window.location.hostname);
  const configuredIsLocal = /^https?:\/\/(localhost|127\.0\.0\.1)/.test(configured);
  if (configured && (onLocalhost || !configuredIsLocal)) return configured;
  if (!onLocalhost) return "/api/v1";
  return "http://localhost:8000/api/v1";
}
