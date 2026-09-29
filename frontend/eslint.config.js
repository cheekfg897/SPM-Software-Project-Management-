import js from '@eslint/js'
import comments from '@eslint-community/eslint-plugin-eslint-comments/configs'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist', 'coverage', 'playwright-report', 'test-results', 'public'] },
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommendedTypeChecked,
      comments.recommended,
      reactHooks.configs.flat.recommended,
    ],
    languageOptions: {
      ecmaVersion: 2022,
      globals: { ...globals.browser, ...globals.node },
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    plugins: { 'react-refresh': reactRefresh },
    rules: {
      // No `any` unless there is no other way; then disable the rule on that line with a
      // reason after `--`, which require-description enforces (frontend/CLAUDE.md §Types).
      '@typescript-eslint/no-explicit-any': 'error',
      '@eslint-community/eslint-comments/require-description': ['error', { ignore: [] }],
      '@eslint-community/eslint-comments/no-unused-disable': 'error',

      '@typescript-eslint/consistent-type-imports': 'error',
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],

      // The backend is reached through src/lib/api only (frontend/CLAUDE.md §Talking to the backend).
      'no-restricted-globals': [
        'error',
        { name: 'fetch', message: 'Call the backend through apiRequest in @/lib/api.' },
      ],
      'no-restricted-imports': [
        'error',
        { paths: [{ name: 'react-router-dom', message: 'Import from react-router (v8).' }] },
      ],
    },
  },
  {
    // Tests and their helpers are never hot-reloaded.
    files: ['src/test/**', '**/*.test.{ts,tsx}'],
    rules: { 'react-refresh/only-export-components': 'off' },
  },
  {
    files: ['src/lib/api/client.ts'],
    rules: { 'no-restricted-globals': 'off' },
  },
)
