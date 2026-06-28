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

// TEMP diagnostic — remove after debugging magic-link delivery.
app.get("/auth/_diag2", async (c) => {
  const email = (c.req.query("email") || "").trim();
  const out: Record<string, unknown> = { email };

  // 1) Raw Notion query (does NOT throw on inactive); show stored email + Active.
  try {
    const resp = await fetch(
      `https://api.notion.com/v1/databases/${c.env.SUBSCRIBERS_DB_ID}/query`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${c.env.NOTION_TOKEN}`,
          "Notion-Version": "2022-06-28",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          filter: { property: "Email", email: { equals: email.toLowerCase() } },
          page_size: 5,
        }),
      }
    );
    const data = (await resp.json()) as {
      results?: Array<{ properties?: Record<string, unknown> }>;
    };
    out.notionStatus = resp.status;
    out.matchCount = data.results?.length ?? 0;
    out.matches = (data.results ?? []).map((p) => {
      const props = p.properties as Record<string, unknown>;
      const e = props?.["Email"] as { email?: string | null };
      const a = props?.["Active"] as { checkbox?: boolean };
      return { storedEmail: e?.email ?? null, active: a?.checkbox ?? null };
    });
  } catch (err) {
    out.notionError = String(err);
  }

  // 2) Real Resend send attempt; report the actual status/body.
  if (c.req.query("send") === "1") {    try {
      const r = await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${c.env.RESEND_API_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          from: "Bargain Hunter <noreply@bargainhunter.dpdns.org>",
          to: [email],
          subject: "Bargain Hunter diag test",
          html: "<p>diag test send</p>",
        }),
      });
      out.resendStatus = r.status;
      out.resendBody = await r.text();
    } catch (err) {
      out.resendError = String(err);
    }
  }

  // 3) Look up delivery status of a previously-sent email id.
  const statusId = c.req.query("statusId");
  if (statusId) {
    try {
      const r = await fetch(`https://api.resend.com/emails/${statusId}`, {
        headers: { Authorization: `Bearer ${c.env.RESEND_API_KEY}` },
      });
      out.statusLookup = await r.json();
    } catch (err) {
      out.statusError = String(err);
    }
  }

  return c.json(out);
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
