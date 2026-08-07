import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "dist",
      "build",
      "node_modules",
      "jest.config.js",
      "playwright.config.ts",
    ],
  },
  {
    extends: [...tseslint.configs.recommended],
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2020,
      sourceType: "module",
    },
    rules: {
      "@typescript-eslint/no-explicit-any": "off", // TODO: add proper types to existing code
      "@typescript-eslint/no-unused-vars": "off", // TODO: clean up unused vars
      "react-hooks/exhaustive-deps": "off", // TODO: fix useEffect dependencies in existing code
    },
  },
);
