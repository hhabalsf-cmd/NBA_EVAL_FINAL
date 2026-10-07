const FASTAPI_URL = Deno.env.get('FASTAPI_URL')!
const FASTAPI_SERVICE_KEY = Deno.env.get('FASTAPI_SERVICE_KEY')!

function isAfterGradeWindow(): boolean {
  return Number(new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York', hour: '2-digit', hourCycle: 'h23',
  }).format(new Date())) >= 23
}

function getTodayET(): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(new Date())
  const value = (type: string) => parts.find(p => p.type === type)!.value
  return `${value('year')}-${value('month')}-${value('day')}`
}

Deno.serve(async (req) => {
  // Verify inbound authorization
  const authHeader = req.headers.get('Authorization')
  const expectedKey = Deno.env.get('WEBHOOK_SECRET')
  // WARNING: a missing webhook secret must never disable authorization.
  if (!expectedKey) {
    return new Response('Webhook authentication is not configured', { status: 503 })
  }
  if (!authHeader || authHeader !== `Bearer ${expectedKey}`) {
    return new Response('Unauthorized', { status: 401 })
  }

  try {
    const body = await req.json()
    const record = body.record

    if (!record?.game_date) {
      return new Response('no game_date', { status: 200 })
    }

    const todayET = getTodayET()
    const isToday = record.game_date === todayET

    if (!isToday || !isAfterGradeWindow()) {
      return new Response('skipped — not today or too early', { status: 200 })
    }

    // Call FastAPI auto-grade
    const res = await fetch(`${FASTAPI_URL}/api/picks/auto-grade`, {
      method: 'POST',
      headers: { 'X-Service-Key': FASTAPI_SERVICE_KEY },
    })

    const text = await res.text()
    console.log(`auto-grade picks response: ${res.status} ${text}`)

    // Also grade game predictions
    const gamesRes = await fetch(`${FASTAPI_URL}/api/games/auto-grade`, {
      method: 'POST',
      headers: { 'X-Service-Key': FASTAPI_SERVICE_KEY },
    })

    if (!res.ok || !gamesRes.ok) {
      return new Response('Upstream grading failed', { status: 502 })
    }
    return new Response('graded', { status: 200 })
  } catch (err) {
    console.error('grade-picks error:', err)
    return new Response(`error: ${err}`, { status: 500 })
  }
})
