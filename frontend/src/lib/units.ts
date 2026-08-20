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

// --- Height ------------------------------------------------------------------
//
// Height follows the same rule as weight: the API stores one canonical unit
// (centimetres) and the display unit is a preference. It follows `weight_unit`
// rather than getting a setting of its own — someone who thinks in pounds
// thinks in feet and inches, and a second unit selector would be two controls
// for one decision.

/** Exact, by definition of the international inch (not an approximation). */
export const CM_PER_INCH = 2.54
const INCHES_PER_FOOT = 12

export interface FeetInches {
  feet: number
  inches: number
}

export function cmToFtIn(cm: number): FeetInches {
  const totalInches = Math.round(cm / CM_PER_INCH)
  return {
    feet: Math.floor(totalInches / INCHES_PER_FOOT),
    inches: totalInches % INCHES_PER_FOOT,
  }
}

/** Feet + inches → the centimetres the API stores.
 *
 * Rounded to 1 decimal, which is a millimetre: finer than anyone measures
 * their own height, and enough that a ft/in round trip doesn't drift in the
 * last digit the way an unrounded kg conversion would. Same argument as
 * displayToKg. */
export function ftInToCm(feet: number, inches: number): number {
  return Math.round((feet * INCHES_PER_FOOT + inches) * CM_PER_INCH * 10) / 10
}

/** Height for display, in whichever unit the weight preference implies. */
export function formatHeight(cm: number, unit: WeightUnit): string {
  if (unit !== 'lb') return `${Math.round(cm)} cm`
  const { feet, inches } = cmToFtIn(cm)
  return `${feet}′ ${inches}″`
}
