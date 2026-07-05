import { Hono } from "hono";
import { requireAuth, requireOwner } from "../middleware/auth";
import { listWaitlist } from "../lib/notion";
import { approveApplicant, rejectApplicant } from "../lib/waitlist";
import { sendActivationEmail } from "../lib/email";
import type { Env, SessionData } from "../types";

type Variables = { user: SessionData };

// Mounted at /api/admin, so it's reachable through the frontend's same-origin
// [...path] proxy (which only forwards /api/*) — see frontend/app/api/[...path]/route.ts.
const app = new Hono<{ Bindings: Env; Variables: Variables }>();

app.use("/*", requireAuth, requireOwner);

// GET /api/admin/waitlist — pending access requests.
app.get("/waitlist", async (c) => {
  if (!c.env.WAITLIST_DB_ID) {
    return c.json({ count: 0, waitlist: [] });
  }
  const waitlist = await listWaitlist(c.env.NOTION_TOKEN, c.env.WAITLIST_DB_ID, "pending");
  return c.json({ count: waitlist.length, waitlist });
});

// POST /api/admin/waitlist/approve { email }
app.post("/waitlist/approve", async (c) => {
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

// POST /api/admin/waitlist/reject { email }
app.post("/waitlist/reject", async (c) => {
  const body = await c.req.json<{ email?: string }>().catch(() => ({ email: "" }));
  const email = (body.email ?? "").toLowerCase().trim();
  if (!email || !email.includes("@")) {
    return c.json({ error: "Invalid email" }, 400);
  }

  await rejectApplicant(c.env, email);
  return c.json({ ok: true, email });
});

export default app;
