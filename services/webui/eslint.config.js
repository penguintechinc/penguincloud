import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";

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
    // eslint-plugin-react-hooks is registered explicitly: it ships no flat
    // config export at 5.1.0, and without registration `rules-of-hooks` and
    // `exhaustive-deps` never run at all.
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // Kept at "error" — this configures the underscore convention for
      // arguments that must exist but go unused, it does not weaken the rule.
      // Express identifies error-handling middleware by arity (fn.length === 4),
      // so dropping `_next` would silently demote it to ordinary middleware.
      "@typescript-eslint/no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
        },
      ],
    },
  },
);
