// M4b page acceptance (m4b-spec §10): button only on click, badge → evidence and back, degraded and
// not-ready states, no horizontal scroll at 390 px. Real model for the generation checks, stub for the rest.
// Usage: node tests/browser/m4b_check.mjs  → docs/acceptance/m4b-browser.json
import { chromium } from 'playwright-core'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const BASE = process.env.BASE_URL || 'http://127.0.0.1:5174' // Vite dev server proxying /api to :8000
const DEGRADED = 'http://127.0.0.1:8801'
const NOT_READY = 'http://127.0.0.1:8802'
const SI_JUN = 'bencaodian:formula:si_jun_zi_tang'
const WIDTHS = [[1280, 900], [390, 844]]
const results = []
const add = (name, ok, detail = '') => {
  results.push({ name, ok: Boolean(ok), detail: String(detail) })
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ' — ' + detail : ''}`)
}

const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true })

async function withPage([width, height], base, fn) {
  const context = await browser.newContext({ viewport: { width, height } })
  const page = await context.newPage()
  const problems = []
  page.on('console', m => {
    if (m.type() !== 'error') return
    // The project ships no favicon, so its 404 is known and allowed (m4a-browser.json notes the same).
    const source = m.location()?.url ?? ''
    if (source.includes('favicon') || m.text().includes('favicon')) return
    problems.push(m.text())
  })
  page.on('pageerror', e => problems.push(String(e)))
  let explainRequests = 0
  page.on('request', r => { if (r.url().includes('/ai/explain')) explainRequests += 1 })
  try {
    await fn(page, () => explainRequests, problems)
  } finally {
    await context.close()
  }
  return problems
}

async function generate(page, width, base) {
  await page.goto(`${base}/entity/${SI_JUN}`, { waitUntil: 'load' })
  await page.locator('#ai-explain-heading').waitFor()
  const button = page.getByRole('button', { name: '生成 AI 解释' })
  add(`${width} 方剂详情显示 AI 解释区与按钮`, await button.isVisible())
  await page.waitForTimeout(1500)
  return button
}

for (const size of WIDTHS) {
  const problems = await withPage(size, BASE, async (page, explainRequests) => {
    const width = size[0]
    const button = await generate(page, width, BASE)
    add(`${width} 点击前不发起解释请求`, (await explainRequests()) === 0)
    await button.click()
    // Generation is a real model call; wait for the footer that only renders with a response.
    await page.waitForFunction(
      () => document.body.innerText.includes('内容依据所列资料生成'), null, { timeout: 120000 })
    const badgeCount = await page.locator('.ref-badge').count()
    add(`${width} 生成解释并显示引用角标`, badgeCount > 0, `status ok, ${badgeCount} badges`)
    await page.locator('.ref-badge').first().click()
    if (!page.url().includes('/evidence/')) {
      // Several evidence IDs behind one ref: the badge opens EvidenceLinks' counter, then a link.
      await page.locator('.ref-evidence button').first().click()
      await page.locator('.ref-evidence a').first().click()
    }
    await page.waitForURL('**/evidence/**', { timeout: 10000 })
    add(`${width} 角标进入证据页`, page.url().includes('/evidence/'), page.url().split('/evidence/')[1].slice(0, 20) + '…')
    await page.goBack()
    await page.waitForURL('**/entity/**', { timeout: 10000 })
    add(`${width} 后退回到方剂详情`, page.url().includes('/entity/'))
  })
  add(`${size[0]} 无意外控制台错误`, problems.length === 0, problems.join(' | ').slice(0, 120))
}

for (const size of WIDTHS) {
  await withPage(size, DEGRADED, async page => {
    const width = size[0]
    await generate(page, width, DEGRADED).then(b => b.click())
    await page.waitForFunction(() => document.body.innerText.includes('未能生成通过校验的解释'), null, { timeout: 20000 })
    const text = await page.locator('.panel', { hasText: 'AI 解释' }).innerText()
    add(`${width} 降级状态显示原因`, text.includes('泽泻') && text.includes('剂量'), text.slice(0, 80).replace(/\n/g, ' '))
    const composition = await page.getByText('适用证候及症状').count()
    const relations = await page.getByRole('heading', { name: '关系', exact: true }).count()
    add(`${width} 降级时页面其余分区仍在`, composition > 0 && relations > 0)
    add(`${width} 降级时不显示任何句子角标`, (await page.locator('.ref-badge').count()) === 0)
  })
  await withPage(size, NOT_READY, async page => {
    await page.goto(`${NOT_READY}/entity/${SI_JUN}`, { waitUntil: 'load' })
    await page.getByText('模型未就绪').waitFor({ timeout: 10000 })
    add(`${size[0]} 模型未就绪提示且按钮可用`, await page.getByRole('button', { name: '生成 AI 解释' }).isEnabled())
  })
}

await withPage([390, 844], BASE, async page => {
  await page.goto(`${BASE}/entity/${SI_JUN}`, { waitUntil: 'load' })
  await page.locator('#ai-explain-heading').waitFor()
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth)
  add('390 无横向滚动', scrollWidth <= 390, `scrollWidth=${scrollWidth}`)
})

await browser.close()
const failed = results.filter(r => !r.ok)
const report = {
  checked_at: new Date().toISOString(),
  browser: 'Google Chrome（playwright-core 1.56.1，无头）',
  viewports: ['1280x900', '390x844'],
  model: 'deepseek-flash（生成用真实调用；降级与未就绪用替身后端）',
  results,
}
const out = path.join(ROOT, 'docs/acceptance/m4b-browser.json')
fs.writeFileSync(out, JSON.stringify(report, null, 2) + '\n')
console.log(`${results.length - failed.length}/${results.length} ok; written to ${path.relative(ROOT, out)}`)
if (failed.length) {
  console.log('FAILED: ' + failed.map(r => r.name).join(' | '))
  process.exit(1)
}
