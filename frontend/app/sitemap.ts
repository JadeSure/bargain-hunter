import type { MetadataRoute } from 'next'
import { getGuides } from '@/lib/guides'

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? 'https://bargainhunter.app'

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const guides = await getGuides()
  const now = new Date()

  return [
    {
      url: siteUrl,
      lastModified: now,
      changeFrequency: 'daily',
      priority: 1,
    },
    {
      url: `${siteUrl}/guides`,
      lastModified: now,
      changeFrequency: 'daily',
      priority: 0.8,
    },
    ...guides.map((guide) => ({
      url: `${siteUrl}/guides/${guide.id}`,
      lastModified: guide.generated_at ? new Date(guide.generated_at) : now,
      changeFrequency: 'weekly' as const,
      priority: 0.7,
    })),
  ]
}
