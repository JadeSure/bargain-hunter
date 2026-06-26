import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  webpack(config, { nextRuntime }) {
    if (nextRuntime === 'edge') {
      config.resolve.fallback = {
        ...config.resolve.fallback,
        path: false,
        fs: false,
        process: false,
      }
    }
    return config
  },
}

export default nextConfig
