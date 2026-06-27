import { Hono } from "hono";
import { cors } from "hono/cors";
import { logger } from "hono/logger";
import magicLinkRoutes from "./routes/auth/magic-link";
import requestAccessRoute from "./routes/auth/request-access";
import logoutRoute from "./routes/auth/logout";
import subscriberRoutes from "./routes/subscriber";
import { allowedOrigins } from "./lib/origins";
import type { Env } from "./types";

const app = new Hono<{ Bindings: Env }>();

app.use("*", logger());

app.use(
  "*",
  cors({
    origin: (origin, c) => {
      const allowed = allowedOrigins(c.env);
      return origin && allowed.includes(origin) ? origin : null;
    },
    allowMethods: ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allowHeaders: ["Content-Type"],
    credentials: true,
    maxAge: 86400,
  })
);

app.get("/health", (c) => c.json({ ok: true }));

// TEMP DIAGNOSTIC — remove after verifying Resend. Sends a test email to
// OWNER_EMAIL only (no arbitrary recipient) and returns Resend's raw status so
// we can tell a missing key (401) from an unverified domain (403) etc.
app.get("/auth/_diag", async (c) => {
  const key = c.env.RESEND_API_KEY ?? "";
  const to = c.env.OWNER_EMAIL;
  let status = 0;
  let body = "";
  try {
    const resp = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        from: "Bargain Hunter <onboarding@resend.dev>",
        to: [to],
        subject: "Bargain Hunter diagnostic",
        html: "<p>Resend diagnostic test — safe to ignore.</p>",
      }),
    });
    status = resp.status;
    body = (await resp.text()).slice(0, 300);
  } catch (e) {
    body = String(e).slice(0, 300);
  }
  return c.json({ keyPresent: key.length > 0, keyLen: key.length, to, status, body });
});

app.route("/auth/magic-link", magicLinkRoutes);
app.route("/auth/request-access", requestAccessRoute);
app.route("/auth/logout", logoutRoute);
app.route("/api", subscriberRoutes);

app.onError((err, c) => {
  console.error(err);
  return c.json({ error: "Internal server error" }, 500);
});

app.notFound((c) => c.json({ error: "Not found" }, 404));

export default app;
