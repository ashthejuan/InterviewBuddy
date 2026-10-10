import type { NextConfig } from "next";
import { loadEnvConfig } from "@next/env";
import path from "node:path";

// Monorepo: secrets live in repo-root `.env`; Next only auto-loads `frontend/`.
loadEnvConfig(path.join(__dirname, ".."));
loadEnvConfig(__dirname);

const nextConfig: NextConfig = {
  /* config options here */
};

export default nextConfig;
