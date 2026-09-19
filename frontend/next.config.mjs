/** @type {import('next').NextConfig} */
const nextConfig = {
  async redirects() {
    return process.env.APP_MODE === "lti"
      ? [{ source: "/", destination: "/portal", permanent: false }]
      : [];
  },
  async rewrites() {
    return [
      {
        source: "/lti/:path*",
        destination: `${process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000"}/lti/:path*`,
      },
      {
        source: "/api-proxy/:path*",
        destination: `${process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000"}/:path*`,
      },
    ];
  },
  // Allow bounded course imports and LLM requests to finish through the proxy.
  httpAgentOptions: {
    keepAlive: true,
  },
  experimental: {
    proxyTimeout: 300000,
  },
};

export default nextConfig;
