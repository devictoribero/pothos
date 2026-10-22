# Working in this project

- `src/ui/`: shared UI primitives, one folder per component with its contract (`README.md`), styles (CSS Modules) and tests. Exported from `src/ui/index.ts`. Design tokens in `src/ui/tokens.css`, imported once by the app shell (not part of this fixture); a preview imports it itself.
- `src/hooks/`: hooks shared across features.
- `src/features/<area>/`: feature components, composed from `src/ui`.
- Tests: Vitest + Testing Library (`npm test`). Type-check: `npm run typecheck`. Both must pass before a change is done.
- Tests are written as given / when / then with plain-language names.
