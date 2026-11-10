import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Use the compiler API: this environment returns empty captured CLI config output.
  // Type checking remains enabled; standalone tsc is also part of validation.
  experimental: { useTypeScriptCli: false },
  async rewrites() {
    const api = process.env.PORTFOLIO_API_INTERNAL_URL ?? (process.env.PORTFOLIO_API_INTERNAL_HOSTPORT ? `http://${process.env.PORTFOLIO_API_INTERNAL_HOSTPORT}` : "http://127.0.0.1:8000");
    if (process.env.RENDER === "true") {
      const upstream = new URL(api);
      if (!process.env.PORTFOLIO_API_INTERNAL_URL || upstream.protocol !== "https:" || upstream.username || upstream.password || upstream.pathname !== "/" || upstream.search || upstream.hash || ["localhost", "127.0.0.1", "[::1]"].includes(upstream.hostname)) {
        throw new Error("Render requires PORTFOLIO_API_INTERNAL_URL with the actual API HTTPS origin.");
      }
    }
    return [{ source: "/api/portfolio/:path*", destination: `${api.replace(/\/$/, "")}/api/portfolio/:path*` }];
  },
  cacheComponents: true,
  partialPrefetching: true,
};

export default nextConfig;
