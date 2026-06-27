import type { NextRequest } from 'next/server'

export const runtime = 'edge'
export const dynamic = 'force-dynamic'

const WORKER = process.env.NEXT_PUBLIC_WORKER_URL ?? ''

// Same-origin proxy for authenticated portal API calls (e.g. PUT /api/me).
//
// Client-side fetches hit this route on the frontend's own domain, so the
// browser automatically attaches the session cookie. We forward that cookie to
// the portal worker (which authorises via the `session` cookie) and stream the
// response back. This is required because the worker lives on a separate
// *.workers.dev site whose cookies the browser will not send from *.pages.dev.
async function proxy(req: NextRequest, path: string[]): Promise<Response> {
  const reqUrl = new URL(req.url)
  const target = `${WORKER}/api/${path.join('/')}${reqUrl.search}`

  const headers = new Headers()
  const cookie = req.headers.get('cookie')
  if (cookie) headers.set('cookie', cookie)
  const contentType = req.headers.get('content-type')
  if (contentType) headers.set('content-type', contentType)

  const init: RequestInit = { method: req.method, headers, redirect: 'manual' }
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    init.body = await req.text()
  }

  let upstream: Response
  try {
    upstream = await fetch(target, init)
  } catch {
    return new Response(JSON.stringify({ error: 'Upstream unavailable' }), {
      status: 502,
      headers: { 'content-type': 'application/json' },
    })
  }

  const resHeaders = new Headers()
  const upstreamContentType = upstream.headers.get('content-type')
  if (upstreamContentType) resHeaders.set('content-type', upstreamContentType)
  const setCookie = upstream.headers.get('set-cookie')
  if (setCookie) resHeaders.append('set-cookie', setCookie)

  return new Response(upstream.body, { status: upstream.status, headers: resHeaders })
}

type Ctx = { params: Promise<{ path: string[] }> }

export async function GET(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path)
}
export async function PUT(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path)
}
export async function POST(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path)
}
export async function DELETE(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path)
}
