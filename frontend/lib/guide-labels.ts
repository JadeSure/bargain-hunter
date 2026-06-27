export const TECHNIQUE_LABELS: Record<string, string> = {
  cashback: 'Cashback',
  discounted_giftcard: 'Discounted Gift Cards',
  education_store: 'Education Store',
  credit_card_points: 'Credit Card Points',
  signup_bonus: 'Sign-up Bonus',
  bank_switch: 'Bank Switch',
  churning: 'Card Churning',
  trade_in: 'Trade-in',
  price_match: 'Price Match',
  coupon: 'Coupon',
  sale_timing: 'Sale Timing',
  membership: 'Membership',
  loyalty_program: 'Loyalty Program',
  receipt_scanning: 'Receipt Scanning',
  subscription_swap: 'Subscription Swap',
  bill_switching: 'Bill Switching',
  no_fx_fee_card: 'No-FX Travel Card',
  other: 'Other',
}

export function techniqueLabel(technique: string): string {
  return TECHNIQUE_LABELS[technique] ?? technique
}
