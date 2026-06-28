export const CATEGORY_LABELS: Record<string, string> = {
  cashback_portal: 'Cashback Portals',
  bank: 'Bank Accounts',
  loyalty: 'Loyalty Programs',
  food_app: 'Food & Dining Apps',
  fuel_app: 'Fuel Apps',
  travel: 'Travel & FX',
  telco: 'Telco',
  survey: 'Surveys',
  shopping_app: 'Shopping Apps',
  other: 'Other',
}

export function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category
}
