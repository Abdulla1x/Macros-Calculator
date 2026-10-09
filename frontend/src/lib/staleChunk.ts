/** Recovery for a page piece that no longer exists after a deploy.
 *
 * The app is split into one file per page, each named by a hash of its
 * contents, and a deploy replaces them all. A page loaded before the deploy
 * still asks for the OLD names, and those are gone: Vercel answers 404 since
 * the rewrite stopped covering /assets/. Reloading fetches the new index.html,
 * which names the new files, and that is the whole fix.
 *
 * Most tabs never get here. The service worker serves the old files from its
 * precache until the new version activates, and vite-plugin-pwa's autoUpdate
 * then reloads every tab it controls. What is left is a page the worker does
 * NOT control: the very first visit before it installs, a hard refresh (which
 * bypasses it), a browser or private window that blocks service workers, and
 * the moment between activation and that reload. Those fetch from the network
 * and meet the 404.
 *
 * Reload at most once per 10 seconds, so a piece that is broken for some other
 * reason (offline, a real bug) cannot loop the tab; the second failure shows
 * the crash screen instead, which has its own Reload button. A window rather
 * than a once-per-session flag, because a long-lived tab can meet more than
 * one deploy. If storage is blocked the guard cannot remember anything, so it
 * does not reload at all rather than risk a loop.
 */

const RELOADED_AT = 'trackaholic:stale-chunk-reload'
const WINDOW_MS = 10_000

let reloading = false

/** True while a reload this module started is under way: the caller should
 *  render nothing rather than flash an error the reload is about to clear. */
export function isReloadingForNewVersion(): boolean {
  return reloading
}

/** The browsers' wording for a dynamic import whose file could not be
 *  fetched (Chromium, Safari, Firefox), plus Vite's for a failed CSS
 *  preload. Anything else is a real error and must reach the crash screen. */
export function isStaleChunkError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error)
  return /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|Unable to preload CSS/i.test(
    message,
  )
}

/** Load `href` afresh to pick up the new version, unless that was tried in
 *  the last WINDOW_MS. Returns whether a reload was started.
 *
 *  The destination is passed in rather than reloading the current address,
 *  because the browser's address can still show the page being LEFT: reload
 *  that and the user lands back where they started, having to tap again. */
export function reloadForNewVersion(href: string): boolean {
  if (reloading) return true
  try {
    const last = Number(sessionStorage.getItem(RELOADED_AT))
    if (last && Date.now() - last < WINDOW_MS) return false
    sessionStorage.setItem(RELOADED_AT, String(Date.now()))
  } catch {
    return false
  }
  reloading = true
  window.location.assign(href)
  return true
}
