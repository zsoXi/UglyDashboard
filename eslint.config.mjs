import js from '@eslint/js';
import globals from 'globals';

export default [
  { ignores: ['web/dist/**', 'artifacts/**', '.venv/**', 'node_modules/**'] },
  {
    files: ['web/app.js', 'web/i18n/*.js'],
    languageOptions: { ecmaVersion: 'latest', sourceType: 'module', globals: globals.browser },
    rules: {
      ...js.configs.recommended.rules,
      'no-unused-vars': ['error', { argsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' }],
      eqeqeq: ['error', 'always', { null: 'ignore' }],
    },
  },
  {
    files: ['scripts/*.mjs', '*.config.mjs', 'tests/*.mjs'],
    languageOptions: { ecmaVersion: 'latest', sourceType: 'module', globals: globals.node },
    rules: { ...js.configs.recommended.rules },
  },
];
