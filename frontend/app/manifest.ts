import type { MetadataRoute } from 'next'

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'Bargain Hunter',
    short_name: 'Bargain Hunter',
    description: 'Australian deal alerts and practical saving guides.',
    start_url: '/',
    display: 'standalone',
    background_color: '#101827',
    theme_color: '#101827',
    icons: [
      {
        src: '/icon.svg',
        sizes: 'any',
        type: 'image/svg+xml',
        purpose: 'any',
      },
      {
        src: '/icon.svg',
        sizes: 'any',
        type: 'image/svg+xml',
        purpose: 'maskable',
      },
    ],
  }
}
