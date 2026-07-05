import { Hono } from "hono";
import { findSubscriberPageAny } from "../../lib/notion";
import { createMagicToken, isResubscribeEligible } from "../../lib/kv";
import { sendMagicLink } from "../../lib/email";
import { primaryFrontendUrl } from "../../lib/origins";
import { resultPage } from "../../lib/html";
import type { Env } from "../../types";

const app = new Hono<{ Bindings: Env }>();

// POST /auth/resubscribe — self-serve reactivation, reached from the "changed
// your mind?" form on the unsubscribe confirmation page. Anti-enumeration:
// always renders the same confirmation page, and only actually sends an email
// if the address is eligible — i.e. was previously active and deactivated via
// /auth/unsubscribe (marked in KV there). This deliberately excludes accounts
// that are inactive because they're still a pending, unapproved waitlist
// applicant — those must never be able to self-activate.
app.post("/", async (c) => {
  const body = await c.req.parseBody().catch(() => ({}) as Record<string, unknown>);
  const rawEmail = typeof body.email === "string" ? body.email : "";
  const email = rawEmail.toLowerCase().trim();

  if (email && email.includes("@")) {
    c.executionCtx.waitUntil(
      (async () => {
        try {
          const eligible = await isResubscribeEligible(c.env.PORTAL_KV, email);
          if (!eligible) return;

          const page = await findSubscriberPageAny(c.env.NOTION_TOKEN, c.env.SUBSCRIBERS_DB_ID, email);
          if (!page || page.active) return;

          const token = await createMagicToken(c.env.PORTAL_KV, email);
          const url = `${primaryFrontendUrl(c.env)}/auth/verify?token=${token}`;
          await sendMagicLink(c.env.RESEND_API_KEY, email, url);
        } catch (err) {
          console.error("resubscribe error:", err);
        }
      })()
    );
  }

  return c.html(
    resultPage(
      "Check your email",
      "If that address was previously subscribed, we've sent a reactivation link. It stays valid for 30 minutes.",
      true
    )
  );
});

export default app;
