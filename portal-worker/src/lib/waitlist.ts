import { activateSubscriber, updateWaitlistStatus } from "./notion";
import { createMagicToken } from "./kv";
import { primaryFrontendUrl } from "./origins";
import type { Env } from "../types";

export type ApproveResult =
  | { ok: true; magicLinkUrl: string }
  | { ok: false; reason: "not_found" };

// Activates the subscriber and marks the waitlist row approved. Does NOT send
// the activation email itself — callers should waitUntil() that separately so
// the HTTP response doesn't wait on Resend.
export async function approveApplicant(env: Env, email: string): Promise<ApproveResult> {
  const activated = await activateSubscriber(env.NOTION_TOKEN, env.SUBSCRIBERS_DB_ID, email);
  if (!activated) return { ok: false, reason: "not_found" };

  if (env.WAITLIST_DB_ID) {
    try {
      await updateWaitlistStatus(env.NOTION_TOKEN, env.WAITLIST_DB_ID, email, "approved");
    } catch (err) {
      console.error("waitlist status update (approved) failed:", err);
    }
  }

  const token = await createMagicToken(env.PORTAL_KV, email);
  const magicLinkUrl = `${primaryFrontendUrl(env)}/auth/verify?token=${token}`;
  return { ok: true, magicLinkUrl };
}

// Marks the waitlist row rejected. Rejected applicants get no email (silent)
// and their (inactive) Subscriber row is left as-is.
export async function rejectApplicant(env: Env, email: string): Promise<boolean> {
  if (!env.WAITLIST_DB_ID) return false;
  return updateWaitlistStatus(env.NOTION_TOKEN, env.WAITLIST_DB_ID, email, "rejected");
}
