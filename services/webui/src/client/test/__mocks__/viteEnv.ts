/**
 * jest stub for lib/env — reads process.env so a test can still drive a value,
 * without the bundler-only `import.meta` syntax jest cannot parse.
 */

export function readEnv(key: string): string | undefined {
  return process.env[key];
}
