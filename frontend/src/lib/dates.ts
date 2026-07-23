// The user's calendar date. Never use toISOString() for this — it returns the
// UTC date, which is off by one near midnight for anyone not in UTC.
export function localIsoDate(date: Date = new Date()): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

// Parse a YYYY-MM-DD string into a local Date at midnight. Never use
// `new Date(iso)` for this — it parses the string as UTC, reintroducing the
// off-by-one-near-midnight bug localIsoDate exists to avoid.
export function parseIsoDate(iso: string): Date {
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(year, month - 1, day)
}

// Shift a YYYY-MM-DD string by whole days. Constructing the date locally lets
// JS normalize month/year rollover, and it's DST-safe for date-only math.
export function addDays(iso: string, delta: number): string {
  const [year, month, day] = iso.split('-').map(Number)
  return localIsoDate(new Date(year, month - 1, day + delta))
}
