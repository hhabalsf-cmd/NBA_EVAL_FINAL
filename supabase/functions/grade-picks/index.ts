const FASTAPI_URL = Deno.env.get('FASTAPI_URL')!
const FASTAPI_SERVICE_KEY = Deno.env.get('FASTAPI_SERVICE_KEY')!

function isAfterGradeWindow(): boolean {
  const now = new Date()
  const etTime = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }))
  return etTime.getHours() >= 23
}

function getTodayET(): string {
  const now = new Date()
  return new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }))
    .toISOString()
    .slice(0, 10)
}

Deno.serve(async (req) => {
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
    await fetch(`${FASTAPI_URL}/api/games/auto-grade`, {
      method: 'POST',
      headers: { 'X-Service-Key': FASTAPI_SERVICE_KEY },
    })

    return new Response('graded', { status: 200 })
  } catch (err) {
    console.error('grade-picks error:', err)
    return new Response(`error: ${err}`, { status: 500 })
  }
})
