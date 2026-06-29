import { Hono } from "hono";
import { deactivateSubscriber } from "../../lib/notion";
import type { Env } from "../../types";

const app = new Hono<{ Bindings: Env }>();

async function verifyToken(secret: string, email: string, token: string): Promise<boolean> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"]
  );
  // Reconstruct the expected digest from the same message format used by render.py.
  const msgBytes = enc.encode(`unsubscribe|${email}`);
  const sigBytes = await crypto.subtle.sign("HMAC", key, msgBytes);
  const hex = Array.from(new Uint8Array(sigBytes))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 32);
  return hex === token;
}

// GET /auth/unsubscribe?e=<email>&t=<hmac_token>
// One-click unsubscribe — no login required. The HMAC prevents arbitrary
// email enumeration. Returns a self-contained HTML page.
app.get("/", async (c) => {
  const email = (c.req.query("e") ?? "").toLowerCase().trim();
  const token = (c.req.query("t") ?? "").trim();

  if (!email || !token || !c.env.UNSUBSCRIBE_HMAC_SECRET) {
    return c.html(resultPage("Invalid link", "This unsubscribe link is missing required parameters.", false));
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

  return c.html(resultPage("Unsubscribed", "You've been unsubscribed from Bargain Hunter emails. Your account still exists — you can reactivate it at any time by contacting the owner.", true));
});

function resultPage(title: string, message: string, success: boolean): string {
  const colour = success ? "#2e7d32" : "#c62828";
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${title} — Bargain Hunter</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; background: #f5f5f5; display: flex; align-items: center; justify-content: center; min-height: 100vh; }
  .card { background: #fff; border-radius: 8px; padding: 40px 48px; max-width: 480px; box-shadow: 0 1px 4px rgba(0,0,0,.1); text-align: center; }
  .icon { font-size: 48px; margin-bottom: 16px; }
  h1 { margin: 0 0 12px; color: ${colour}; font-size: 22px; }
  p { margin: 0; color: #444; line-height: 1.6; }
</style>
</head>
<body>
<div class="card">
  <div class="icon">${success ? "✅" : "❌"}</div>
  <h1>${title}</h1>
  <p>${message}</p>
</div>
</body>
</html>`;
}

export default app;
