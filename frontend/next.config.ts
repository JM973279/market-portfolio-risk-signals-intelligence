import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Use the compiler API: this environment returns empty captured CLI config output.
  // Type checking remains enabled; standalone tsc is also part of validation.
  experimental: { useTypeScriptCli: false },
  async rewrites() {
    // mqs 포트폴리오 서버(python3 -m qsignals.portfolio_server, 기본 3108). 다른 주소면 환경변수로 지정한다.
    const api = process.env.PORTFOLIO_API_INTERNAL_URL ?? (process.env.PORTFOLIO_API_INTERNAL_HOSTPORT ? `http://${process.env.PORTFOLIO_API_INTERNAL_HOSTPORT}` : "http://127.0.0.1:3108");
    if (process.env.RENDER === "true") {
      const upstream = new URL(api);
      if (!process.env.PORTFOLIO_API_INTERNAL_URL || upstream.protocol !== "https:" || upstream.username || upstream.password || upstream.pathname !== "/" || upstream.search || upstream.hash || ["localhost", "127.0.0.1", "[::1]"].includes(upstream.hostname)) {
        throw new Error("Render requires PORTFOLIO_API_INTERNAL_URL with the actual API HTTPS origin.");
      }
    }
    const base = api.replace(/\/$/, "");
    // Both markets use the deployed API. An explicit Korea server remains optional.
    const krBase = process.env.PORTFOLIO_KR_API_INTERNAL_URL?.replace(/\/$/, "");
    return [
      { source: "/api/portfolio/:path*", destination: `${base}/api/portfolio/:path*` },
      // mqs 포트폴리오 화면과 그 정적 파일 (iframe으로 사이트 안에 표시)
      { source: "/portfolio-lab", destination: `${base}/portfolio` },
      { source: "/portfolio/:file(app.js|style.css)", destination: `${base}/portfolio/:file` },
      { source: "/api/portfolio-kr/:path*", destination: krBase ? `${krBase}/api/portfolio/:path*` : `${base}/api/portfolio-kr/:path*` },
      { source: "/portfolio-kr-lab", destination: krBase ? `${krBase}/portfolio` : `${base}/portfolio-kr` },
    ];
  },
  cacheComponents: true,
  partialPrefetching: true,
};

export default nextConfig;
