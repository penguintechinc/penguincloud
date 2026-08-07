export default {
  preset: "ts-jest",
  testEnvironment: "jsdom",
  roots: ["<rootDir>/src"],
  testMatch: ["**/__tests__/**/*.ts?(x)", "**/?(*.)+(spec|test).ts?(x)"],
  moduleFileExtensions: ["ts", "tsx", "js", "jsx", "json", "node"],
  moduleNameMapper: {
    "\\.(css|less|scss|sass)$": "identity-obj-proxy",
    "^lucide-react$": "<rootDir>/src/client/test/__mocks__/lucide-react.tsx",
  },
  setupFilesAfterEnv: ["<rootDir>/src/client/tests/setup.ts"],
  collectCoverageFrom: [
    "src/client/**/*.{ts,tsx}",
    "!src/client/**/*.d.ts",
    "!src/client/main.tsx",
    "!src/client/index.css",
    "!src/client/components/kit/index.ts", // Barrel exports have no behavior to test
  ],
  coverageThreshold: {
    // TODO: Expand scope to whole app after Phase 1F
    // Currently scoped to kit + api modules per brief requirement
    // lib/api.ts deferred for Phase 2 (complex interceptor testing)
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
  },
  transform: {
    "^.+\\.tsx?$": [
      "ts-jest",
      {
        tsconfig: {
          jsx: "react-jsx",
          esModuleInterop: true,
          allowSyntheticDefaultImports: true,
        },
      },
    ],
  },
};
