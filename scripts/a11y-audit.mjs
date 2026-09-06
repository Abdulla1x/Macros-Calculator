#!/usr/bin/env node
//
// Run axe-core over every route in the app, at both widths, and report what
// fails WCAG 2.1 A and AA.
//
// WHY THIS EXISTS RATHER THAN A ONE-OFF AUDIT. The accessibility pass this
// script was written for found two things the roadmap had recorded as open and
// which were in fact already fixed, and one thing it had recorded as fixed
// which had quietly come back. A prose list of defects goes stale the moment
// the next phase adds a section; a script does not. Run it before and after a
// change and the number is the claim.
//
// It also answers a question a grep structurally cannot. The caption token
// --color-ink-faint is tuned against --color-surface, but a caption's ground is
// a DIFFERENT ELEMENT from the caption -- so "which captions sit on a lighter
// card" is not a text search, it is a question about the rendered tree with the
// alpha layers composited. axe does that compositing; grep cannot.
//
// Usage:
//
//   node scripts/a11y-audit.mjs                 # report to stdout
//   node scripts/a11y-audit.mjs report.json     # and write the raw findings
//
// Exits non-zero if anything fails, so it can be used as a ratchet.
//
// Deliberately NOT part of scripts/check.sh, for the same reason
// dom-snapshot.mjs is not: that gate is five fast offline commands, and this
// needs a browser and both servers running.
//
// ⚠ Setup, the route lists, the seeded account and the navigation loop live in
// scripts/lib/harness.mjs. Read its header before the first run on a machine --
// in particular, playwright-core and axe-core must be installed in ONE npm
// command or the second install deletes the first.
//
// ---------------------------------------------------------------------------
// What this can and cannot see
//
// CAN: names, roles, contrast, landmarks, heading order, form labels, ARIA
// attribute validity, duplicate ids -- everything that is a property of the
// rendered tree at rest.
//
// CANNOT: anything that only exists while you are driving the app. Whether a
// live region actually announces, whether Escape closes a dropdown, whether
// focus returns to the control that opened a dialog, whether a keyboard user
// can reach a list at all. Those need a person or a scripted keyboard pass, and
// no violation count here is evidence about them. Say so rather than letting a
// green run imply it.
//
// It also only sees what is ON SCREEN. EXPAND_ON in the harness opens the
// panels that render nothing until clicked -- the AI analyzer, the capped
// library lists, the add-a-food form. That hole has been found four times in
// this project; check what a default state hides before trusting a count here.
//
// ⚠ AND THE FIFTH INSTANCE WAS THIS SCRIPT'S OWN FIRST RUN. It reported the
// prose-link rule fixed at four links. A grep then found five more of exactly
// the same defect that the run had never rendered:
//
//   * AnnouncementsModal -- the harness seeds macros_seen_announcements, so the
//     modal never opens. That seeding is deliberate and correct (an unseeded
//     account gets a full-screen overlay on every route), which is what makes
//     this the hard case: the measure that keeps the harness honest is the same
//     measure that hides a component from it.
//   * The dashboard's "Nothing logged yet" line -- the harness seeds 14 days of
//     meals, so the empty state is unreachable by construction.
//   * ResetPassword's invalid-token branch, which needs a bad token in the URL.
//
// So a clean run means "clean in the states the harness renders", and the
// states it renders are chosen for determinism, not for coverage. Grep for the
// pattern as well when fixing a class of defect. The count is a floor.

import { writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

import {
  PRIVATE_ROUTES,
  PUBLIC_ROUTES,
  openSession,
  visitRoutes,
} from './lib/harness.mjs'

const reportPath = process.argv[2] ?? null

// The two widths every browser pass in this project uses: a 360px phone, which
// is the narrowest real device the tab bar was designed against, and a 1280px
// desktop, where the nav is a rail instead. They are not the same tree --
// Layout renders one nav element into two shells -- so a rule can fail at one
// width and pass at the other.
const VIEWPORTS = [
  { name: '360px', width: 360, height: 780 },
  { name: '1280px', width: 1280, height: 900 },
]

// axe-core resolves from the repo-root node_modules, relative to this file, so
// the script works from any working directory. fileURLToPath rather than
// .pathname: the latter leaves percent-encoding in place, so a checkout under a
// path with a space in it would hand playwright a filename that does not exist.
const AXE_SOURCE = fileURLToPath(new URL('../node_modules/axe-core/axe.min.js', import.meta.url))

/** Inject axe and run it against the whole document.
 *
 *  `runOnly` on the four WCAG tags rather than axe's whole rule set: the rest
 *  are best-practice rules that are opinions, not conformance, and mixing them
 *  in means the number cannot be read as "does this conform".
 *
 *  The result is mapped down INSIDE the browser. axe's raw output carries the
 *  full element handle and every check's data for every node, which is
 *  megabytes on a page like /settings/food and serialises slowly across the
 *  bridge for information nothing here reads. */
async function runAxe(page) {
  await page.addScriptTag({ path: AXE_SOURCE })
  return page.evaluate(async () => {
    const results = await window.axe.run(document, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
      resultTypes: ['violations'],
    })
    return results.violations.map((violation) => ({
      id: violation.id,
      impact: violation.impact,
      help: violation.help,
      nodes: violation.nodes.map((node) => ({
        target: node.target.join(' '),
        summary: (node.failureSummary ?? '').replace(/\s+/g, ' ').trim(),
      })),
    }))
  })
}

const findings = []

const session = await openSession()
try {
  for (const viewport of VIEWPORTS) {
    const record = async (page, route) => {
      const violations = await runAxe(page)
      const nodes = violations.reduce((total, violation) => total + violation.nodes.length, 0)
      findings.push({ width: viewport.name, route, violations })
      console.log(
        `  ${viewport.name.padEnd(7)} ${route.padEnd(20)} ` +
          `${violations.length === 0 ? 'clean' : `${violations.length} rules, ${nodes} nodes`}`,
      )
    }

    const size = { width: viewport.width, height: viewport.height }

    const anonymous = await session.anonymousContext(size)
    await visitRoutes(anonymous, PUBLIC_ROUTES, record)
    await anonymous.close()

    const authed = await session.authedContext(size)
    await visitRoutes(authed, PRIVATE_ROUTES, record)
    await authed.close()
  }
} finally {
  await session.browser.close()
}

// ---------------------------------------------------------------------------
// Report, grouped by RULE rather than by route.
//
// A single missing attribute in a shared component fails on every route that
// renders it, so a per-route listing prints the same defect eighteen times and
// buries how many distinct problems there actually are. Grouping by rule is
// what makes "four things are wrong" readable.

const byRule = new Map()
for (const { width, route, violations } of findings) {
  for (const violation of violations) {
    if (!byRule.has(violation.id)) {
      byRule.set(violation.id, { impact: violation.impact, help: violation.help, nodes: [] })
    }
    for (const node of violation.nodes) {
      byRule.get(violation.id).nodes.push({ width, route, ...node })
    }
  }
}

const totalNodes = [...byRule.values()].reduce((total, rule) => total + rule.nodes.length, 0)

console.log(`\n${'='.repeat(72)}`)
if (byRule.size === 0) {
  console.log('No WCAG 2.1 A/AA violations across 18 routes at both widths.')
} else {
  console.log(`${byRule.size} rules violated, ${totalNodes} nodes, across 18 routes at both widths\n`)
  const ranked = [...byRule.entries()].sort((a, b) => b[1].nodes.length - a[1].nodes.length)
  for (const [id, rule] of ranked) {
    console.log(`\n▶ ${id}  (${rule.impact}, ${rule.nodes.length} nodes)`)
    console.log(`  ${rule.help}`)
    // One example summary per rule: axe repeats the same sentence for every
    // node, and eighteen copies of it is what makes these reports unreadable.
    const example = rule.nodes.find((node) => node.summary)
    if (example) console.log(`  e.g. ${example.summary.slice(0, 300)}`)
    // Distinct targets, with the routes each appears on folded together, for
    // the same reason.
    const byTarget = new Map()
    for (const node of rule.nodes) {
      if (!byTarget.has(node.target)) byTarget.set(node.target, new Set())
      byTarget.get(node.target).add(`${node.route}@${node.width}`)
    }
    for (const [target, where] of byTarget) {
      const places = [...where]
      console.log(
        `    ${target}\n      ${places.slice(0, 4).join(', ')}` +
          `${places.length > 4 ? ` … +${places.length - 4} more` : ''}`,
      )
    }
  }
}
console.log(`${'='.repeat(72)}`)

if (reportPath) {
  await writeFile(reportPath, `${JSON.stringify(findings, null, 2)}\n`, 'utf8')
  console.log(`\nraw findings written to ${reportPath}`)
}

process.exit(byRule.size === 0 ? 0 : 1)
