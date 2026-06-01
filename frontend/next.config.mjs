/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api-proxy/:path*",
        destination: `${process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000"}/:path*`,
      },
    ];
  },
  // Increase proxy timeout to 90s for slow Canvas API responses
  httpAgentOptions: {
    keepAlive: true,
  },
  experimental: {
    proxyTimeout: 90000,
  },
};

export default nextConfig;
