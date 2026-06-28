import type { Metadata } from 'next'
import { Space_Grotesk } from 'next/font/google'
import './globals.css'

const siteUrl = new URL(process.env.NEXT_PUBLIC_SITE_URL ?? 'https://bargain-hunter.sylvalume.online')
const siteDescription =
  'Automated Australian deal alerts and saving guides, monitoring OzBargain and CamelCamelCamel AU for hot deals, price drops, and personalised watch matches.'

const spaceGrotesk = Space_Grotesk({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-sans',
})

export const metadata: Metadata = {
  metadataBase: siteUrl,
  applicationName: 'Bargain Hunter',
  title: {
    default: 'Bargain Hunter · Australian Deal Alerts',
    template: '%s · Bargain Hunter',
  },
  description: siteDescription,
  keywords: [
    'Bargain Hunter',
    'Australian deals',
    'OzBargain alerts',
    'CamelCamelCamel AU',
    'price drop alerts',
    'cashback stacking',
    'discounted gift cards',
    'saving guides Australia',
  ],
  alternates: {
    canonical: '/',
  },
  icons: {
    icon: [
      { url: '/favicon.ico', sizes: 'any' },
      { url: '/icon.svg', type: 'image/svg+xml' },
    ],
    apple: '/apple-icon.svg',
  },
  manifest: '/manifest.webmanifest',
  openGraph: {
    type: 'website',
    url: '/',
    siteName: 'Bargain Hunter',
    title: 'Bargain Hunter · Australian Deal Alerts',
    description: siteDescription,
    locale: 'en_AU',
    images: [
      {
        url: '/icon.svg',
        width: 512,
        height: 512,
        alt: 'Bargain Hunter discount tag icon',
      },
    ],
  },
  twitter: {
    card: 'summary',
    title: 'Bargain Hunter · Australian Deal Alerts',
    description: siteDescription,
    images: ['/icon.svg'],
  },
}

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const structuredData = {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    name: 'Bargain Hunter',
    url: siteUrl.toString(),
    description: siteDescription,
    inLanguage: 'en-AU',
    potentialAction: {
      '@type': 'ReadAction',
      target: `${siteUrl.toString()}guides`,
    },
  }

  return (
    <html lang="en" className={spaceGrotesk.variable}>
      <body>
        {children}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
        />
      </body>
    </html>
  )
}
