import { NextResponse } from 'next/server'

export const runtime = 'edge'
export const dynamic = 'force-dynamic'

const WORKER = process.env.NEXT_PUBLIC_WORKER_URL ?? ''

// Same-origin proxy for the magic-link verification step.
//
// The browser hits this route on the frontend's own domain. We forward the
// token to the portal worker, then re-emit the worker's Set-Cookie header on
// *this* (frontend) response so the session cookie lands on the frontend's
// domain — the only domain the portal middleware/layout can read it from.
// Free *.pages.dev and *.workers.dev are separate sites that cannot share a
// cookie, so the worker cannot set it on the frontend directly.
export async function GET(req: Request) {
  const reqUrl = new URL(req.url)
  const token = reqUrl.searchParams.get('token') ?? ''

  let upstream: Response
  try {
    upstream = await fetch(`${WORKER}/auth/magic-link/verify?token=${encodeURIComponent(token)}`, {
      redirect: 'manual',
    })
  } catch {
    return NextResponse.redirect(new URL('/login?error=server', reqUrl.origin))
  }

  const setCookie = upstream.headers.get('set-cookie')
  const upstreamLocation = upstream.headers.get('location')

  // Reissue the worker's redirect on our own origin so the session cookie set
  // below is sent on the follow-up navigation. Default to /portal on success
  // (cookie present) or the login page on failure.
  let target = setCookie ? '/portal' : '/login?error=invalid'
  if (upstreamLocation) {
    try {
      const u = new URL(upstreamLocation, reqUrl.origin)
      target = `${u.pathname}${u.search}`
    } catch {
      // keep default target
    }
  }

  const res = NextResponse.redirect(new URL(target, reqUrl.origin))
  if (setCookie) res.headers.append('set-cookie', setCookie)
  return res
}
