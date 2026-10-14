/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // pnpm standalone tracing needs symlink privileges on Windows.
  // Local Windows builds run with `next start`; Linux/Docker keeps standalone.
  output: process.platform === "win32" ? undefined : "standalone",
};

export default nextConfig;
