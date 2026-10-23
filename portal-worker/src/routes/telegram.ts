import { Hono } from "hono";
import { consumeTelegramLinkToken } from "../lib/kv";
import { findSubscriberPageByTelegram, linkTelegram, unlinkTelegram } from "../lib/notion";
import { sendTelegramMessage, telegramConfigured } from "../lib/telegram";
import type { Env } from "../types";

const app = new Hono<{ Bindings: Env }>();

// Mirrors routes/auth/unsubscribe.ts — no shared helper module between routes yet.
function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

interface TelegramUpdate {
  message?: {
    chat?: { id: number; type?: string };
    text?: string;
  };
}

// POST /telegram/webhook — registered with Telegram's setWebhook using
// secret_token=TELEGRAM_WEBHOOK_SECRET, which Telegram echoes back in the
// X-Telegram-Bot-Api-Secret-Token header on every update.
//
//   /start <token>  link this chat to the portal account that minted <token>
//   /start          explain how to link from the portal
//   /stop           unlink this chat (the Telegram channel is switched off)
//
// Always answers 200 once authenticated: a non-2xx makes Telegram redeliver.
app.post("/webhook", async (c) => {
  if (!telegramConfigured(c.env)) return c.json({ error: "Not found" }, 404);

  const header = c.req.header("X-Telegram-Bot-Api-Secret-Token") ?? "";
  if (!timingSafeEqual(header, c.env.TELEGRAM_WEBHOOK_SECRET ?? "")) {
    return c.json({ error: "Forbidden" }, 403);
  }

  const update = await c.req.json<TelegramUpdate>().catch(() => ({}) as TelegramUpdate);
  const chat = update.message?.chat;
  const text = (update.message?.text ?? "").trim();
  if (!chat || chat.type !== "private" || !text.startsWith("/")) return c.json({ ok: true });

  const chatId = String(chat.id);
  const [command, arg = ""] = text.split(/\s+/, 2);
  const cmd = command.split("@")[0].toLowerCase();

  if (cmd === "/start") {
    const link = arg ? await consumeTelegramLinkToken(c.env.PORTAL_KV, arg) : null;
    if (!link) {
      await sendTelegramMessage(
        c.env,
        chatId,
        arg
          ? "That link has expired. Open Settings in the Bargain Hunter portal and press “Connect Telegram” again."
          : "Hi! To get deal alerts here, open Settings in the Bargain Hunter portal and press “Connect Telegram”."
      );
      return c.json({ ok: true });
    }
    try {
      await linkTelegram(c.env.NOTION_TOKEN, link.notionPageId, chatId);
    } catch (err) {
      console.error(err);
      await sendTelegramMessage(
        c.env,
        chatId,
        "Sorry, linking failed. Please press “Connect Telegram” in the portal and try again."
      );
      return c.json({ ok: true });
    }
    await sendTelegramMessage(
      c.env,
      chatId,
      "✅ Connected. Your Bargain Hunter alerts will now arrive here. Send /stop to disconnect."
    );
    return c.json({ ok: true });
  }

  if (cmd === "/stop") {
    const pageId = await findSubscriberPageByTelegram(
      c.env.NOTION_TOKEN,
      c.env.SUBSCRIBERS_DB_ID,
      chatId
    );
    if (pageId) await unlinkTelegram(c.env.NOTION_TOKEN, pageId);
    await sendTelegramMessage(
      c.env,
      chatId,
      "Disconnected — no more Telegram alerts. Your email settings are unchanged."
    );
  }

  return c.json({ ok: true });
});

export default app;
