import { Hono } from "hono";
import { cors } from "hono/cors";
import { logger } from "hono/logger";
import magicLinkRoutes from "./routes/auth/magic-link";
import requestAccessRoute from "./routes/auth/request-access";
import logoutRoute from "./routes/auth/logout";
import subscriberRoutes from "./routes/subscriber";
import type { Env } from "./types";

const app = new Hono<{ Bindings: Env }>();

app.use("*", logger());

app.use(
  "*",
  cors({
    origin: (origin, c) => {
      const allowed = c.env.FRONTEND_URL;
      return origin === allowed ? origin : null;
    },
    allowMethods: ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allowHeaders: ["Content-Type"],
    credentials: true,
    maxAge: 86400,
  })
);

app.get("/health", (c) => c.json({ ok: true }));

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
