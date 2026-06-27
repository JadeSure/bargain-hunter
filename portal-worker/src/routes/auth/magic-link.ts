import { Hono } from "hono";
import { setCookie } from "hono/cookie";
import { findSubscriberByEmail } from "../../lib/notion";
import { createMagicToken, consumeMagicToken, createSession } from "../../lib/kv";
import { sendMagicLink } from "../../lib/email";
import { primaryFrontendUrl } from "../../lib/origins";
import type { Env } from "../../types";

const app = new Hono<{ Bindings: Env }>();

// POST /auth/magic-link — request a login email
app.post("/", async (c) => {
  const { email } = await c.req.json<{ email: string }>();

  if (!email || !email.includes("@")) {
    return c.json({ error: "Invalid email" }, 400);
  }

  // Always return 200 regardless of whether the email is registered (prevent enumeration).
  // Fire-and-forget: if the subscriber isn't found, no email is sent.
  c.executionCtx.waitUntil(
    (async () => {
      try {
        const found = await findSubscriberByEmail(
          c.env.NOTION_TOKEN,
          c.env.SUBSCRIBERS_DB_ID,
          email.toLowerCase().trim()
        );
        if (!found) return;

        const token = await createMagicToken(c.env.PORTAL_KV, email.toLowerCase().trim());
        const url = `${c.env.WORKER_URL}/auth/verify?token=${token}`;
        await sendMagicLink(c.env.RESEND_API_KEY, email, url);
      } catch (err) {
        console.error("magic-link error:", err);
      }
    })()
  );

  return c.json({ ok: true });
});

// GET /auth/verify?token=xxx — validate token, create session, redirect to portal
app.get("/verify", async (c) => {
  const frontend = primaryFrontendUrl(c.env);
  const token = c.req.query("token");
  if (!token) return c.redirect(`${frontend}/login?error=invalid`);

  const email = await consumeMagicToken(c.env.PORTAL_KV, token);
  if (!email) return c.redirect(`${frontend}/login?error=expired`);

  const found = await findSubscriberByEmail(
    c.env.NOTION_TOKEN,
    c.env.SUBSCRIBERS_DB_ID,
    email
  );
  if (!found) return c.redirect(`${frontend}/login?error=not_found`);

  const sessionId = await createSession(c.env.PORTAL_KV, {
    email: found.subscriber.email,
    name: found.subscriber.name,
    notionPageId: found.pageId,
  });

  setCookie(c, "session", sessionId, {
    httpOnly: true,
    secure: true,
    sameSite: "Lax",
    maxAge: 60 * 60 * 24 * 7,
    path: "/",
  });

  return c.redirect(`${frontend}/portal`);
});

export default app;
