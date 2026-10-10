/**
 * Typed access to the portal API, backed by the generated OpenAPI schema.
 *
 * `schema.d.ts` is generated from `openapi/v1.yaml` (`npm run generate:api`),
 * which is itself generated from the backend's live route table. That chain
 * is the point: a path or a response field that changes on the server
 * becomes a TypeScript error here, at build time, instead of `undefined` in
 * a component at runtime.
 *
 * This is a thin layer over the existing axios instance in `lib/api`, not a
 * replacement for it. That instance already owns token attachment, refresh
 * on 401 and the tenant header; re-implementing any of that here would give
 * the app two auth paths that could disagree — and the one used by generated
 * calls would be the less-tested of the two.
 *
 * Scope note: the backend currently annotates only some routes with
 * `@validate_response`, so many operations resolve to a `default` response
 * with no schema. `ApiResponse` degrades to `unknown` for those rather than
 * inventing a shape — an `any` would type-check every misuse of an
 * undocumented body and defeat the reason for generating types at all. As
 * routes gain response models the types tighten with no change here.
 */

import api from "../lib/api";
import type { paths } from "./schema";

/** Every path string the API documents. */
export type ApiPath = keyof paths;

/** HTTP methods, as the generated schema spells them. */
export type HttpMethod = "get" | "post" | "put" | "delete" | "patch";

/** Paths that document the given method. */
export type PathsWith<M extends HttpMethod> = {
  [P in ApiPath]: paths[P] extends Record<M, unknown> ? P : never;
}[ApiPath];

type Operation<P extends ApiPath, M extends HttpMethod> = paths[P] extends {
  [K in M]: infer O;
}
  ? O
  : never;

/**
 * The 2xx body an operation documents, or `unknown` when it documents none.
 *
 * `unknown` (not `any`) is deliberate: callers must narrow before use, which
 * is exactly the pressure needed to get the remaining routes annotated.
 */
export type ApiResponse<P extends ApiPath, M extends HttpMethod> =
  Operation<P, M> extends {
    responses: { 200: { content: { "application/json": infer B } } };
  }
    ? B
    : Operation<P, M> extends {
          responses: { 201: { content: { "application/json": infer B } } };
        }
      ? B
      : unknown;

/** The request body an operation documents, or `never` when it takes none. */
export type ApiRequestBody<P extends ApiPath, M extends HttpMethod> =
  Operation<P, M> extends {
    requestBody: { content: { "application/json": infer B } };
  }
    ? B
    : never;

/**
 * The axios instance is configured with `baseURL: "/api/v1"`, but the OpenAPI
 * document keys paths by their absolute form. Stripping the prefix here means
 * call sites use the documented path verbatim — no mental translation, and no
 * class of bug where a caller passes the already-stripped form and silently
 * requests `/api/v1/api/v1/...`.
 */
const BASE_PREFIX = "/api/v1";

function toRequestUrl(path: string): string {
  return path.startsWith(BASE_PREFIX) ? path.slice(BASE_PREFIX.length) : path;
}

/**
 * Substitute `{param}` placeholders in a documented path.
 *
 * Values are URL-encoded. A tenant slug or external id can legitimately
 * contain a slash or a question mark, and interpolating one raw would let it
 * change which endpoint is called.
 */
export function buildPath(
  path: string,
  params: Record<string, string | number> = {},
): string {
  return path.replace(/\{([^}]+)\}/g, (_match, key: string) => {
    const value = params[key];
    if (value === undefined) {
      throw new Error(
        `[PortalClient] Missing path parameter "${key}" for ${path}`,
      );
    }
    return encodeURIComponent(String(value));
  });
}

export interface RequestOptions {
  /** Values for `{param}` placeholders in the path. */
  path?: Record<string, string | number>;
  /** Query string parameters. */
  query?: Record<string, unknown>;
}

/**
 * Typed request helpers.
 *
 * Each takes a path that the generated schema confirms documents that method,
 * so a typo or a removed endpoint fails the build rather than 404-ing in
 * production.
 */
export const portal = {
  async get<P extends PathsWith<"get">>(
    path: P,
    options: RequestOptions = {},
  ): Promise<ApiResponse<P, "get">> {
    const response = await api.get(
      toRequestUrl(buildPath(path as string, options.path)),
      { params: options.query },
    );
    return response.data as ApiResponse<P, "get">;
  },

  async post<P extends PathsWith<"post">>(
    path: P,
    body?: ApiRequestBody<P, "post"> | Record<string, unknown>,
    options: RequestOptions = {},
  ): Promise<ApiResponse<P, "post">> {
    const response = await api.post(
      toRequestUrl(buildPath(path as string, options.path)),
      body,
      { params: options.query },
    );
    return response.data as ApiResponse<P, "post">;
  },

  async put<P extends PathsWith<"put">>(
    path: P,
    body?: ApiRequestBody<P, "put"> | Record<string, unknown>,
    options: RequestOptions = {},
  ): Promise<ApiResponse<P, "put">> {
    const response = await api.put(
      toRequestUrl(buildPath(path as string, options.path)),
      body,
      { params: options.query },
    );
    return response.data as ApiResponse<P, "put">;
  },

  async delete<P extends PathsWith<"delete">>(
    path: P,
    options: RequestOptions = {},
  ): Promise<ApiResponse<P, "delete">> {
    const response = await api.delete(
      toRequestUrl(buildPath(path as string, options.path)),
      { params: options.query },
    );
    return response.data as ApiResponse<P, "delete">;
  },
};

export default portal;
