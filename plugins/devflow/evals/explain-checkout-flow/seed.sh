#!/usr/bin/env bash
set -euo pipefail
cd "${1:-$PWD}"
git init -q -b main .
git config user.email eval@example.com
git config user.name eval
git remote add origin https://github.com/acme/shop.git
# Private devflow folder linked into the workspace so graders can read it.
mkdir -p .devflow-home "$(dirname "$PWD")/.config"
ln -s "$PWD/.devflow-home" "$(dirname "$PWD")/.config/devflow"
echo ".devflow-home" >> .git/info/exclude
mkdir -p src
cat > src/cart.js <<'JS'
// Entry point: the checkout button calls placeOrder.
const { reserveStock, releaseStock } = require('./inventory');
const { chargeCard } = require('./payments');

async function placeOrder(cart, card) {
  const reservation = await reserveStock(cart.items);
  try {
    const receipt = await chargeCard(card, cart.total);
    return { status: 'confirmed', receipt };
  } catch (error) {
    await releaseStock(reservation);
    return { status: 'payment_failed' };
  }
}
module.exports = { placeOrder };
JS
cat > src/inventory.js <<'JS'
async function reserveStock(items) { /* holds stock for 10 minutes */ return { id: 'r1', items }; }
async function releaseStock(reservation) { /* frees the held stock */ }
module.exports = { reserveStock, releaseStock };
JS
cat > src/payments.js <<'JS'
async function chargeCard(card, amount) { /* calls the payment provider */ return { id: 'p1', amount }; }
module.exports = { chargeCard };
JS
echo '{ "name": "shop", "private": true }' > package.json
git add -A && git commit -q -m "initial"
