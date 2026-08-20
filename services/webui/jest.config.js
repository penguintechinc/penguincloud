export default {
  preset: "ts-jest",
  testEnvironment: "jsdom",
  roots: ["<rootDir>/src"],
  testMatch: ["**/__tests__/**/*.ts?(x)", "**/?(*.)+(spec|test).ts?(x)"],
  // Playwright specs live under src and match testMatch; jest cannot load
  // @playwright/test, so they are excluded here and run via `npm run test:e2e`.
  testPathIgnorePatterns: ["/node_modules/", "/src/client/tests/e2e/"],
  moduleFileExtensions: ["ts", "tsx", "js", "jsx", "json", "node"],
  moduleNameMapper: {
    "\\.(css|less|scss|sass)$": "identity-obj-proxy",
    // react-libs publishes an exports map with only an "import" condition, so
    // jest's resolver cannot find an entry point. Point it straight at the ESM
    // build and let the transform below convert it.
    "^@penguintechinc/react-libs$":
      "<rootDir>/node_modules/@penguintechinc/react-libs/dist/index.js",
    // lib/viteEnv is the only module touching `import.meta`, which jest's CJS
    // transform cannot parse; the stub reads process.env instead.
    viteEnv$: "<rootDir>/src/client/test/__mocks__/viteEnv.ts",
    "^lucide-react$": "<rootDir>/src/client/test/__mocks__/lucide-react.tsx",
    "^react-router$": "<rootDir>/src/client/test/__mocks__/react-router.tsx",
    "^react-router-dom$":
      "<rootDir>/src/client/test/__mocks__/react-router.tsx",
  },
  setupFilesAfterEnv: ["<rootDir>/src/client/tests/setup.ts"],
  // Scope deliberately matches coverageThreshold below. Collecting from all of
  // src/client while only thresholding a subset reported a misleading
  // whole-app percentage that no threshold actually enforced.
  collectCoverageFrom: [
    "src/client/components/kit/**/*.{ts,tsx}",
    "src/client/api/**/*.{ts,tsx}",
    "src/client/lib/**/*.{ts,tsx}",
    // Only the new mutationErrorStore, not stores/** broadly: tenantStore.ts
    // predates this gate, has no dedicated unit test of its own (only
    // indirect coverage via other components' mocks), and gating the whole
    // directory would fail it immediately for pre-existing, out-of-scope
    // reasons — see M2 in the mutation-error-surfacing review, which asked
    // for the NEW logic to be covered, not a retroactive audit of the rest
    // of the folder.
    "src/client/stores/mutationErrorStore.ts",
    "!src/client/**/*.d.ts",
    "!src/client/components/kit/index.ts", // Barrel exports have no behavior to test
    // Bundler-only `import.meta` access; stubbed in tests, so the real body
    // never executes under jest (see moduleNameMapper above).
    "!src/client/lib/viteEnv.ts",
  ],
  coverageThreshold: {
    "src/client/components/kit/**": {
      branches: 90,
      functions: 90,
      lines: 90,
      statements: 90,
    },
    "src/client/api/**": {
      branches: 90,
      functions: 90,
      lines: 90,
      statements: 90,
    },
    "src/client/lib/**": {
      branches: 90,
      functions: 90,
      lines: 90,
      statements: 90,
    },
    "src/client/stores/mutationErrorStore.ts": {
      branches: 90,
      functions: 90,
      lines: 90,
      statements: 90,
    },
  },
  transform: {
    // msw's dependency tree ships plain ESM .mjs files (rettime) alongside
    // .js/.ts — widened from `[jt]sx?` so those get the same transform
    // instead of falling through untransformed and hitting jest's default
    // CJS parse of a bare `import` statement.
    "^.+\\.[cm]?[jt]sx?$": [
      "ts-jest",
      {
        useESM: true,
        tsconfig: {
          jsx: "react-jsx",
          esModuleInterop: true,
          allowSyntheticDefaultImports: true,
          allowJs: true,
          module: "esnext",
        },
      },
    ],
  },
  extensionsToTreatAsEsm: [".ts", ".tsx"],
  // msw ships ESM-only and pulls in a tree of ESM-only runtime dependencies
  // of its own — added so `mocks/handlers.ts` can be imported by a jest test
  // at all; see mocks/__tests__/handlers.contract.test.ts.
  transformIgnorePatterns: [
    "node_modules/(?!(react-router|react-router-dom|@penguintechinc|msw|@mswjs|@open-draft|rettime|statuses|headers-polyfill|is-node-process|outvariant|path-to-regexp|strict-event-emitter|until-async|cookie)/)",
  ],
};
