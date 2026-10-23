import type { Env } from "../types";

export function telegramConfigured(env: Env): boolean {
  return Boolean(env.TELEGRAM_BOT_TOKEN && env.TELEGRAM_BOT_USERNAME && env.TELEGRAM_WEBHOOK_SECRET);
}

export function deepLink(env: Env, startToken: string): string {
  const bot = (env.TELEGRAM_BOT_USERNAME ?? "").replace(/^@/, "");
  return `https://t.me/${bot}?start=${startToken}`;
}

// Best-effort reply: a failed confirmation message must not fail the webhook,
// otherwise Telegram keeps redelivering an update that was already applied.
export async function sendTelegramMessage(
  env: Env,
  chatId: string | number,
  text: string
): Promise<void> {
  try {
    const resp = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text }),
    });
    if (!resp.ok) console.log("telegram sendMessage failed", resp.status);
  } catch (err) {
    console.log("telegram sendMessage error", String(err));
  }
}
