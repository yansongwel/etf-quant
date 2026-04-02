import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8000/api/:path*",
      },
      {
        source: "/health",
        destination: "http://127.0.0.1:8000/health",
      },
      {
        source: "/etf/:path*",
        destination: "http://127.0.0.1:8000/etf/:path*",
      },
      {
        source: "/market/:path*",
        destination: "http://127.0.0.1:8000/market/:path*",
      },
    ];
  },
};

export default nextConfig;
