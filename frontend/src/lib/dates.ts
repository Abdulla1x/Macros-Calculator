// The user's calendar date. Never use toISOString() for this — it returns the
// UTC date, which is off by one near midnight for anyone not in UTC.
export function localIsoDate(date: Date = new Date()): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

// Split a YYYY-MM-DD string into its three numbers, or refuse.
//
// `iso.split('-').map(Number)` destructured into [year, month, day] looks total
// and is not: given anything that is not three parts, month and day are
// undefined, and `new Date(NaN, NaN, undefined)` is not an error but an Invalid
// Date. That propagates silently — as the literal text "Invalid Date" through
// toLocaleDateString, and, worse, as the string "NaN-NaN-NaN" out of addDays,
// which Dashboard hands straight to the analytics endpoint as a query
// parameter. Every caller today passes a value this module or the server
// generated, so a bad one is a programmer error; throwing says so at the point
// it happens rather than somewhere downstream that cannot explain it.
function isoParts(iso: string): [number, number, number] {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  if (!match) {
    throw new Error(`Expected a YYYY-MM-DD date, got ${JSON.stringify(iso)}`)
  }
  // Indices 1-3 exist whenever the pattern matched, but the compiler cannot
  // know that from a RegExpExecArray, hence the fallbacks. They are unreachable.
  return [Number(match[1] ?? 0), Number(match[2] ?? 0), Number(match[3] ?? 0)]
}

// Parse a YYYY-MM-DD string into a local Date at midnight. Never use
// `new Date(iso)` for this — it parses the string as UTC, reintroducing the
// off-by-one-near-midnight bug localIsoDate exists to avoid.
export function parseIsoDate(iso: string): Date {
  const [year, month, day] = isoParts(iso)
  return new Date(year, month - 1, day)
}

// Shift a YYYY-MM-DD string by whole days. Constructing the date locally lets
// JS normalize month/year rollover, and it's DST-safe for date-only math.
//
// The normalization is deliberate and is why isoParts validates the *string*
// rather than the resulting date: `day + delta` is expected to run past the end
// of the month and be carried, so a date-validity check here would reject the
// one thing this function is for.
export function addDays(iso: string, delta: number): string {
  const [year, month, day] = isoParts(iso)
  return localIsoDate(new Date(year, month - 1, day + delta))
}
