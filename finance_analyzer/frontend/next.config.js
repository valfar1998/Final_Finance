/** @type {import('next').NextConfig} */
const path = require("path");

const nextConfig = {
  reactStrictMode: true,
  // Evita che Next.js usi C:\Users\Valerio come root (lockfile fuori progetto)
  outputFileTracingRoot: path.join(__dirname),
  // Metadata statici in <head> invece del div hidden+Suspense (fix hydration dev)
  htmlLimitedBots: /.*/,
};

module.exports = nextConfig;
