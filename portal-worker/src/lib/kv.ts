import type { KVNamespace } from "@cloudflare/workers-types";
import type { SessionData } from "../types";

const SESSION_TTL = 60 * 60 * 8; // 8 hours (must match the session cookie's maxAge)
const MAGIC_LINK_TTL = 60 * 30; // 30 minutes (link stays usable until it expires)
const RESUBSCRIBE_MARKER_TTL = 60 * 60 * 24 * 90; // 90 days — bounds how long a "you may reactivate" grant stays valid

export function generateId(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export async function createSession(
  kv: KVNamespace,
  data: SessionData
): Promise<string> {
  const id = generateId();
  await kv.put(`session:${id}`, JSON.stringify(data), {
    expirationTtl: SESSION_TTL,
  });
  return id;
}

export async function getSession(
  kv: KVNamespace,
  id: string
): Promise<SessionData | null> {
  const raw = await kv.get(`session:${id}`);
  if (!raw) return null;
  return JSON.parse(raw) as SessionData;
}

export async function deleteSession(
  kv: KVNamespace,
  id: string
): Promise<void> {
  await kv.delete(`session:${id}`);
}

export async function createMagicToken(
  kv: KVNamespace,
  email: string
): Promise<string> {
  const token = generateId();
  await kv.put(`magic:${token}`, JSON.stringify({ email }), {
    expirationTtl: MAGIC_LINK_TTL,
  });
  return token;
}

// Read a magic-link token without consuming it. The token stays valid for the
// full MAGIC_LINK_TTL window rather than being deleted on first use: this was
// previously single-use, but that regressed under email security scanners
// (Microsoft Safe Links, Proofpoint, etc.) that pre-fetch links before the
// user clicks — the scanner's fetch would burn the token and lock the real
// user out with an "expired" error (see commit 053961ec). The short 30-minute
// TTL bounds the exposure instead. A proper single-use fix would need a
// POST-confirm step so GET requests (including scanner prefetches) can't
// consume the token — left as future work.
export async function readMagicToken(
  kv: KVNamespace,
  token: string
): Promise<string | null> {
  const raw = await kv.get(`magic:${token}`);
  if (!raw) return null;
  const { email } = JSON.parse(raw) as { email: string };
  return email;
}

// Marks an email as eligible for self-serve resubscribe. Set only when a
// subscriber deactivates via the unsubscribe flow — this is what lets
// /auth/resubscribe (and the reactivation branch in /auth/verify) tell a
// "previously active, now unsubscribed" account apart from a still-pending
// waitlist applicant who was never approved (both look like Active=false in
// Notion, but only the former should ever be able to self-reactivate).
export async function markResubscribeEligible(
  kv: KVNamespace,
  email: string
): Promise<void> {
  await kv.put(`resub:${email}`, "1", { expirationTtl: RESUBSCRIBE_MARKER_TTL });
}

export async function isResubscribeEligible(
  kv: KVNamespace,
  email: string
): Promise<boolean> {
  return (await kv.get(`resub:${email}`)) !== null;
}

export async function clearResubscribeEligible(
  kv: KVNamespace,
  email: string
): Promise<void> {
  await kv.delete(`resub:${email}`);
}
