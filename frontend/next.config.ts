import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  allowedDevOrigins: ["localhost", "127.0.0.1", "10.29.81.210", "10.*.*.*", "192.168.*.*"],
};

export default nextConfig;
