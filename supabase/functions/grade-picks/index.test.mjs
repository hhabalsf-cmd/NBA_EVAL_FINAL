import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import vm from 'node:vm'
import test from 'node:test'
import assert from 'node:assert/strict'

const require = createRequire(new URL('../../../frontend/package.json', import.meta.url))
const ts = require('typescript')
const source = ts.transpileModule(readFileSync(new URL('./index.ts', import.meta.url), 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2022 },
}).outputText

function harness(secret = 'test-secret', statuses = [200, 200]) {
  let handler
  const calls = []
  class FrozenDate extends Date {
    constructor(...args) { super(...(args.length ? args : ['2026-10-21T03:30:00Z'])) }
  }
  vm.runInNewContext(source, {
    Deno: {
      env: { get: key => ({ WEBHOOK_SECRET: secret, FASTAPI_URL: 'https://example.invalid', FASTAPI_SERVICE_KEY: 'service-test' })[key] },
      serve: fn => { handler = fn },
    },
    Date: FrozenDate, Intl, Response, console: { log() {}, error() {} },
    fetch: async (...args) => {
      calls.push(args)
      return new Response('upstream', { status: statuses[calls.length - 1] })
    },
  })
  const request = (authorization = 'Bearer test-secret') => new Request('https://example.invalid', {
    method: 'POST', headers: { Authorization: authorization },
    body: JSON.stringify({ record: { game_date: '2026-10-20' } }),
  })
  return { handler, request, calls }
}

test('missing webhook secret fails closed without reaching grading endpoints', async () => {
  const h = harness('')
  assert.equal((await h.handler(h.request())).status, 503)
  assert.equal(h.calls.length, 0)
})
test('incorrect webhook credentials cannot trigger grading', async () => {
  const h = harness()
  assert.equal((await h.handler(h.request('Bearer wrong'))).status, 401)
  assert.equal(h.calls.length, 0)
})
test('late ET slate grades on its ET date even after UTC midnight', async () => {
  const h = harness()
  assert.equal((await h.handler(h.request())).status, 200)
  assert.equal(h.calls.length, 2)
  assert.equal(h.calls[0][1].headers['X-Service-Key'], 'service-test')
})
for (const statuses of [[503, 200], [200, 503]]) {
  test(`upstream failure ${statuses} is reported as failure`, async () => {
    const h = harness('test-secret', statuses)
    assert.equal((await h.handler(h.request())).status, 502)
  })
}
