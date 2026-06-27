import type { KVNamespace } from "@cloudflare/workers-types";
import type { SessionData } from "../types";

const SESSION_TTL = 60 * 60 * 24 * 7; // 7 days
const MAGIC_LINK_TTL = 60 * 15; // 15 minutes
const OAUTH_STATE_TTL = 60 * 10; // 10 minutes

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

export async function consumeMagicToken(
  kv: KVNamespace,
  token: string
): Promise<string | null> {
  const raw = await kv.get(`magic:${token}`);
  if (!raw) return null;
  await kv.delete(`magic:${token}`);
  const { email } = JSON.parse(raw) as { email: string };
  return email;
}

export async function createOAuthState(kv: KVNamespace): Promise<string> {
  const state = generateId();
  await kv.put(`oauth:${state}`, "1", { expirationTtl: OAUTH_STATE_TTL });
  return state;
}

export async function verifyOAuthState(
  kv: KVNamespace,
  state: string
): Promise<boolean> {
  const val = await kv.get(`oauth:${state}`);
  if (!val) return false;
  await kv.delete(`oauth:${state}`);
  return true;
}
