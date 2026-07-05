import { Hono } from "hono";
import { sendAccessRequest, sendActivationEmail, sendApplicantConfirmation } from "../../lib/email";
import { addToWaitlist, listWaitlist, createInactiveSubscriber } from "../../lib/notion";
import { approveApplicant, rejectApplicant } from "../../lib/waitlist";
import { requireAuth, requireOwner } from "../../middleware/auth";
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
          `${primaryFrontendUrl(c.env)}/portal/admin`
        );
      } catch (err) {
        console.error("request-access email failed:", err);
      }

      try {
        await sendApplicantConfirmation(
          c.env.RESEND_API_KEY,
          email,
          `${primaryFrontendUrl(c.env)}/deals`,
          `${primaryFrontendUrl(c.env)}/guides`
        );
      } catch (err) {
        console.error("applicant confirmation email failed:", err);
      }
    })()
  );

  return c.json({ ok: true });
});

// GET /auth/request-access — owner-only: inspect the waitlist.
app.get("/", requireAuth, requireOwner, async (c) => {
  if (!c.env.WAITLIST_DB_ID) {
    return c.json({ count: 0, waitlist: [] });
  }
  const waitlist = await listWaitlist(c.env.NOTION_TOKEN, c.env.WAITLIST_DB_ID);
  return c.json({ count: waitlist.length, waitlist });
});

// POST /auth/request-access/approve — owner-only: activate a subscriber,
// mark the waitlist row approved, and send a magic-link welcome email.
app.post("/approve", requireAuth, requireOwner, async (c) => {
  const body = await c.req.json<{ email?: string }>().catch(() => ({ email: "" }));
  const email = (body.email ?? "").toLowerCase().trim();
  if (!email || !email.includes("@")) {
    return c.json({ error: "Invalid email" }, 400);
  }

  const result = await approveApplicant(c.env, email);
  if (!result.ok) {
    return c.json({ error: "Subscriber not found" }, 404);
  }

  c.executionCtx.waitUntil(
    sendActivationEmail(c.env.RESEND_API_KEY, email, result.magicLinkUrl).catch((err) =>
      console.error("activation email failed:", err)
    )
  );

  return c.json({ ok: true, email });
});

// POST /auth/request-access/reject — owner-only: mark the waitlist row
// rejected. Silent — rejected applicants get no email.
app.post("/reject", requireAuth, requireOwner, async (c) => {
  const body = await c.req.json<{ email?: string }>().catch(() => ({ email: "" }));
  const email = (body.email ?? "").toLowerCase().trim();
  if (!email || !email.includes("@")) {
    return c.json({ error: "Invalid email" }, 400);
  }

  await rejectApplicant(c.env, email);
  return c.json({ ok: true, email });
});

export default app;
