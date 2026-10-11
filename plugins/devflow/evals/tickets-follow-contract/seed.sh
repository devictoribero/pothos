#!/usr/bin/env bash
set -euo pipefail
cd "${1:-$PWD}"
git init -q -b main .
git config user.email eval@example.com
git config user.name eval
git remote add origin https://github.com/acme/vetapp.git
mkdir -p .devflow-home/contracts/github.com/acme "$(dirname "$PWD")/.config"
ln -s "$PWD/.devflow-home" "$(dirname "$PWD")/.config/devflow"
echo ".devflow-home" >> .git/info/exclude
cat > .devflow-home/contracts/github.com/acme/vetapp.json <<'JSON'
{"version": 1, "verify": {"full": "npm test"}, "tracker": {"kind": "local", "path": "work"}}
JSON
cat > package.json <<'JSON'
{"name": "vetapp", "private": true, "scripts": {"test": "node --test"}}
JSON
mkdir -p src
cat > src/appointments.js <<'JS'
// Appointments are stored in memory for now.
const appointments = [];
export function book(petId, startsAt) {
  appointments.push({ petId, startsAt });
  return appointments.length;
}
export function list() {
  return [...appointments];
}
JS
git add -A && git commit -q -m "initial"
