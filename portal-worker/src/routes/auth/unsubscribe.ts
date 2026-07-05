import { Hono } from "hono";
import { deactivateSubscriber } from "../../lib/notion";
import { markResubscribeEligible } from "../../lib/kv";
import { resultPage, escapeHtml, escapeAttr } from "../../lib/html";
import type { Env } from "../../types";

const app = new Hono<{ Bindings: Env }>();

// Mirrors feedback-worker/src/index.js's timingSafeEqual — same threat model
// (public HMAC verification endpoint), kept in sync by convention since the
// two workers don't share a package.
function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function verifyToken(secret: string, email: string, token: string): Promise<boolean> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  // Reconstruct the expected digest from the same message format used by render.py.
  const msgBytes = enc.encode(`unsubscribe|${email}`);
  const sigBytes = await crypto.subtle.sign("HMAC", key, msgBytes);
  const hex = Array.from(new Uint8Array(sigBytes))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 32);
  return timingSafeEqual(hex, token);
}

function extractParams(c: { req: { query: (k: string) => string | undefined } }): {
  email: string;
  token: string;
} {
  const email = (c.req.query("e") ?? "").toLowerCase().trim();
  const token = (c.req.query("t") ?? "").trim();
  return { email, token };
}

// GET /auth/unsubscribe?e=<email>&t=<hmac_token>
// Renders a confirmation page with a POST form — does NOT unsubscribe on GET.
// This avoids accidental unsubscribes from mail clients / security scanners
// that prefetch links. The actual deactivation happens on POST (below), which
// is also the endpoint RFC 8058 one-click clients (List-Unsubscribe-Post) hit
// directly with the same query string.
app.get("/", async (c) => {
  const { email, token } = extractParams(c);

  if (!email || !token || !c.env.UNSUBSCRIBE_HMAC_SECRET) {
    return c.html(resultPage("Invalid link", "This unsubscribe link is missing required parameters.", false), 400);
  }

  let valid = false;
  try {
    valid = await verifyToken(c.env.UNSUBSCRIBE_HMAC_SECRET, email, token);
  } catch {
    // fall through to invalid response
  }

  if (!valid) {
    return c.html(resultPage("Invalid link", "This unsubscribe link is invalid or has expired.", false), 400);
  }

  return c.html(confirmPage(email, c.req.url));
});

// POST /auth/unsubscribe?e=<email>&t=<hmac_token>
// Verifies the HMAC and deactivates the subscriber. Hit either by our own
// confirmation form, or directly by mail clients doing an RFC 8058 one-click
// unsubscribe (body "List-Unsubscribe=One-Click", ignored — the token in the
// query string is what authorises the action).
app.post("/", async (c) => {
  const { email, token } = extractParams(c);

  if (!email || !token || !c.env.UNSUBSCRIBE_HMAC_SECRET) {
    return c.html(resultPage("Invalid link", "This unsubscribe link is missing required parameters.", false), 400);
  }

  let valid = false;
  try {
    valid = await verifyToken(c.env.UNSUBSCRIBE_HMAC_SECRET, email, token);
  } catch {
    // fall through to invalid response
  }

  if (!valid) {
    return c.html(resultPage("Invalid link", "This unsubscribe link is invalid or has expired.", false), 400);
  }

  try {
    await deactivateSubscriber(c.env.NOTION_TOKEN, c.env.SUBSCRIBERS_DB_ID, email);
  } catch (err) {
    console.error("unsubscribe deactivate failed:", err);
    return c.html(resultPage("Something went wrong", "We couldn't process your request. Please try again later.", false), 500);
  }

  try {
    await markResubscribeEligible(c.env.PORTAL_KV, email);
  } catch (err) {
    console.error("mark resubscribe-eligible failed:", err);
  }

  const resubscribeForm = `
    <p style="margin-top:20px;">Changed your mind?</p>
    <form method="POST" action="/auth/resubscribe" style="margin-top:8px;">
      <input type="hidden" name="email" value="${escapeAttr(email)}" />
      <button type="submit" style="background:#2e7d32;">Send me a reactivation link</button>
    </form>`;

  return c.html(
    resultPage(
      "Unsubscribed",
      "You've been unsubscribed from Bargain Hunter emails. Your account still exists.",
      true,
      resubscribeForm
    )
  );
});

function confirmPage(email: string, actionUrl: string): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Unsubscribe — Bargain Hunter</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; background: #f5f5f5; display: flex; align-items: center; justify-content: center; min-height: 100vh; }
  .card { background: #fff; border-radius: 8px; padding: 40px 48px; max-width: 480px; box-shadow: 0 1px 4px rgba(0,0,0,.1); text-align: center; }
  h1 { margin: 0 0 12px; color: #111; font-size: 22px; }
  p { margin: 0 0 20px; color: #444; line-height: 1.6; }
  button { background: #c62828; color: #fff; border: none; border-radius: 6px; padding: 11px 24px; font-size: 14px; font-weight: 600; cursor: pointer; }
  button:hover { background: #b71c1c; }
</style>
</head>
<body>
<div class="card">
  <h1>Unsubscribe from Bargain Hunter?</h1>
  <p>${escapeHtml(email)} will stop receiving deal digests. You can be reactivated later if you change your mind.</p>
  <form method="POST" action="${escapeAttr(actionUrl)}">
    <button type="submit">Unsubscribe</button>
  </form>
</div>
</body>
</html>`;
}

export default app;
