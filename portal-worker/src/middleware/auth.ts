import { createMiddleware } from "hono/factory";
import { getCookie } from "hono/cookie";
import { getSession } from "../lib/kv";
import type { Env, SessionData } from "../types";

type Variables = { user: SessionData };

export const requireAuth = createMiddleware<{
  Bindings: Env;
  Variables: Variables;
}>(async (c, next) => {
  const sessionId = getCookie(c, "session");
  if (!sessionId) {
    return c.json({ error: "Unauthorised" }, 401);
  }

  const session = await getSession(c.env.PORTAL_KV, sessionId);
  if (!session) {
    return c.json({ error: "Session expired" }, 401);
  }

  c.set("user", session);
  return next();
});

// Must run after requireAuth (needs c.get("user") already set).
export const requireOwner = createMiddleware<{
  Bindings: Env;
  Variables: Variables;
}>(async (c, next) => {
  const user = c.get("user");
  const owner = c.env.OWNER_EMAIL?.toLowerCase().trim();
  if (!owner || user.email.toLowerCase().trim() !== owner) {
    return c.json({ error: "Forbidden" }, 403);
  }
  return next();
});
