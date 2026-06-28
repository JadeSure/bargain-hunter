import { Hono } from "hono";
import { sendAccessRequest } from "../../lib/email";
import { addToWaitlist, listWaitlist } from "../../lib/notion";
import { requireAuth } from "../../middleware/auth";
import { primaryFrontendUrl } from "../../lib/origins";
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

  // Durable source of truth: persist first so a request is never lost, even if
  // the notification email later fails. Errors are swallowed (still return ok)
  // to avoid leaking state, but are logged for observability.
  try {
    if (c.env.WAITLIST_DB_ID) {
      await addToWaitlist(c.env.NOTION_TOKEN, c.env.WAITLIST_DB_ID, email, "modal");
    } else {
      console.warn("WAITLIST_DB_ID not set — skipping waitlist persistence");
    }
  } catch (err) {
    console.error("waitlist persist failed:", err);
  }

  // Best-effort owner notification — fire-and-forget.
  c.executionCtx.waitUntil(
    sendAccessRequest(
      c.env.RESEND_API_KEY,
      c.env.OWNER_EMAIL,
      email,
      `${primaryFrontendUrl(c.env)}/login`
    ).catch((err) => console.error("request-access email failed:", err))
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

export default app;
