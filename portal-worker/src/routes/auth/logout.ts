import { Hono } from "hono";
import { getCookie, deleteCookie } from "hono/cookie";
import { deleteSession } from "../../lib/kv";
import type { Env } from "../../types";

const app = new Hono<{ Bindings: Env }>();

app.post("/", async (c) => {
  const sessionId = getCookie(c, "session");
  if (sessionId) {
    await deleteSession(c.env.PORTAL_KV, sessionId);
  }
  deleteCookie(c, "session", { path: "/" });
  return c.json({ ok: true });
});

export default app;
