/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  poweredByHeader: false,
  turbopack: {root: process.cwd()},
  images: {
    remotePatterns: [{protocol: "https", hostname: "itviec.com"}],
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {key: "X-Content-Type-Options", value: "nosniff"},
          {key: "Referrer-Policy", value: "strict-origin-when-cross-origin"},
          {key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()"},
        ],
      },
    ];
  },
  async rewrites() {
    const apiBase = (
      process.env.API_INTERNAL_URL ??
      process.env.NEXT_PUBLIC_API_URL ??
      "http://localhost:8000"
    ).replace(/\/$/, "");
    return [
      {source: "/api/:path*", destination: `${apiBase}/api/:path*`},
      {source: "/health/:path*", destination: `${apiBase}/health/:path*`},
      {source: "/version", destination: `${apiBase}/version`},
    ];
  },
};

export default nextConfig;
