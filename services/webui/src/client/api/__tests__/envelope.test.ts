/**
 * The shared envelope readers.
 *
 * `envelopeList` is exercised incidentally by every product's api tests, but
 * `envelopeString` is new and its whole purpose is the branch that REFUSES —
 * so the refusals are asserted directly rather than through a screen. Each
 * message is checked too: "no key" and "wrong type" have to be
 * distinguishable in a stack trace, or the operator's bug report says only
 * that the preview did not load.
 */

import { envelopeList, envelopeString } from "../envelope";

describe("envelopeString", () => {
  it("returns the value under the key", () => {
    expect(envelopeString({ html: "<h1>hi</h1>" }, "html")).toBe("<h1>hi</h1>");
  });

  it("returns an empty string the product genuinely sent", () => {
    // The point of the helper is telling "" apart from absent. A page that
    // really renders to nothing must still come back as "", not throw.
    expect(envelopeString({ html: "" }, "html")).toBe("");
  });

  it.each([
    ["null", null],
    ["undefined", undefined],
    ["a string", "not an object"],
    ["an array", [{ html: "x" }]],
  ])("refuses %s as an envelope", (_label, payload) => {
    expect(() => envelopeString(payload, "html")).toThrow(
      /no envelope object carrying "html"/,
    );
  });

  it("refuses an absent key rather than rendering blank", () => {
    expect(() => envelopeString({ rendered: "<h1/>" }, "html")).toThrow(
      /no "html" key in the response — refusing to render it as blank/,
    );
  });

  it("logs the received key set for a developer rather than in the thrown message", () => {
    // C1: a client-generated Error is trusted verbatim by
    // describeMutationError, so the untrusted response's own key names stay
    // out of the message and go to the console instead.
    const spy = jest
      .spyOn(console, "error")
      .mockImplementation(() => undefined);

    expect(() => envelopeString({ rendered: "<h1/>" }, "html")).toThrow();

    expect(spy).toHaveBeenCalledWith('[envelope] Missing "html" key', [
      "rendered",
    ]);
    spy.mockRestore();
  });

  it("refuses a non-string under a present key", () => {
    expect(() => envelopeString({ html: { nested: true } }, "html")).toThrow(
      /non-string under "html"/,
    );
    expect(() => envelopeString({ html: null }, "html")).toThrow(
      /non-string under "html"/,
    );
  });
});

describe("envelopeList", () => {
  it("returns the rows under the key", () => {
    expect(envelopeList({ peers: [{ node_id: "a" }] }, "peers")).toEqual([
      { node_id: "a" },
    ]);
  });

  it("returns a genuinely empty list", () => {
    expect(envelopeList({ peers: [] }, "peers")).toEqual([]);
  });

  it.each([
    ["null", null],
    ["a bare array", [1, 2]],
  ])("refuses %s as an envelope", (_label, payload) => {
    expect(() => envelopeList(payload, "peers")).toThrow(
      /no envelope object carrying "peers"/,
    );
  });

  it("refuses an absent key rather than reporting none", () => {
    expect(() => envelopeList({ items: [] }, "peers")).toThrow(
      /no "peers" key in the response — refusing to report it as empty/,
    );
  });

  it("refuses a non-list under a present key", () => {
    expect(() => envelopeList({ peers: { node_id: "a" } }, "peers")).toThrow(
      /non-list under "peers"/,
    );
  });
});
