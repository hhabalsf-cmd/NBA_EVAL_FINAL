/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SUPABASE_URL: string
  readonly VITE_SUPABASE_ANON_KEY: string
  readonly VITE_API_URL?: string
  /**
   * Gates every model-prediction surface (best bets, prediction cards, model
   * edge, line evaluation). OFF unless '1' or 'true'. Read via
   * `src/shared/lib/flags.ts` — never directly from components.
   */
  readonly VITE_ENABLE_PREDICTIONS?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
