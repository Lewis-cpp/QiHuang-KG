import assert from 'node:assert/strict'
import { after, afterEach, beforeEach, mock, test } from 'node:test'
import { createServer } from 'vite'

const server = await createServer({
  configFile: false,
  server: { middlewareMode: true, hmr: false, watch: null },
})
after(() => server.close())
const client = await server.ssrLoadModule('/src/api/client.ts')
const BUILD_A = 'a'.repeat(64)
const BUILD_B = 'b'.repeat(64)

beforeEach(() => {
  client.forgetBuild()
  client.snapshotChanged.value = false
})
afterEach(() => mock.restoreAll())

for (const first of ['/stats', '/datasets']) {
  test(`rejects the other batch when ${first} responds first`, async () => {
    const pending = new Map()
    mock.method(globalThis, 'fetch', url => new Promise(resolve => pending.set(url, resolve)))
    const requests = {
      '/stats': client.get('/stats', {}, { pinBuild: false }),
      '/datasets': client.get('/datasets'),
    }
    const second = first === '/stats' ? '/datasets' : '/stats'
    pending.get(`/api/v1${first}`)(Response.json({ build_id: BUILD_A }))
    assert.deepEqual(await requests[first], { build_id: BUILD_A })

    const rejected = assert.rejects(requests[second], { status: 409, code: 'snapshot_changed' })
    pending.get(`/api/v1${second}`)(Response.json({ build_id: BUILD_B }))
    await rejected
    assert.equal(client.storedBuild(), BUILD_A)
    assert.equal(client.snapshotChanged.value, true)
  })
}

test('accepts the same batch and omits the query parameter only for unpinned requests', async () => {
  const urls = []
  mock.method(globalThis, 'fetch', async url => {
    urls.push(url)
    return Response.json({ build_id: BUILD_A })
  })
  await client.get('/stats', {}, { pinBuild: false })
  await client.get('/datasets')
  await client.get('/stats', {}, { pinBuild: false })
  assert.deepEqual(urls, ['/api/v1/stats', `/api/v1/datasets?build_id=${BUILD_A}`, '/api/v1/stats'])
  assert.equal(client.storedBuild(), BUILD_A)
  assert.equal(client.snapshotChanged.value, false)
})

test('keeps an accepted health response without a top-level batch', async () => {
  client.rememberBuild(BUILD_A)
  const health = { status: 'unavailable', services: { database: { status: 'unavailable' } } }
  mock.method(globalThis, 'fetch', async () => Response.json(health, { status: 503 }))
  assert.deepEqual(await client.get('/health', {}, { pinBuild: false, acceptStatus: [503] }), health)
  assert.equal(client.storedBuild(), BUILD_A)
  assert.equal(client.snapshotChanged.value, false)
})

test('keeps the existing server-side snapshot error behavior', async () => {
  client.rememberBuild(BUILD_A)
  mock.method(globalThis, 'fetch', async () => Response.json({
    error: { code: 'snapshot_changed', message: '数据批次已更新，请刷新后重试' },
  }, { status: 409 }))
  await assert.rejects(client.get('/datasets'), { status: 409, code: 'snapshot_changed' })
  assert.equal(client.storedBuild(), BUILD_A)
  assert.equal(client.snapshotChanged.value, true)
})
