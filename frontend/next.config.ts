import type { NextConfig } from "next";

// Deployed frontends proxy /api/v1/* to the backend, so no CORS or public env var is needed.
// Override the target with API_PROXY_TARGET (server-side env var) when the backend lives elsewhere.
const API_PROXY_TARGET = process.env.API_PROXY_TARGET || "https://path-sense.onrender.com";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${API_PROXY_TARGET}/api/v1/:path*` }];
  },
};
export default nextConfig;
