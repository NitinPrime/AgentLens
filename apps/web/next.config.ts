import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Only for Docker (`OUTPUT_STANDALONE=1`). Leaving this on breaks Vercel on
  // Next.js 16.3+ (ENOENT next-server.js.nft.json).
  ...(process.env.OUTPUT_STANDALONE === "1" ? { output: "standalone" as const } : {}),
};

export default nextConfig;
