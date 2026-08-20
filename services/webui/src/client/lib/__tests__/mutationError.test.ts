/**
 * `describeMutationError` is the only place deciding what an operator sees
 * after a rejected save — most mutations reach a product through the portal's
 * proxy, which forwards an upstream error body mostly verbatim (see
 * `services/portal-api/app/proxy.py`). These tests pin both directions: a
 * short, portal-shaped message is shown, and anything that looks like it
 * leaked operational detail is not.
 */
import {
  describeMutationError,
  GENERIC_MUTATION_ERROR_MESSAGE,
} from "../mutationError";

function axiosError(data: unknown): unknown {
  return { isAxiosError: true, response: { data } };
}

describe("describeMutationError", () => {
  it("shows a portal-shaped { error } message", () => {
    expect(
      describeMutationError(axiosError({ error: "Route not allowed" })),
    ).toBe("Route not allowed");
  });

  it("falls back to a { message } field when error is absent", () => {
    expect(
      describeMutationError(
        axiosError({ message: "Insufficient permissions" }),
      ),
    ).toBe("Insufficient permissions");
  });

  it("prefers error over message when both are present", () => {
    expect(
      describeMutationError(
        axiosError({ error: "Route not allowed", message: "ignored" }),
      ),
    ).toBe("Route not allowed");
  });

  it("shows a client-generated Error message verbatim", () => {
    // The guard every product mutation hook throws (useTobogganingMutation,
    // useGoughMutation, useDatabaseMutations) — never proxied, always safe.
    expect(
      describeMutationError(
        new Error("No Tobogganing connection for the active tenant"),
      ),
    ).toBe("No Tobogganing connection for the active tenant");
  });

  it("falls back to the generic message for a response with no recognised field", () => {
    expect(describeMutationError(axiosError({ detail: "whatever" }))).toBe(
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

  it("falls back to the generic message for an empty string", () => {
    expect(describeMutationError(axiosError({ error: "" }))).toBe(
      GENERIC_MUTATION_ERROR_MESSAGE,
    );
    expect(describeMutationError(new Error(""))).toBe(
      GENERIC_MUTATION_ERROR_MESSAGE,
    );
  });

  it("refuses a message over the length cap rather than truncating it", () => {
    const long = "x".repeat(201);
    expect(describeMutationError(axiosError({ error: long }))).toBe(
      GENERIC_MUTATION_ERROR_MESSAGE,
    );
  });

  it.each([
    ["a URL", "connect to https://gough-internal.svc.cluster.local failed"],
    [
      "a multi-label hostname",
      "upstream host gough-internal.example.com refused",
    ],
    ["a single-dot hostname", "could not reach gough.local"],
    ["an IPv4 address", "connection to 10.0.4.17 timed out"],
    ["an already-redacted marker", "auth failed: [REDACTED]"],
  ])("refuses a message containing %s", (_label, leaky) => {
    expect(describeMutationError(axiosError({ error: leaky }))).toBe(
      GENERIC_MUTATION_ERROR_MESSAGE,
    );
  });

  it("does not flag an ordinary abbreviation or version string as a leak", () => {
    expect(
      describeMutationError(
        axiosError({ error: "invalid category, e.g. malware" }),
      ),
    ).toBe("invalid category, e.g. malware");
  });
});
