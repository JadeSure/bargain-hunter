import type { SubscriberData, SubscriberUpdate } from "../types";

const NOTION_API = "https://api.notion.com/v1";
const NOTION_VERSION = "2022-06-28";

// Property names must match the Notion DB schema (see src/bargain_hunter/subscribers.py)
const P = {
  NAME: "Name",
  EMAIL: "Email",
  TELEGRAM: "Telegram Chat ID",
  ACTIVE: "Active",
  CHANNELS: "Channels",
  HOT: "Subscribe Hot Deals",
  KEYWORDS: "Watch Keywords",
  MIN_DISCOUNT: "Min Discount %",
  CATEGORIES: "Categories",
  MAX_ALERTS: "Max Alerts/Day",
  MAX_WATCH_ALERTS: "Max Watch Alerts/Day",
  BLOCK_KEYWORDS: "Block Keywords",
} as const;

function headers(token: string): Record<string, string> {
  return {
    Authorization: `Bearer ${token}`,
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json",
  };
}

function richText(props: Record<string, unknown>, key: string): string {
  const prop = props[key] as { rich_text?: Array<{ plain_text: string }> };
  return (prop?.rich_text ?? []).map((t) => t.plain_text).join("").trim();
}

function multiSelect(props: Record<string, unknown>, key: string): string[] {
  const prop = props[key] as { multi_select?: Array<{ name: string }> };
  return (prop?.multi_select ?? []).map((o) => o.name);
}

function parseKeywords(raw: string): string[] {
  return raw
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
}

function parseSubscriber(
  page: Record<string, unknown>
): { subscriber: SubscriberData; pageId: string } {
  const props = page.properties as Record<string, unknown>;
  const id = page.id as string;

  const nameTitle = props[P.NAME] as {
    title?: Array<{ plain_text: string }>;
  };
  const name = (nameTitle?.title ?? []).map((t) => t.plain_text).join("").trim();

  const emailProp = props[P.EMAIL] as { email?: string | null };
  const email = emailProp?.email ?? "";

  const telegramRaw = richText(props, P.TELEGRAM);
  const telegramChatId = telegramRaw || null;

  const activeProp = props[P.ACTIVE] as { checkbox?: boolean };
  const active = activeProp?.checkbox ?? false;

  if (!active) throw new Error("Subscriber is not active");

  const channels = multiSelect(props, P.CHANNELS);
  const subscribeHot = (props[P.HOT] as { checkbox?: boolean })?.checkbox ?? false;
  const watchKeywords = parseKeywords(richText(props, P.KEYWORDS));
  const blockKeywords = parseKeywords(richText(props, P.BLOCK_KEYWORDS));

  const minDiscountProp = props[P.MIN_DISCOUNT] as { number?: number | null };
  const minDiscountPercent = minDiscountProp?.number ?? null;

  const categories = multiSelect(props, P.CATEGORIES);

  const maxAlertsProp = props[P.MAX_ALERTS] as { number?: number | null };
  const maxAlertsPerDay = maxAlertsProp?.number ?? 10;

  const maxWatchAlertsProp = props[P.MAX_WATCH_ALERTS] as {
    number?: number | null;
  };
  const maxWatchAlertsPerDay = maxWatchAlertsProp?.number ?? 10;

  return {
    pageId: id,
    subscriber: {
      name,
      email,
      telegramChatId,
      subscribeHot,
      watchKeywords,
      blockKeywords,
      minDiscountPercent,
      maxAlertsPerDay,
      maxWatchAlertsPerDay,
      channels,
      categories,
    },
  };
}

export async function findSubscriberByEmail(
  token: string,
  dbId: string,
  email: string
): Promise<{ subscriber: SubscriberData; pageId: string } | null> {
  const resp = await fetch(`${NOTION_API}/databases/${dbId}/query`, {
    method: "POST",
    headers: headers(token),
    body: JSON.stringify({
      filter: { property: P.EMAIL, email: { equals: email } },
      page_size: 1,
    }),
  });

  if (!resp.ok) {
    throw new Error(`Notion query failed: ${resp.status}`);
  }

  const data = (await resp.json()) as {
    results: Array<Record<string, unknown>>;
  };
  if (!data.results.length) return null;

  try {
    return parseSubscriber(data.results[0]);
  } catch {
    return null;
  }
}

export async function updateSubscriber(
  token: string,
  pageId: string,
  update: SubscriberUpdate
): Promise<void> {
  const properties: Record<string, unknown> = {};

  if (update.subscribeHot !== undefined) {
    properties[P.HOT] = { checkbox: update.subscribeHot };
  }
  if (update.watchKeywords !== undefined) {
    properties[P.KEYWORDS] = {
      rich_text: [{ text: { content: update.watchKeywords.join("\n") } }],
    };
  }
  if (update.blockKeywords !== undefined) {
    properties[P.BLOCK_KEYWORDS] = {
      rich_text: [{ text: { content: update.blockKeywords.join("\n") } }],
    };
  }
  if (update.minDiscountPercent !== undefined) {
    properties[P.MIN_DISCOUNT] = { number: update.minDiscountPercent };
  }
  if (update.maxAlertsPerDay !== undefined) {
    properties[P.MAX_ALERTS] = { number: update.maxAlertsPerDay };
  }
  if (update.maxWatchAlertsPerDay !== undefined) {
    properties[P.MAX_WATCH_ALERTS] = { number: update.maxWatchAlertsPerDay };
  }
  if (update.channels !== undefined) {
    properties[P.CHANNELS] = {
      multi_select: update.channels.map((name) => ({ name })),
    };
  }
  if (update.categories !== undefined) {
    properties[P.CATEGORIES] = {
      multi_select: update.categories.map((name) => ({ name })),
    };
  }

  if (!Object.keys(properties).length) return;

  const resp = await fetch(`${NOTION_API}/pages/${pageId}`, {
    method: "PATCH",
    headers: headers(token),
    body: JSON.stringify({ properties }),
  });

  if (!resp.ok) {
    throw new Error(`Notion update failed: ${resp.status}`);
  }
}
