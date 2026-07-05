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
    if (body.minDiscountPercent === null) {
      update.minDiscountPercent = null;
    } else {
      const n = Number(body.minDiscountPercent);
      if (!Number.isFinite(n)) {
        return c.json({ error: "minDiscountPercent must be a number" }, 400);
      }
      update.minDiscountPercent = Math.max(0, Math.min(100, n));
    }
  }
  if (body.maxAlertsPerDay !== undefined) {
    const n = Number(body.maxAlertsPerDay);
    if (!Number.isFinite(n)) {
      return c.json({ error: "maxAlertsPerDay must be a number" }, 400);
    }
    update.maxAlertsPerDay = Math.max(1, Math.min(50, n));
  }
  if (body.maxWatchAlertsPerDay !== undefined) {
    const n = Number(body.maxWatchAlertsPerDay);
    if (!Number.isFinite(n)) {
      return c.json({ error: "maxWatchAlertsPerDay must be a number" }, 400);
    }
    update.maxWatchAlertsPerDay = Math.max(1, Math.min(50, n));
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
  // Per-user quiet-hours override: "HH:MM" (24h) or null = use the pipeline's
  // global default. Both must be set together for the override to take effect
  // pipeline-side, but each field is validated/stored independently.
  const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;
  if (body.quietHoursStart !== undefined) {
    if (body.quietHoursStart === null || body.quietHoursStart === "") {
      update.quietHoursStart = null;
    } else {
      const v = String(body.quietHoursStart).trim();
      if (!HHMM.test(v)) {
        return c.json({ error: "quietHoursStart must be HH:MM (24h)" }, 400);
      }
      update.quietHoursStart = v;
    }
  }
  if (body.quietHoursEnd !== undefined) {
    if (body.quietHoursEnd === null || body.quietHoursEnd === "") {
      update.quietHoursEnd = null;
    } else {
      const v = String(body.quietHoursEnd).trim();
      if (!HHMM.test(v)) {
        return c.json({ error: "quietHoursEnd must be HH:MM (24h)" }, 400);
      }
      update.quietHoursEnd = v;
    }
  }

  await updateSubscriber(c.env.NOTION_TOKEN, user.notionPageId, update);
  return c.json({ ok: true });
});

export default app;
