/**
 * Single point of access to build-time environment values.
 *
 * `import.meta.env` is bundler-only syntax that jest's CJS transform cannot
 * parse, so it is confined to this module and stubbed in tests
 * (see jest.config.js moduleNameMapper). Everything else reads env through
 * `readEnv` and stays testable.
 */

export function readEnv(key: keyof ImportMetaEnv): string | undefined {
  return import.meta.env?.[key];
}
