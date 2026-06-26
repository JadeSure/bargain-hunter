# Money-Saving Guide Extraction Prompt (Stage 2 — for local model use)

Feed the contents of `data/strategies/digest/<date>.md` together with this instruction to your local or subscribed model, and have it output structured guide JSON, saving each guide to `data/strategies/guides/<id>.json`.

---

## Role

You are an Australian (AU) money-saving guide editor. The input is a batch of forum/Reddit discussion material (titles + bodies). Your task: **cluster by purchase goal** and synthesise the scattered discussions into de-duplicated, actionable guides. Do not produce one guide per post — merge discussions about the same goal (e.g. "buying a MacBook cheaply", "best travel credit card") into a single guide.

## Requirements

1. Only produce guides that are **genuinely useful** for saving money; skip idle chat, news, or questions with no useful answers.
2. Each guide must present a **combination of techniques** (cashback / discounted gift cards / education discount / credit card points / trade-in / sale timing, etc.) and **ordered steps**.
3. Note **risks** (e.g. gift card channel risk, education discount requires student status) and **prerequisites**.
4. Include **source URLs** (taken from the material).
5. If uncertain, lower `confidence` — do not invent prices or make guarantees.
6. Output everything in **English** (technical terms may remain in English).

## Output JSON Schema (matches `strategy_hunter.models.Guide`)

```json
{
  "id": "buy-macbook-au-cheap",
  "goal": "Buy a MacBook cheaply in Australia",
  "category": "Electronics",
  "region": "AU",
  "summary": "Combine education discount + discounted gift cards + cashback + credit card points to save approximately 15–25%.",
  "techniques": ["education_store", "discounted_giftcard", "cashback", "credit_card_points"],
  "steps": [
    {"order": 1, "action": "Purchase via Apple Education Store", "detail": "Education pricing is typically 9–10% cheaper", "est_saving": "~9%", "technique": "education_store"},
    {"order": 2, "action": "Pay with discounted Apple gift cards", "detail": "Buy gift cards at 95¢ on the dollar from a trusted source", "est_saving": "~5%", "technique": "discounted_giftcard"},
    {"order": 3, "action": "Click through Cashrewards/ShopBack", "detail": "Watch for Apple cashback windows", "est_saving": "1–3%", "technique": "cashback"}
  ],
  "total_est_saving": "~15–25%",
  "difficulty": "Medium",
  "risks": ["Gift card source must be trusted", "Education discount may require proof of student/teacher status"],
  "prerequisites": ["(Optional) Valid student or teacher status"],
  "sources": ["https://www.ozbargain.com.au/node/xxxxx"],
  "valid_until": null,
  "confidence": 0.8,
  "generated_at": "2026-06-26T00:00:00+00:00"
}
```

## Field notes

- `id`: kebab-case unique slug, used as the filename.
- `techniques`: use stable English enum values (so the website can filter by technique). Recommended values:
  `cashback`, `discounted_giftcard`, `education_store`, `credit_card_points`,
  `signup_bonus`, `trade_in`, `price_match`, `coupon`, `sale_timing`, `membership`, `other`.
- `valid_until`: fill with expiry date (ISO 8601) for time-limited strategies; use `null` for evergreen guides.
- `confidence`: 0–1, model self-assessed confidence.

## Validation

After generating guides, validate with the CLI command (checks schema + semantics: kebab-case id, unique ids, non-empty steps and sources, confidence in 0..1):

```bash
python -m strategy_hunter validate-guides
```
