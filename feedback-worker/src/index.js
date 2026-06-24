// Bargain Hunter — feedback collector (Cloudflare Worker)
//
// Receives 👍/👎 clicks from digest emails and appends a row to the Notion
// Feedback DB. There is no server to run: the Worker executes only when a link
// is clicked, and idles at $0 the rest of the time.
//
//   Secret: NOTION_TOKEN     -> wrangler secret put NOTION_TOKEN
//   Var:    FEEDBACK_DB_ID    -> set in wrangler.jsonc
//
// Link shape (built in the email template):
//   https://<worker>.workers.dev/?d=<deal_key>&v=up|down&e=<email>

const NOTION_VERSION = "2022-06-28";

async function verifyHmac(secret, dealKey, verdict, email, token) {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(`${dealKey}|${verdict}|${email}`));
  const hex = Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 32);
  return hex === token;
}

const page = (msg) =>
  new Response(
    `<!doctype html><meta charset="utf-8">` +
      `<meta name="viewport" content="width=device-width,initial-scale=1">` +
      `<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;` +
      `max-width:480px;margin:64px auto;text-align:center;color:#111">` +
      `<h2>${msg}</h2><p style="color:#888">You can close this page.</p></div>`,
    { headers: { "content-type": "text/html; charset=utf-8" } },
  );

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Health / smoke check
    if (url.pathname === "/" && !url.search) {
      return page("Bargain Hunter feedback ✔");
    }

    const deal = url.searchParams.get("d");
    const verdict = url.searchParams.get("v"); // "up" | "down"
    const email = url.searchParams.get("e") || null;

    if (!deal || (verdict !== "up" && verdict !== "down")) {
      return new Response("bad request", { status: 400 });
    }

    const token = url.searchParams.get("t");
    if (!token || !(await verifyHmac(env.FEEDBACK_HMAC_SECRET, deal, verdict, email || "", token))) {
      return new Response("forbidden", { status: 403 });
    }

    const resp = await fetch("https://api.notion.com/v1/pages", {
      method: "POST",
      headers: {
        authorization: `Bearer ${env.NOTION_TOKEN}`,
        "notion-version": NOTION_VERSION,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        parent: { database_id: env.FEEDBACK_DB_ID },
        properties: {
          "Deal ID": { title: [{ text: { content: deal } }] },
          Verdict: { select: { name: verdict } },
          "Subscriber Email": { email },
          At: { date: { start: new Date().toISOString() } },
          Source: { select: { name: "customer" } },
        },
      }),
    });

    if (!resp.ok) {
      // Don't leak internals to the clicker; still thank them.
      console.log("notion write failed", resp.status, await resp.text());
      return page("Thanks — noted (sync pending)");
    }
    return page(
      verdict === "up"
        ? "Thanks! 👍 Glad it was useful."
        : "Got it 👎 We'll aim for fewer like this.",
    );
  },
};
