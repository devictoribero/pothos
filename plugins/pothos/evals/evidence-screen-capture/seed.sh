#!/usr/bin/env bash
# A mobile app in a monorepo with a capture command that stands in for the real web tier: it writes a PNG per
# screen and language and prints the paths, so the eval checks the skill's steps,
# not a browser.
set -euo pipefail
cd "${1:-$PWD}"
git init -q -b main .
git config user.email eval@example.com
git config user.name eval
git remote add origin https://github.com/acme/pets.git
mkdir -p .pothos-home/contracts/github.com/acme "$(dirname "$PWD")/.config"
ln -sfn "$PWD/.pothos-home" "$(dirname "$PWD")/.config/pothos"
printf '.pothos-home\n' >> .git/info/exclude
cat > .pothos-home/contracts/github.com/acme/pets.json <<'JSON'
{
  "version": 1,
  "verify": {"full": "node --test"},
  "run": {
    "apps": [{
      "name": "mobile", "path": "apps/mobile", "screenshots": "android-emulator",
      "capture": {"command": "node apps/mobile/scripts/screenshot/capture.js", "doc": "apps/mobile/docs/screenshots.md"},
      "ui": {
        "components": ["apps/mobile/components"], "tokens": ["apps/mobile/shared/theme"],
        "screens": ["apps/mobile/features/*/screens", "apps/mobile/app/**/_layout.tsx"],
        "locales": ["apps/mobile/shared/i18n/locales"], "languages": ["es", "ca"]
      }
    }]
  },
  "pr": {"base": "main"}
}
JSON
mkdir -p apps/mobile/features/pet/screens apps/mobile/features/home/screens apps/mobile/components/primitives/Badge apps/mobile/shared/i18n/locales apps/mobile/scripts/screenshot/scenarios apps/mobile/docs test
cat > package.json <<'JSON'
{"name": "pets", "private": true}
JSON
cat > test/noop.test.js <<'JS'
const { test } = require('node:test');
test('noop', () => {});
JS
cat > apps/mobile/features/pet/screens/PetScreen.tsx <<'TSX'
import { Badge } from '@/primitives/Badge/Badge';
export const PetScreen = () => <Badge label="vaccinated" />;
TSX
cat > apps/mobile/features/home/screens/HomeScreen.tsx <<'TSX'
export const HomeScreen = () => null;
TSX
cat > apps/mobile/components/primitives/Badge/Badge.tsx <<'TSX'
export const Badge = ({ label }: { label: string }) => <span>{label}</span>;
TSX
cat > apps/mobile/shared/i18n/locales/es.ts <<'TS'
export const es = { pet: { vaccinated: 'Vacunada' } };
TS
cat > apps/mobile/shared/i18n/locales/ca.ts <<'TS'
export const ca = { pet: { vaccinated: 'Vacunada' } };
TS
cat > apps/mobile/docs/screenshots.md <<'MD'
# Screenshots without a device

`node apps/mobile/scripts/screenshot/capture.js <scenario>... [--lang es,ca] [--out DIR]` renders a
scenario in a headless browser and prints one image path per line. Scenarios are the files under
`apps/mobile/scripts/screenshot/scenarios/`: `pet` is the pet screen, `home` the home tab.
It cannot show font scale or native surfaces.
MD
cat > apps/mobile/scripts/screenshot/scenarios/pet.ts <<'TS'
export const scenario = { path: '/pet/pet-1' };
TS
cat > apps/mobile/scripts/screenshot/scenarios/home.ts <<'TS'
export const scenario = { path: '/hogar' };
TS
cat > apps/mobile/scripts/screenshot/capture.js <<'JS'
// Stand-in for the web screenshot tier: a 1x1 PNG per scenario and language, named like the real one.
const fs = require('fs');
const path = require('path');
const args = process.argv.slice(2);
const flag = (name, fallback) => (args.includes(name) ? args[args.indexOf(name) + 1] : fallback);
const out = path.resolve(flag('--out', '.context/screenshots'));
const langs = flag('--lang', 'es').split(',');
const names = args.filter((a, i) => !a.startsWith('--') && (i === 0 || !['--out', '--lang'].includes(args[i - 1])));
if (names.length === 0) { console.error('usage: capture.js <scenario>... [--lang es,ca] [--out DIR]'); process.exit(64); }
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==', 'base64');
fs.mkdirSync(out, { recursive: true });
for (const name of names) {
  if (!fs.existsSync(path.join(__dirname, 'scenarios', `${name}.ts`))) { console.error(`no scenario named ${name}; known: pet, home`); process.exit(1); }
  for (const lang of langs) {
    const file = path.join(out, `${name}-${lang}.png`);
    fs.writeFileSync(file, PNG);
    console.log(file);
  }
}
JS
git add -A && git commit -q -m "chore: pets app"
git checkout -q -b badge-tone
cat > apps/mobile/components/primitives/Badge/Badge.tsx <<'TSX'
export const Badge = ({ label }: { label: string }) => <span style={{ color: 'green' }}>{label}</span>;
TSX
cat > apps/mobile/shared/i18n/locales/ca.ts <<'TS'
export const ca = { pet: { vaccinated: 'Vacunada i al dia' } };
TS
git add -A && git commit -q -m "feat(mobile): badge tone and catalan copy"
