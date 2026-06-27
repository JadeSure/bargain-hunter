import type { SubscriberData, SubscriberUpdate, WaitlistEntry } from "../types";

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
  HOT_LEVEL: "Hot Level",
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

function selectName(props: Record<string, unknown>, key: string): string | null {
  const prop = props[key] as { select?: { name: string } | null };
  return prop?.select?.name ?? null;
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
  const hotLevel = selectName(props, P.HOT_LEVEL);

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
      hotLevel,
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
  if (update.hotLevel !== undefined) {
    properties[P.HOT_LEVEL] =
      update.hotLevel === null ? { select: null } : { select: { name: update.hotLevel } };
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

// --- Access waitlist (separate Notion database) ---
// Create a Notion database, share it with the integration, and put its id in
// WAITLIST_DB_ID. It must expose these properties (exact names + types):
//   Email (Title) | Status (Select: pending/approved/rejected) |
//   Requested At (Date) | Last Seen (Date) | Count (Number) | Source (Text)
const W = {
  EMAIL: "Email",
  STATUS: "Status",
  REQUESTED_AT: "Requested At",
  LAST_SEEN: "Last Seen",
  COUNT: "Count",
  SOURCE: "Source",
} as const;

function parseWaitlistEntry(page: Record<string, unknown>): WaitlistEntry {
  const props = page.properties as Record<string, unknown>;
  const titleProp = props[W.EMAIL] as { title?: Array<{ plain_text: string }> };
  const email = (titleProp?.title ?? []).map((t) => t.plain_text).join("").trim();
  const status =
    (props[W.STATUS] as { select?: { name: string } | null })?.select?.name ?? "pending";
  const requestedAt =
    (props[W.REQUESTED_AT] as { date?: { start: string } | null })?.date?.start ?? null;
  const lastSeen =
    (props[W.LAST_SEEN] as { date?: { start: string } | null })?.date?.start ?? null;
  const count = (props[W.COUNT] as { number?: number | null })?.number ?? 0;
  const source = richText(props, W.SOURCE);
  return {
    pageId: page.id as string,
    email,
    status,
    source,
    requestedAt,
    lastSeen,
    count,
  };
}

async function findWaitlistPage(
  token: string,
  dbId: string,
  email: string
): Promise<WaitlistEntry | null> {
  const resp = await fetch(`${NOTION_API}/databases/${dbId}/query`, {
    method: "POST",
    headers: headers(token),
    body: JSON.stringify({
      filter: { property: W.EMAIL, title: { equals: email } },
      page_size: 1,
    }),
  });

  if (!resp.ok) {
    throw new Error(`Notion waitlist query failed: ${resp.status}`);
  }

  const data = (await resp.json()) as { results: Array<Record<string, unknown>> };
  return data.results.length ? parseWaitlistEntry(data.results[0]) : null;
}

// Persist an access request. De-dups by email: a repeat request bumps Count and
// Last Seen on the existing row rather than creating a duplicate.
export async function addToWaitlist(
  token: string,
  dbId: string,
  email: string,
  source = "modal"
): Promise<void> {
  const now = new Date().toISOString();
  const existing = await findWaitlistPage(token, dbId, email);

  if (existing) {
    const resp = await fetch(`${NOTION_API}/pages/${existing.pageId}`, {
      method: "PATCH",
      headers: headers(token),
      body: JSON.stringify({
        properties: {
          [W.COUNT]: { number: existing.count + 1 },
          [W.LAST_SEEN]: { date: { start: now } },
        },
      }),
    });
    if (!resp.ok) {
      throw new Error(`Notion waitlist update failed: ${resp.status}`);
    }
    return;
  }

  const resp = await fetch(`${NOTION_API}/pages`, {
    method: "POST",
    headers: headers(token),
    body: JSON.stringify({
      parent: { database_id: dbId },
      properties: {
        [W.EMAIL]: { title: [{ text: { content: email } }] },
        [W.STATUS]: { select: { name: "pending" } },
        [W.REQUESTED_AT]: { date: { start: now } },
        [W.LAST_SEEN]: { date: { start: now } },
        [W.COUNT]: { number: 1 },
        [W.SOURCE]: { rich_text: [{ text: { content: source } }] },
      },
    }),
  });
  if (!resp.ok) {
    throw new Error(`Notion waitlist create failed: ${resp.status}`);
  }
}

export async function listWaitlist(
  token: string,
  dbId: string
): Promise<WaitlistEntry[]> {
  const entries: WaitlistEntry[] = [];
  let cursor: string | undefined;
  for (;;) {
    const resp = await fetch(`${NOTION_API}/databases/${dbId}/query`, {
      method: "POST",
      headers: headers(token),
      body: JSON.stringify({
        sorts: [{ property: W.LAST_SEEN, direction: "descending" }],
        page_size: 100,
        ...(cursor ? { start_cursor: cursor } : {}),
      }),
    });
    if (!resp.ok) {
      throw new Error(`Notion waitlist list failed: ${resp.status}`);
    }
    const data = (await resp.json()) as {
      results: Array<Record<string, unknown>>;
      has_more: boolean;
      next_cursor: string | null;
    };
    for (const page of data.results) entries.push(parseWaitlistEntry(page));
    if (!data.has_more || !data.next_cursor) break;
    cursor = data.next_cursor;
  }
  return entries;
}
