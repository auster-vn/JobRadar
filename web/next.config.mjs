/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  poweredByHeader: false,
  turbopack: {root: process.cwd()},
  images: {
    remotePatterns: [{protocol: "https", hostname: "itviec.com"}],
  },
  async rewrites() {
    const apiBase = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
    return [
      {source: "/api/:path*", destination: `${apiBase}/api/:path*`},
      {source: "/health/:path*", destination: `${apiBase}/health/:path*`},
      {source: "/version", destination: `${apiBase}/version`},
    ];
  },
};

export default nextConfig;
