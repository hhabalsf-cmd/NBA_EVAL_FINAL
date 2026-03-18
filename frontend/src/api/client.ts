/**
 * API client infrastructure — auth token management + fetch wrapper.
 * Feature-specific API functions live in each feature's api.ts.
 * All shared types live in api/types.ts.
 */

import { supabase } from '../shared/lib/supabase'

export const API_BASE = (import.meta.env.VITE_API_URL ?? '') + '/api'

// Cache the access token so apiFetch() doesn't await getSession() on every call.
let _accessToken: string | null = null
supabase.auth.getSession().then(({ data }) => {
  _accessToken = data.session?.access_token ?? null
})
supabase.auth.onAuthStateChange((_event, session) => {
  _accessToken = session?.access_token ?? null
})

/** Throw a user-friendly error, with special handling for 429 rate limits. */
export async function throwResponseError(response: Response, fallback: string): Promise<never> {
  if (response.status === 429) {
    const body = await response.json().catch(() => ({}))
    throw new Error((body as { detail?: string }).detail ?? 'Too many requests — please wait a moment and try again.')
  }
  const body = await response.json().catch(() => ({}))
  throw new Error((body as { detail?: string }).detail ?? fallback)
}

/**
 * Fetch wrapper that attaches the Supabase session token as a Bearer header
 * and dispatches a global event on 401 so the auth store can log the user out.
 */
export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const token = _accessToken ?? (await supabase.auth.getSession()).data.session?.access_token ?? null
  const headers = new Headers(init.headers)
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const res = await fetch(input, { ...init, headers })
  if (res.status === 401) {
    window.dispatchEvent(new Event('auth:unauthorized'))
  }
  return res
}

// Re-export all types for backward compatibility
export * from './types'
