#!/usr/bin/env bash
# A clinic service: an API that runs as several instances, and a worker that runs every delayed job.
# Usage: council-seed.sh <dir> [open|settled]
#   open (default): a decision record states that the API runs as three instances and rules on nothing,
#     so "a timer in the API or a job on the queue" is a real fork with a planted fact to find.
#   settled: the records also forbid timers in the API and send delayed work to the queue, so the same
#     question is already answered and a council must stand aside.
# A benchmark script settles the search question on its own in both modes.
set -euo pipefail
cd "${1:-$PWD}"
mode="${2:-open}"
git init -q -b main .
git config user.email eval@example.com
git config user.name eval
git remote add origin https://github.com/acme/clinic.git
mkdir -p .pothos-home "$(dirname "$PWD")/.config"
ln -sfn "$PWD/.pothos-home" "$(dirname "$PWD")/.config/pothos"
echo ".pothos-home" >> .git/info/exclude
mkdir -p api/src/appointments api/src/search worker/src shared docs/decisions scripts
cat > README.md <<'MD'
# clinic

Appointments and reminders for a veterinary clinic. `api/` serves the app, `worker/` runs delayed jobs from the queue in `shared/queue.js`.
MD
cat > docs/decisions/0004-the-api-runs-as-several-instances.md <<'MD'
# 0004 The API runs as several instances

The API runs as three instances behind the load balancer, and the number changes with load. Every instance starts the same code and none of them knows about the others.
MD
if [ "$mode" = settled ]; then
cat >> docs/decisions/0004-the-api-runs-as-several-instances.md <<'MD'

Nothing in the API process may assume it runs once. No timers, intervals or schedulers inside the API: each instance would fire its own, so anything sent from one would be sent once per instance.
MD
cat > docs/decisions/0002-delayed-work-goes-through-the-queue.md <<'MD'
# 0002 Delayed work goes through the queue

Anything that happens later than the request that caused it is a job on the queue, run by the worker. The worker retries a failed job and never runs the same job twice.
MD
fi
cat > shared/queue.js <<'JS'
// A delayed job queue on the `jobs` table, shared by the API and the worker. `enqueue` stores a job to
// run at `runAt`. `claimDue` hands each due job to one worker; `release` gives a failed job back.
async function enqueue(db, name, payload, { runAt }) {
  await db.insert('jobs', { name, payload, run_at: runAt, claimed_by: null, done_at: null });
}
async function claimDue(db, now, workerId) {
  return db.query(
    'update jobs set claimed_by = $2 where run_at <= $1 and claimed_by is null and done_at is null returning *',
    [now, workerId],
  );
}
async function finish(db, job) { await db.query('update jobs set done_at = now() where id = $1', [job.id]); }
async function release(db, job) { await db.query('update jobs set claimed_by = null where id = $1', [job.id]); }
module.exports = { enqueue, claimDue, finish, release };
JS
cat > worker/src/jobs.js <<'JS'
// Every delayed job the worker knows. A handler runs once per job; a throw is retried.
const handlers = {};
function registerJob(name, handler) { handlers[name] = handler; }
registerJob('vaccine.due', async ({ petId }, { push }) => push.send(petId, 'A vaccine is due this week'));
registerJob('invoice.overdue', async ({ invoiceId }, { mail }) => mail.send(invoiceId, 'Your invoice is overdue'));
module.exports = { handlers, registerJob };
JS
cat > worker/src/run.js <<'JS'
// The worker: one process. Every ten seconds it claims the due jobs and runs each handler once.
const { claimDue, finish, release } = require('../../shared/queue');
const { handlers } = require('./jobs');
async function tick(db, services, workerId) {
  for (const job of await claimDue(db, new Date(), workerId)) {
    try { await handlers[job.name](job.payload, services); await finish(db, job); } catch (e) { await release(db, job); }
  }
}
function start(db, services) { return setInterval(() => tick(db, services, 'worker-1'), 10000); }
module.exports = { start, tick };
JS
cat > api/src/appointments/create-appointment.js <<'JS'
// POST /appointments: stores the appointment. Nothing reminds the owner yet.
async function createAppointment(db, body) {
  if (!body.petId || !body.startsAt) throw new Error('petId and startsAt are required');
  const [row] = await db.insert('appointments', { pet_id: body.petId, starts_at: body.startsAt });
  return row;
}
module.exports = { createAppointment };
JS
cat > api/src/server.js <<'JS'
// Started once per instance by the platform; INSTANCE_COUNT is 3 in production.
const http = require('http');
const { createAppointment } = require('./appointments/create-appointment');
function start(db) {
  return http.createServer(async (req, res) => {
    if (req.method === 'POST' && req.url === '/appointments') {
      res.end(JSON.stringify(await createAppointment(db, JSON.parse(await read(req)))));
    }
  }).listen(process.env.PORT);
}
function read(req) { return new Promise((ok) => { let b = ''; req.on('data', (c) => { b += c; }); req.on('end', () => ok(b)); }); }
module.exports = { start };
JS
cat > api/src/search/find-pets.js <<'JS'
// Pet search by name. Two candidate indexes exist; scripts/bench-search.js times both on the fixture.
function findPets(db, text, index = 'prefix') { return db.query(`select * from pets_${index} where name like $1`, [`${text}%`]); }
module.exports = { findPets };
JS
cat > scripts/bench-search.js <<'JS'
// Times the prefix index against the trigram index on 50k fixture pets and prints both, in ms.
// Usage: node scripts/bench-search.js
const { performance } = require('perf_hooks');
for (const index of ['prefix', 'trigram']) {
  const t = performance.now();
  for (let i = 0; i < 50000; i += 1) { `${index}-${i}`.startsWith('pre'); }
  console.log(index, (performance.now() - t).toFixed(1));
}
JS
cat > package.json <<'JSON'
{"name": "clinic", "private": true}
JSON
git add -A && git commit -q -m "chore: clinic"
