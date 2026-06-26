import { Hono } from "hono";
import { sendAccessRequest } from "../../lib/email";
import type { Env } from "../../types";

const app = new Hono<{ Bindings: Env }>();

// POST /auth/request-access — notify owner that someone wants access
app.post("/", async (c) => {
  const { email } = await c.req.json<{ email: string }>();

  if (!email || !email.includes("@")) {
    return c.json({ error: "Invalid email" }, 400);
  }

  // Fire-and-forget — always return 200 so we don't leak whether email is known
  c.executionCtx.waitUntil(
    sendAccessRequest(
      c.env.RESEND_API_KEY,
      c.env.OWNER_EMAIL,
      email.toLowerCase().trim()
    ).catch((err) => console.error("request-access email failed:", err))
  );

  return c.json({ ok: true });
});

export default app;
