import { Hono } from "hono";
import { sendAccessRequest, sendActivationEmail } from "../../lib/email";
import { addToWaitlist, listWaitlist, createInactiveSubscriber, activateSubscriber } from "../../lib/notion";
import { requireAuth } from "../../middleware/auth";
import { primaryFrontendUrl } from "../../lib/origins";
import { createMagicToken } from "../../lib/kv";
import type { Env, SessionData } from "../../types";

type Variables = { user: SessionData };

const app = new Hono<{ Bindings: Env; Variables: Variables }>();

// POST /auth/request-access — persist the applicant to the Notion waitlist DB,
// then notify the owner. Always returns 200 so we don't leak whether the email
// is already known (anti-enumeration).
app.post("/", async (c) => {
  const body = await c.req
    .json<{ email?: string }>()
    .catch(() => ({ email: "" }));
  const email = (body.email ?? "").toLowerCase().trim();

  if (!email || !email.includes("@")) {
    return c.json({ error: "Invalid email" }, 400);
  }

  // Persist to waitlist and create an inactive subscriber entry. Both are
  // best-effort — errors are logged but never surfaced to the caller (anti-enumeration).
  c.executionCtx.waitUntil(
    (async () => {
      try {
        if (c.env.WAITLIST_DB_ID) {
          await addToWaitlist(c.env.NOTION_TOKEN, c.env.WAITLIST_DB_ID, email, "modal");
        } else {
          console.warn("WAITLIST_DB_ID not set — skipping waitlist persistence");
        }
      } catch (err) {
        console.error("waitlist persist failed:", err);
      }

      try {
        if (c.env.SUBSCRIBERS_DB_ID) {
          await createInactiveSubscriber(c.env.NOTION_TOKEN, c.env.SUBSCRIBERS_DB_ID, email);
        }
      } catch (err) {
        console.error("inactive subscriber create failed:", err);
      }

      try {
        await sendAccessRequest(
          c.env.RESEND_API_KEY,
          c.env.OWNER_EMAIL,
          email,
          `${primaryFrontendUrl(c.env)}/login`
        );
      } catch (err) {
        console.error("request-access email failed:", err);
      }
    })()
  );

  return c.json({ ok: true });
});

// GET /auth/request-access — owner-only: inspect the waitlist.
app.get("/", requireAuth, async (c) => {
  const user = c.get("user");
  const owner = c.env.OWNER_EMAIL?.toLowerCase().trim();
  if (!owner || user.email.toLowerCase().trim() !== owner) {
    return c.json({ error: "Forbidden" }, 403);
  }
  if (!c.env.WAITLIST_DB_ID) {
    return c.json({ count: 0, waitlist: [] });
  }
  const waitlist = await listWaitlist(c.env.NOTION_TOKEN, c.env.WAITLIST_DB_ID);
  return c.json({ count: waitlist.length, waitlist });
});

// POST /auth/request-access/approve — owner-only: activate a subscriber and
// send them a magic-link welcome email.
app.post("/approve", requireAuth, async (c) => {
  const user = c.get("user");
  const owner = c.env.OWNER_EMAIL?.toLowerCase().trim();
  if (!owner || user.email.toLowerCase().trim() !== owner) {
    return c.json({ error: "Forbidden" }, 403);
  }

  const body = await c.req.json<{ email?: string }>().catch(() => ({ email: "" }));
  const email = (body.email ?? "").toLowerCase().trim();
  if (!email || !email.includes("@")) {
    return c.json({ error: "Invalid email" }, 400);
  }

  const activated = await activateSubscriber(c.env.NOTION_TOKEN, c.env.SUBSCRIBERS_DB_ID, email);
  if (!activated) {
    return c.json({ error: "Subscriber not found" }, 404);
  }

  // Generate a magic link and email it to the newly activated user.
  const token = await createMagicToken(c.env.PORTAL_KV, email);
  const magicLinkUrl = `${primaryFrontendUrl(c.env)}/auth/verify?token=${token}`;

  c.executionCtx.waitUntil(
    sendActivationEmail(c.env.RESEND_API_KEY, email, magicLinkUrl).catch((err) =>
      console.error("activation email failed:", err)
    )
  );

  return c.json({ ok: true, email });
});

export default app;
