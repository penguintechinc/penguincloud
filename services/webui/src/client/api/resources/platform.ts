/**
 * Platform-level endpoints: the sample hello routes.
 *
 * `goApi` (`/go/status`, `/go/numa/info`, `/go/memory/stats`) was removed
 * rather than repaired. All three resolved to `/api/v1/go/*`, which the portal
 * does not register — and could not have reached the Go backend either, since
 * the webui server rewrites `^/api/go` (`src/server/index.ts:79`), a prefix the
 * axios `baseURL` of `/api/v1` can never produce. Nothing outside its own tests
 * called it, and this repo contains no Go service to check a corrected path
 * against, so guessing one would have been inventing a contract rather than
 * fixing a bug. See task-4N-report.md §Fix round 3.
 */

import api from "../../lib/api";

export const helloApi = {
  get: async (): Promise<{ message: string; timestamp: string }> => {
    const response = await api.get("/hello");
    return response.data;
  },
  getProtected: async (): Promise<{
    message: string;
    user: string;
    role: string;
  }> => {
    const response = await api.get("/hello/protected");
    return response.data;
  },
};
