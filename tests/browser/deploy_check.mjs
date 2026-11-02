// M7 deploy check (m7-spec §3): the built frontend served by uvicorn — three deep links, refreshed.
// Usage: node tests/browser/deploy_check.mjs <base>  → prints {"ok": bool, "detail": …} JSON.
import { chromium } from 'playwright-core'

const BASE = process.argv[2] || 'http://127.0.0.1:8000'
const ROUTES = [`/entity/bencaodian:formula:si_jun_zi_tang`, `/graph/bencaodian:formula:si_jun_zi_tang`, `/ai`]
const EXPECTED = ['四君子汤', '四君子汤', 'AI 条件查询']
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true })
const problems = []
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const page = await context.newPage()
  page.on('console', m => {
    if (m.type() !== 'error') return
    const source = m.location()?.url ?? ''
    // The project ships no favicon, so its 404 is the one allowed console error.
    if (source.includes('favicon') || m.text().includes('favicon')) return
    problems.push(m.text())
  })
  page.on('pageerror', e => problems.push(String(e)))
  for (let i = 0; i < ROUTES.length; i += 1) {
    await page.goto(BASE + ROUTES[i], { waitUntil: 'load' })
    await page.locator('h1', { hasText: EXPECTED[i] }).waitFor({ timeout: 20000 })
    await page.reload({ waitUntil: 'load' })
    await page.locator('h1', { hasText: EXPECTED[i] }).waitFor({ timeout: 20000 })
  }
  await context.close()
} catch (error) {
  problems.push(String(error.message || error).slice(0, 200))
} finally {
  await browser.close()
}
console.log(JSON.stringify({ ok: problems.length === 0, detail: problems.join(' | ').slice(0, 300) }))
process.exit(problems.length ? 1 : 0)
