import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: 'standalone',
  outputFileTracingIncludes: { '/*': ['./app/shell.html'] },
  cacheMaxMemorySize: 0,
};

export default nextConfig;
