# Social Content Generation Spec (Reddit / short-form)

Rewrite an **approved** guide JSON (`data/strategies/guides/<id>.json`) into ready-to-post
English social content. **Use only information already in the guide** — never invent prices,
discounts, or sources. Tone can be friendly, but every fact must match the guide; when unsure,
reuse the guide's exact wording or omit it.

Output path: `data/strategies/content/<id>.<platform>.md`, where `platform` is `reddit` or `short`.

## Common rules

- Language: English (AU spelling, e.g. "favourite", "maximise").
- Never promise returns; reuse the guide's `est_saving` / `total_est_saving` wording (e.g. "~15%").
- Keep and naturally weave in the guide's **risks** and **prerequisites** — this is honest and
  stops readers getting burned.
- End with a one-line disclaimer: mechanics/prices change anytime; check the retailer's current terms.
- Cite 1–2 source links at the end (taken from the guide's `sources`).

## Reddit version (`*.reddit.md`)

Long-form "value post" style, suited to community deep-reads (e.g. r/AusFinance, r/AusFrugal):

- Title: `<goal> — <one-line hook>`.
- Open: 1–2 sentences naming the pain point + how much you can save.
- Body: numbered steps following the guide's `steps` order, each with its `detail` and `est_saving`.
- "Watch out" section: list the `risks`.
- "Before you start" section: list `prerequisites` (if any).
- 250–500 words.

## Short-form version (`*.short.md`)

Light, scannable style for X / Instagram / Threads captions:

- Hook: ≤ 120 chars, lead with the savings result (e.g. "Save ~$1k on a MacBook in AU 💻").
- Body: short lines + light emoji + whitespace; steps as ✅ or 1️⃣2️⃣3️⃣.
- Close with 5–8 hashtags: `#AusFinance #AusFrugal #Bargain #SaveMoney #<category>` etc.
- 80–150 words.

## Quality gates (do not post if any are true)

- A price/discount/source appears that is not in the guide.
- A risk was dropped while still recommending a risky play.
- Anything is inconsistent with the guide (techniques, step order, applicable region).
