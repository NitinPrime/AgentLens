import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone is for Docker / self-hosting. On Vercel it breaks Next 16.3+
  // (ENOENT next-server.js.nft.json) because the platform adapter skips that file.
  output: process.env.VERCEL ? undefined : "standalone",
};

export default nextConfig;
