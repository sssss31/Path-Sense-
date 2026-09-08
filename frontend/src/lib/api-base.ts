/** Single source of truth for the API base URL.
 *  1. NEXT_PUBLIC_API_BASE_URL when set (local dev with a custom port, or a separately hosted API);
 *  2. otherwise, on a deployed host, the same-origin "/api/v1" which next.config.ts proxies to the backend
 *     (no CORS, no env vars needed on Vercel);
 *  3. otherwise the local backend. */
export function apiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (configured) return configured;
  if (typeof window !== "undefined" && !["localhost", "127.0.0.1"].includes(window.location.hostname)) return "/api/v1";
  return "http://localhost:8000/api/v1";
}
