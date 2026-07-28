// The API stores and returns kilograms, always. Pounds are a display
// preference, so every conversion in the app goes through this file — there is
// no second copy anywhere, and nothing sends pounds over the wire.

/** Exact, by definition of the international pound (not an approximation). */
export const KG_PER_LB = 0.45359237

export type WeightUnit = 'kg' | 'lb'

export function unitLabel(unit: WeightUnit): string {
  return unit === 'lb' ? 'lb' : 'kg'
}

export function kgToDisplay(kg: number, unit: WeightUnit): number {
  return unit === 'lb' ? kg / KG_PER_LB : kg
}

/** Display-unit input → the kg the API stores.
 *
 * Rounded to 3 decimals: a pound entry converts to a long float, and storing it
 * whole would make the value shown back drift in the last digit on every
 * round trip. Three decimals is a gram — finer than any scale reports. */
export function displayToKg(value: number, unit: WeightUnit): number {
  const kg = unit === 'lb' ? value * KG_PER_LB : value
  return Math.round(kg * 1000) / 1000
}

/** One decimal place, which is the precision bathroom scales actually have. */
export function formatWeight(kg: number, unit: WeightUnit): string {
  return kgToDisplay(kg, unit).toFixed(1)
}

/** A rate of change, signed, so "no change" and "losing" are distinguishable. */
export function formatRate(kgPerWeek: number, unit: WeightUnit): string {
  const value = kgToDisplay(kgPerWeek, unit)
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}`
}
