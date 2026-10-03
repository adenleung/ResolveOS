import js from "@eslint/js";
import ts from "typescript-eslint";
import hooks from "eslint-plugin-react-hooks";
import globals from "globals";
export default [
  {ignores: [".next/**", "node_modules/**", "test-results/**", "playwright-report/**", "next-env.d.ts"]},
  js.configs.recommended, ...ts.configs.recommended,
  {languageOptions: {globals: {...globals.browser, ...globals.node}}},
  {files: ["src/**/*.tsx", "src/**/*.ts"], plugins: {"react-hooks": hooks}, rules: hooks.configs.recommended.rules},
];
