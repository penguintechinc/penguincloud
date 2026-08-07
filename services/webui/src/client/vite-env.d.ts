/// <reference types="vite/client" />

/**
 * Build-time environment exposed to the client.
 * VITE_MOCKS=true starts the MSW worker before first render (see main.tsx).
 */
interface ImportMetaEnv {
  readonly VITE_MOCKS?: string;
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
