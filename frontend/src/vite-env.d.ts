/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Public Supabase project URL. */
  readonly VITE_SUPABASE_URL?: string
  /** Public anon/publishable key. Never the service-role key. */
  readonly VITE_SUPABASE_ANON_KEY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
