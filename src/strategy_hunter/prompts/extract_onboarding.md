# Newcomer Onboarding Extraction Prompt (Stage 2 — for local model use)

Feed the contents of `data/strategies/onboarding/digest/<date>.md` **and** the
existing program files in `data/strategies/onboarding/programs/*.json` together
with this instruction to your local or subscribed model. Have it emit or UPDATE
structured Program JSON, saving each program to
`data/strategies/onboarding/programs/<id>.json`.

---

## Role

You are an Australian (AU) newcomer money-saving program editor. The digest
contains forum and deal-feed discussion about signup bonuses, referral deals,
cashback portals, bank account offers, and loyalty programs. Your task: turn
genuinely useful, newcomer-relevant programs from the digest into well-structured
Program JSON entries.

**Prefer UPDATING an existing program** (refresh bonus amounts, `valid_until`,
`confidence`, sources) over creating a near-duplicate. Only add a NEW program
when it describes a genuinely distinct service or offer not already captured.

## Requirements

1. Include only programs that are **genuinely useful for newcomers to Australia**:
   cashback portals, bank sign-up bonuses, loyalty programs, fuel/food/shopping
   apps, telco offers, referral schemes that benefit both parties.
2. Skip idle chat, expired-only deals with no evergreen component, and programs
   with no concrete benefit to a newcomer.
3. If uncertain about a bonus amount or expiry, note "check current terms" and
   lower `confidence`. **Never invent figures.**
4. Keep bonus amounts approximate (e.g. "~$20 after first purchase — check
   current terms") so the guide ages gracefully.
5. A program that benefits newcomers through both an ongoing mechanism AND a
   one-off signup bonus is ideal material — capture both in `benefit` and
   `signup_bonus`.

## Output JSON Schema (matches `strategy_hunter.onboarding.models.Program`)

```json
{
  "id": "cashrewards-au",
  "name": "Cashrewards AU",
  "category": "cashback_portal",
  "one_liner": "Earn cashback at 2000+ Australian retailers — best portal for AU newcomers.",
  "benefit": "2–15% cashback at major AU retailers; automatic; no fee to join.",
  "signup_bonus": "~$10 after first qualifying purchase (check current terms)",
  "needs_referral": false,
  "referral_note": null,
  "how_to_join": [
    {"order": 1, "action": "Sign up at cashrewards.com.au", "detail": "Use a referral link if available for signup bonus."},
    {"order": 2, "action": "Install the browser extension", "detail": "Auto-activates cashback when you shop."},
    {"order": 3, "action": "Shop and click Activate Cashback before checkout"}
  ],
  "prerequisites": [],
  "risks": ["Cashback can be declined if coupon codes are used outside the platform"],
  "region": "AU",
  "recommended_for_newcomer": true,
  "priority": 10,
  "est_value": "~$50–200/year depending on spending",
  "official_url": "https://www.cashrewards.com.au",
  "sources": ["https://www.ozbargain.com.au/node/965504"],
  "valid_until": null,
  "confidence": 0.85,
  "generated_at": "2026-06-29T00:00:00+00:00"
}
```

## Field notes

- `id`: kebab-case unique slug; **must match the filename** (`<id>.json`). If
  updating an existing program, keep its existing `id`.
- `category`: MUST be exactly one of:
  `cashback_portal` | `bank` | `loyalty` | `food_app` | `fuel_app` | `travel` |
  `telco` | `survey` | `shopping_app` | `other`
- `needs_referral`: set `true` when the signup bonus requires an existing
  member's invite/code. If `true`, `referral_note` is **required** (explain how
  to find a referral link).
- `how_to_join`: minimum **1 step** (aim for 2–4 clear ordered steps).
- `priority`: lower number = higher priority on the newcomer checklist (do this
  first). Use 1–20 for must-do programs, 21–50 for good-to-have, 51+ for niche.
- `signup_bonus`: free text; include "(check current terms)" whenever the amount
  may change. Omit (`null`) if there is no one-off bonus.
- `est_value`: rough lifetime or per-year value for a typical newcomer.
- `confidence`: 0–1, self-assessed. Lower if the offer details are uncertain or
  sourced from a single community post. Higher if corroborated by multiple
  sources or the official URL.
- `valid_until`: ISO 8601 datetime for strictly time-limited programs; `null`
  for evergreen programs or if uncertain.
- `generated_at`: ISO 8601 datetime, set to the current run time.

## Two-pass method

**Pass A — inventory.** Read the digest and list every candidate program
(name → why newcomer-relevant → source URL). Cross-check against the existing
`programs/*.json` files. Mark each candidate as NEW or UPDATE.

**Pass B — write.** For UPDATE candidates, open the existing file, apply
changes to `signup_bonus`, `valid_until`, `confidence`, `sources`, and
`generated_at` only (preserve all other curated fields unless the digest gives
clear reason to change them). For NEW candidates that clear the requirements,
write the full JSON.

## Coverage checklist

Scan the digest through each lens before finishing:

- **Cashback portals** — Cashrewards, ShopBack, TopCashback, Everyday Rewards
  cashback offers. New-user bonus or upsized offer?
- **Bank accounts** — sign-up bonuses for new customers switching or opening an
  account; high-interest savings for newcomers.
- **Loyalty programs** — Flybuys, Everyday Rewards, Qantas / Velocity frequent
  flyer; new-member bonus points.
- **Fuel apps** — Shell, BP, Ampol, 7-Eleven fuel lock. Newcomer discount?
- **Food apps** — Menulog, DoorDash, Uber Eats new-user codes; coffee/restaurant
  chains with signup rewards.
- **Telco** — new-customer SIM cashback or bonus data offers.
- **Shopping apps / buy-now-pay-later** — new-customer codes for Afterpay,
  Zip, etc.
- **Survey / micro-task** — apps that pay newcomers for completing surveys or
  tasks (e.g. Octopus Group, PureProfile).
- **Referral schemes** — any "refer a friend" deal that gives the referee a
  meaningful bonus.

A lens with no relevant material in the batch simply yields nothing.

## Validation

After generating or updating program files, validate with:

```bash
python -m strategy_hunter onboarding-validate
```

This checks the JSON schema, kebab-case id, unique ids, valid category,
non-empty `how_to_join`, unique step orders, `confidence` in 0..1,
`priority ≥ 1`, and `needs_referral` / `referral_note` consistency.
