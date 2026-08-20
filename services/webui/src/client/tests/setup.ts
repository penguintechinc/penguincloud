import "@testing-library/jest-dom";

// `setupFilesAfterEnv` runs for every test file regardless of that file's own
// `@jest-environment` pragma — most of the suite is jsdom, but
// `mocks/__tests__/handlers.contract.test.ts` opts into `node` (msw reads
// Fetch API globals jsdom does not provide), so `window` is genuinely absent
// there. Guarded rather than assumed.
if (typeof window !== "undefined") {
  // Mock window.matchMedia
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: jest.fn().mockImplementation((query) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: jest.fn(),
      removeListener: jest.fn(),
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
      dispatchEvent: jest.fn(),
    })),
  });
}

// Note: MSW setup deferred to integration tests that actually need it.
// Unit tests of kit components don't require API mocking.

// Suppress console errors during tests (optional)
const originalError = console.error;
beforeAll(() => {
  console.error = (...args: unknown[]) => {
    if (
      typeof args[0] === "string" &&
      args[0].includes("Warning: ReactDOM.render")
    ) {
      return;
    }
    originalError.call(console, ...args);
  };
});

afterAll(() => {
  console.error = originalError;
});
