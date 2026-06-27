import { Hono } from "hono";
import { requireAuth } from "../middleware/auth";
import { findSubscriberByEmail, updateSubscriber } from "../lib/notion";
import type { Env, SessionData, SubscriberUpdate } from "../types";

type Variables = { user: SessionData };

const app = new Hono<{ Bindings: Env; Variables: Variables }>();

app.use("/*", requireAuth);

// GET /api/me — return current subscriber's settings
app.get("/me", async (c) => {
  const user = c.get("user");
  const found = await findSubscriberByEmail(
    c.env.NOTION_TOKEN,
    c.env.SUBSCRIBERS_DB_ID,
    user.email
  );
  if (!found) return c.json({ error: "Subscriber not found" }, 404);
  return c.json(found.subscriber);
});

// PUT /api/me — update editable fields
app.put("/me", async (c) => {
  const user = c.get("user");
  const body = await c.req.json<SubscriberUpdate>();

  // Validate and sanitise
  const update: SubscriberUpdate = {};

  if (body.subscribeHot !== undefined) {
    update.subscribeHot = Boolean(body.subscribeHot);
  }
  if (Array.isArray(body.watchKeywords)) {
    update.watchKeywords = body.watchKeywords
      .map((k) => String(k).trim())
      .filter(Boolean);
  }
  if (Array.isArray(body.blockKeywords)) {
    update.blockKeywords = body.blockKeywords
      .map((k) => String(k).trim())
      .filter(Boolean);
  }
  if (body.minDiscountPercent !== undefined) {
    update.minDiscountPercent =
      body.minDiscountPercent === null
        ? null
        : Math.max(0, Math.min(100, Number(body.minDiscountPercent)));
  }
  if (body.maxAlertsPerDay !== undefined) {
    update.maxAlertsPerDay = Math.max(1, Math.min(50, Number(body.maxAlertsPerDay)));
  }
  if (body.maxWatchAlertsPerDay !== undefined) {
    update.maxWatchAlertsPerDay = Math.max(
      1,
      Math.min(50, Number(body.maxWatchAlertsPerDay))
    );
  }
  if (Array.isArray(body.channels)) {
    const valid = new Set(["Email", "Telegram"]);
    update.channels = body.channels.filter((ch) => valid.has(String(ch)));
  }
  if (Array.isArray(body.categories)) {
    update.categories = body.categories.map((c) => String(c).trim()).filter(Boolean);
  }
  if (body.hotLevel !== undefined) {
    const valid = new Set(["top", "great", "good"]);
    const v = body.hotLevel === null ? null : String(body.hotLevel).trim().toLowerCase();
    update.hotLevel = v && valid.has(v) ? v : null;
  }

  await updateSubscriber(c.env.NOTION_TOKEN, user.notionPageId, update);
  return c.json({ ok: true });
});

export default app;
