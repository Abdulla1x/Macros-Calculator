// The user's calendar date. Never use toISOString() for this — it returns the
// UTC date, which is off by one near midnight for anyone not in UTC.
export function localIsoDate(date: Date = new Date()): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}
