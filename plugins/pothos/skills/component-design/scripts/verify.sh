#!/usr/bin/env bash
# Run type-check and tests without modifying the project.
#
#   verify.sh <project-dir> [overlay-dir]   copy the project to a scratch folder, link node_modules
#                                           package by package, lay overlay-dir/src over it, run the
#                                           project's type-check and the tests of the overlaid files
#   verify.sh --minimal <dir>               no project: run <dir>/src in a throwaway React 18 +
#                                           TypeScript + Vitest + Testing Library project (toolchain
#                                           cached by scripts/toolchain.sh)
#
# Linking node_modules package by package matters: linking the whole folder lets Vite and other
# tools write caches into the original project.
set -euo pipefail
SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/component-verify.XXXXXX")"
trap 'rm -rf "$SCRATCH"' EXIT

if [[ "${1:-}" == "--minimal" ]]; then
  SRC="$(cd "${2:?usage: verify.sh --minimal <dir>}" && pwd)"
  [[ -d "$SRC/src" ]] || { echo "$SRC has no src/: put the component and its tests under src/." >&2; exit 1; }
  TC="$("$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/toolchain.sh")"
  cd "$SCRATCH"
  cat > tsconfig.json <<'JSON'
{ "compilerOptions": { "target": "ES2022", "lib": ["ES2022", "DOM", "DOM.Iterable"], "module": "ESNext",
  "moduleResolution": "bundler", "jsx": "react-jsx", "strict": true, "noEmit": true, "skipLibCheck": true,
  "types": ["vitest/globals", "@testing-library/jest-dom"] }, "include": ["src", "env.d.ts"] }
JSON
  printf "declare module '*.module.css' { const c: Record<string, string>; export default c; }\ndeclare module '*.css';\n" > env.d.ts
  printf "import { defineConfig } from 'vitest/config';\nexport default defineConfig({ cacheDir: './.vite-cache', test: { environment: 'jsdom', globals: true, setupFiles: ['./setup.ts'], include: ['src/**/*.test.{ts,tsx}'], css: { modules: { classNameStrategy: 'non-scoped' } } } });\n" > vitest.config.ts
  echo "import '@testing-library/jest-dom/vitest';" > setup.ts
  cp -R "$SRC/src" src
  mkdir node_modules
  for p in "$TC"/node_modules/* "$TC"/node_modules/.bin; do [[ -e "$p" ]] && ln -sf "$p" node_modules/; done
  echo "== type-check"; ./node_modules/.bin/tsc --noEmit -p .
  echo "== tests"; ./node_modules/.bin/vitest run
  exit 0
fi

PROJECT="$(cd "${1:?usage: verify.sh <project-dir> [overlay-dir]}" && pwd)"
OVERLAY="${2:-}"
[[ -d "$PROJECT/node_modules" ]] || { echo "No node_modules in $PROJECT: install the project's dependencies first." >&2; exit 1; }
if [[ -n "$OVERLAY" ]]; then
  [[ -d "$OVERLAY/src" ]] || { echo "Overlay $OVERLAY has no src/: put the files to verify under src/ as they sit in the project." >&2; exit 1; }
fi
rsync -a --exclude node_modules --exclude .git --exclude build --exclude dist --exclude .next "$PROJECT"/ "$SCRATCH"/
mkdir -p "$SCRATCH/node_modules"
for p in "$PROJECT"/node_modules/* "$PROJECT"/node_modules/.bin; do [[ -e "$p" ]] && ln -s "$p" "$SCRATCH/node_modules/"; done
TESTS=()
if [[ -n "$OVERLAY" ]]; then
  OVERLAY="$(cd "$OVERLAY" && pwd)"
  while IFS= read -r f; do
    rel="${f#"$OVERLAY"/}"; mkdir -p "$SCRATCH/$(dirname "$rel")"; cp "$f" "$SCRATCH/$rel"
    [[ "$rel" =~ \.(test|spec)\.[jt]sx?$ ]] && TESTS+=("$rel")
  done < <(find "$OVERLAY/src" -type f ! -name '*excerpt*')
fi
cd "$SCRATCH"
script() { node -e "const s=require('./package.json').scripts||{};const k=process.argv.slice(1).find(n=>s[n]);if(k)console.log(k)" "$@"; }
TC_SCRIPT="$(script type-check typecheck tsc check-types || true)"
echo "== type-check"
if [[ -n "$TC_SCRIPT" ]]; then npm run --silent "$TC_SCRIPT"; else ./node_modules/.bin/tsc --noEmit; fi
echo "== tests"
# ${TESTS[@]+"${TESTS[@]}"}: bash 3.2 (macOS) treats an empty array as unset under set -u.
if [[ -x node_modules/.bin/vitest ]]; then ./node_modules/.bin/vitest run ${TESTS[@]+"${TESTS[@]}"}
elif [[ -x node_modules/.bin/jest ]]; then ./node_modules/.bin/jest ${TESTS[@]+"${TESTS[@]}"}
else echo "No vitest or jest found: run the project's tests by hand and say so."; exit 1; fi
