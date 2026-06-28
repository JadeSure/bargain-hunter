import type { MetadataRoute } from 'next'

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? 'https://bargain-hunter.sylvalume.online'

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        disallow: ['/login', '/portal'],
      },
    ],
    sitemap: `${siteUrl}/sitemap.xml`,
  }
}
