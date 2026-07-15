import js from "@eslint/js";
import globals from "globals";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import jsxA11y from "eslint-plugin-jsx-a11y";

/**
 * 디자인·접근성 정적 검사(jsx-a11y) + React 훅 규칙.
 * 개발 시 Vite 오버레이(vite-plugin-checker)로 브라우저에도 표시됩니다.
 */
export default [
  { ignores: ["dist/**", "node_modules/**"] },
  js.configs.recommended,
  react.configs.flat.recommended,
  reactHooks.configs.flat.recommended,
  jsxA11y.flatConfigs.recommended,
  {
    files: ["**/*.{js,jsx}"],
    languageOptions: {
      globals: { ...globals.browser },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    settings: { react: { version: "detect" } },
    rules: {
      // Vite uses React's automatic JSX runtime; importing React in every JSX file is unnecessary.
      "react/react-in-jsx-scope": "off",
      // React Compiler를 사용하지 않는 React 18 앱이므로 compiler 전용 권고 규칙은 제외합니다.
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/preserve-manual-memoization": "off",
      // PropTypes 미사용 프로젝트
      "react/prop-types": "off",
      // 기존 단일 파일 UI: 점진 적용 — 치명적이지 않은 규칙은 완화
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
      "jsx-a11y/click-events-have-key-events": "warn",
      "jsx-a11y/no-static-element-interactions": "warn",
      "jsx-a11y/label-has-associated-control": "warn",
      "jsx-a11y/anchor-is-valid": "warn",
    },
  },
  {
    files: ["**/*.test.{js,jsx}"],
    languageOptions: { globals: { ...globals.node } },
  },
];
