/**
 * `describeMutationError` decides what an operator sees after a rejected
 * save by PROVENANCE, not by pattern-matching the string — see the
 * function's own doc comment for why a content-shape denylist cannot work
 * here. These tests prove both directions: every upstream-forwarded body is
 * replaced with the generic message regardless of what it contains
 * (including strings a denylist would have missed), and every
 * portal-generated body is shown verbatim (including validation errors a
 * denylist previously suppressed).
 */
import {
  describeMutationError,
  GENERIC_MUTATION_ERROR_MESSAGE,
} from "../mutationError";

/** A portal-native error response: no upstream-provenance marker. */
function portalError(data: unknown): unknown {
  return { isAxiosError: true, response: { data, headers: {} } };
}

/**
 * A response the proxy marked as forwarded from a connected product — see
 * `UPSTREAM_RESPONSE_HEADER` in services/portal-api/app/proxy.py.
 */
function upstreamError(data: unknown): unknown {
  return {
    isAxiosError: true,
    response: {
      data,
      headers: { "x-portal-upstream-response": "true" },
    },
  };
}

describe("describeMutationError — upstream-forwarded responses", () => {
  // The reviewer's seven strings: every one of these passed the previous
  // denylist's LEAK_PATTERNS and rendered verbatim. None contain a scheme,
  // a dotted hostname, or an IPv4 octet, so no regex extension closes this
  // — only providing they are marked as originating from the proxy does.
  it.each([
    [
      "a dotless in-cluster service name",
      "connection refused: gough-api-primary:8080",
    ],
    [
      "namespace + workload topology",
      "upstream nest-postgres-0 in namespace penguincloud-prod is down",
    ],
    ["an IPv6 address", "Upstream unreachable at 2001:db8:85a3::8a2e:370:7334"],
    [
      "a dotless filesystem path",
      "Permission denied writing /etc/portal/secrets/upstream",
    ],
    // Deliberately low-entropy and not a real vendor key format — gitleaks
    // correctly flags anything that reads as an actual secret, even in
    // fixture data. The point under test is any credential-labelled string,
    // which content shape can no longer save regardless of what it says.
    [
      "a raw live credential",
      "Invalid credential: example placeholder value not a real key",
    ],
    [
      "a FATAL auth message naming a host",
      'FATAL: password authentication failed for user "nest_rw" on host db-primary',
    ],
    ["an already-redacted marker", "auth failed: [REDACTED]"],
  ])("never displays %s verbatim", (_label, leaky) => {
    const message = describeMutationError(upstreamError({ error: leaky }));
    expect(message).toBe(GENERIC_MUTATION_ERROR_MESSAGE);
    expect(message).not.toContain(leaky);
  });

  it("replaces the body even when it looks like an ordinary short message", () => {
    // Provenance decides, not content — an innocuous-looking upstream body
    // is still never trusted, since the next one might not be innocuous.
    const message = describeMutationError(
      upstreamError({ error: "resource not found" }),
    );
    expect(message).toBe(GENERIC_MUTATION_ERROR_MESSAGE);
  });
});

describe("describeMutationError — portal-generated responses", () => {
  // I4: these are exactly the shape the previous denylist suppressed —
  // dotted field paths are the standard JSON-API validation idiom, and the
  // hostname pattern could not tell "config.timeout" from a domain name.
  it.each([
    "config.timeout must be a positive integer",
    "spec.replicas must be greater than zero",
    "policy.rules is required",
  ])("shows a portal validation error verbatim: %s", (validationMessage) => {
    expect(
      describeMutationError(portalError({ error: validationMessage })),
    ).toBe(validationMessage);
  });

  it("shows a portal-shaped { error } message", () => {
    expect(
      describeMutationError(portalError({ error: "Route not allowed" })),
    ).toBe("Route not allowed");
  });

  it("falls back to a { message } field when error is absent", () => {
    expect(
      describeMutationError(
        portalError({ message: "Insufficient permissions" }),
      ),
    ).toBe("Insufficient permissions");
  });

  it("prefers error over message when both are present", () => {
    expect(
      describeMutationError(
        portalError({ error: "Route not allowed", message: "ignored" }),
      ),
    ).toBe("Route not allowed");
  });

  it("falls back to the generic message for a response with no recognised field", () => {
    expect(describeMutationError(portalError({ detail: "whatever" }))).toBe(
      GENERIC_MUTATION_ERROR_MESSAGE,
    );
  });

  it("falls back to the generic message for an empty string", () => {
    expect(describeMutationError(portalError({ error: "" }))).toBe(
      GENERIC_MUTATION_ERROR_MESSAGE,
    );
  });

  it("refuses a message over the length cap rather than truncating it", () => {
    const long = "x".repeat(201);
    expect(describeMutationError(portalError({ error: long }))).toBe(
      GENERIC_MUTATION_ERROR_MESSAGE,
    );
  });
});

describe("describeMutationError — non-response errors", () => {
  it("shows a client-generated Error message verbatim", () => {
    // The guard every product mutation hook throws (useTobogganingMutation,
    // useGoughMutation, useDatabaseMutations) — never proxied, always safe.
    expect(
      describeMutationError(
        new Error("No Tobogganing connection for the active tenant"),
      ),
    ).toBe("No Tobogganing connection for the active tenant");
  });

  it("falls back to the generic message for an empty Error message", () => {
    expect(describeMutationError(new Error(""))).toBe(
      GENERIC_MUTATION_ERROR_MESSAGE,
    );
  });

  it("falls back to the generic message for a network error with no response", () => {
    expect(describeMutationError({ isAxiosError: true })).toBe(
      GENERIC_MUTATION_ERROR_MESSAGE,
    );
  });

  it("falls back to the generic message for a non-Error, non-axios value", () => {
    expect(describeMutationError("boom")).toBe(GENERIC_MUTATION_ERROR_MESSAGE);
    expect(describeMutationError(null)).toBe(GENERIC_MUTATION_ERROR_MESSAGE);
    expect(describeMutationError(undefined)).toBe(
      GENERIC_MUTATION_ERROR_MESSAGE,
    );
  });
});
