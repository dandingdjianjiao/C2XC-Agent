function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function readStringField(obj: unknown, key: string): string {
  if (!isRecord(obj)) return ''
  const value = obj[key]
  return typeof value === 'string' ? value.trim() : ''
}

export function getRunTitleFromRecipesJson(recipesJson: unknown): string | null {
  const obj = isRecord(recipesJson) ? recipesJson : null
  const recipes = Array.isArray(obj?.['recipes']) ? obj?.['recipes'] : []
  if (!recipes.length) return null

  const first = isRecord(recipes[0]) ? recipes[0] : null
  if (!first) return null

  const m1 = readStringField(first, 'M1')
  const m2 = readStringField(first, 'M2')
  const ratio = readStringField(first, 'atomic_ratio')
  const modifier = readStringField(first, 'small_molecule_modifier')

  const catalyst = [m1, m2].filter(Boolean).join('-')
  const parts = [catalyst, ratio, modifier].filter(Boolean)
  if (!parts.length) return null

  const base = parts.join(' · ')
  if (recipes.length <= 1) return base
  return `${base} +${recipes.length - 1} more`
}
