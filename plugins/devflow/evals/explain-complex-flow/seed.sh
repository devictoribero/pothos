#!/usr/bin/env bash
# A notifications subsystem spread over api, queue, worker, templates and the mobile client.
# The worker reads the API's database model directly (planted coupling for the critique case).
set -euo pipefail
cd "${1:-$PWD}"
git init -q -b main .
git config user.email eval@example.com
git config user.name eval
git remote add origin https://github.com/acme/vetapp.git
mkdir -p .devflow-home "$(dirname "$PWD")/.config"
ln -s "$PWD/.devflow-home" "$(dirname "$PWD")/.config/devflow"
echo ".devflow-home" >> .git/info/exclude
mkdir -p api/src/reminders api/src/db worker/src templates mobile/src/notifications shared
cat > api/src/db/reminder-model.js <<'JS'
// Postgres row for a vaccination reminder. Columns: id, pet_id, household_id, due_on, sent_at, channel.
const REMINDER_TABLE = 'reminders';
function toRow(reminder) { return { pet_id: reminder.petId, household_id: reminder.householdId, due_on: reminder.dueOn, channel: reminder.channel, sent_at: null }; }
module.exports = { REMINDER_TABLE, toRow };
JS
cat > api/src/reminders/create-reminder.js <<'JS'
// POST /reminders: validates the request, stores the row, then enqueues a job for the due date.
const { toRow, REMINDER_TABLE } = require('../db/reminder-model');
const { enqueue } = require('../../../shared/queue');
async function createReminder(db, body) {
  if (!body.petId || !body.dueOn) throw new Error('petId and dueOn are required');
  const [row] = await db.insert(REMINDER_TABLE, toRow(body));
  await enqueue('reminder.due', { reminderId: row.id }, { runAt: body.dueOn });
  return row;
}
module.exports = { createReminder };
JS
cat > shared/queue.js <<'JS'
// Thin wrapper over the job queue. Jobs are retried 3 times with exponential backoff.
async function enqueue(type, payload, { runAt }) { /* pushes {type, payload, runAt, attempts: 0} */ }
async function consume(type, handler) { /* calls handler(payload); on throw, retries up to 3 times */ }
module.exports = { enqueue, consume };
JS
cat > worker/src/send-due-reminders.js <<'JS'
// Worker: consumes reminder.due jobs, loads the reminder straight from the API's table, renders and sends it.
const { REMINDER_TABLE } = require('../../api/src/db/reminder-model');   // reaches into the API's private model
const { consume } = require('../../shared/queue');
const { render } = require('./render');
const { pushToDevice } = require('./push');
consume('reminder.due', async ({ reminderId }, db) => {
  const reminder = await db.findOne(REMINDER_TABLE, { id: reminderId });
  if (reminder.sent_at) return;                       // idempotency: already sent
  const message = render('vaccination-due', reminder);
  await pushToDevice(reminder.household_id, message);
  await db.update(REMINDER_TABLE, { id: reminderId }, { sent_at: new Date() });
});
JS
cat > worker/src/render.js <<'JS'
// Fills a template from templates/ with the reminder's fields. Falls back to English when the locale is missing.
function render(templateName, reminder) { return { title: 'Vaccination due', body: `Due on ${reminder.due_on}` }; }
module.exports = { render };
JS
cat > worker/src/push.js <<'JS'
// Sends to every device token registered for the household via the push provider.
async function pushToDevice(householdId, message) { /* looks up tokens, calls provider */ }
module.exports = { pushToDevice };
JS
cat > templates/vaccination-due.json <<'JSON'
{ "en": { "title": "Vaccination due", "body": "{{petName}} is due on {{dueOn}}" }, "es": { "title": "Vacuna pendiente", "body": "A {{petName}} le toca el {{dueOn}}" } }
JSON
cat > mobile/src/notifications/register-device.ts <<'TS'
// On login, the app asks for push permission and registers its token with the API (POST /devices).
export async function registerDevice(api: { post: Function }, token: string) { await api.post('/devices', { token }); }
TS
cat > mobile/src/notifications/handle-open.ts <<'TS'
// When the user taps a reminder notification, the app opens the pet's timeline at the vaccination record.
export function handleOpen(data: { petId: string }) { return `/pets/${data.petId}/timeline?focus=vaccination`; }
TS
# More of the subsystem, so the question really spans several modules.
python3 - <<'PY'
import os, textwrap
files = {
 "api/src/reminders/routes.js": "// Express routes for reminders: POST /reminders -> createReminder, GET /pets/:id/reminders -> listReminders, DELETE /reminders/:id -> cancelReminder.\nconst { createReminder } = require('./create-reminder');\nconst { listReminders } = require('./list-reminders');\nconst { cancelReminder } = require('./cancel-reminder');\nmodule.exports = (router, db) => {\n  router.post('/reminders', (req) => createReminder(db, req.body));\n  router.get('/pets/:id/reminders', (req) => listReminders(db, req.params.id));\n  router.delete('/reminders/:id', (req) => cancelReminder(db, req.params.id));\n};\n",
 "api/src/reminders/list-reminders.js": "// Lists pending reminders for a pet, newest due date first.\nconst { REMINDER_TABLE } = require('../db/reminder-model');\nasync function listReminders(db, petId) { return db.find(REMINDER_TABLE, { pet_id: petId, sent_at: null }, { order: 'due_on desc' }); }\nmodule.exports = { listReminders };\n",
 "api/src/reminders/cancel-reminder.js": "// Cancelling marks the row as sent so the worker skips it; the queued job is not removed.\nconst { REMINDER_TABLE } = require('../db/reminder-model');\nasync function cancelReminder(db, id) { await db.update(REMINDER_TABLE, { id }, { sent_at: new Date(0) }); }\nmodule.exports = { cancelReminder };\n",
 "api/src/reminders/schedule-from-vaccination.js": "// When a vaccination Record is logged, the next dose date is computed and a reminder is created for it.\nconst { createReminder } = require('./create-reminder');\nconst { nextDoseDate } = require('../vaccinations/next-dose');\nasync function onVaccinationLogged(db, record) { const dueOn = nextDoseDate(record); if (dueOn) await createReminder(db, { petId: record.petId, householdId: record.householdId, dueOn, channel: 'push' }); }\nmodule.exports = { onVaccinationLogged };\n",
 "api/src/vaccinations/next-dose.js": "// Next dose: rabies yearly, DHPP every three years after the puppy series; null when the vaccine has no booster.\nfunction nextDoseDate(record) { const years = { rabies: 1, dhpp: 3 }[record.vaccine]; if (!years) return null; const d = new Date(record.date); d.setFullYear(d.getFullYear() + years); return d.toISOString().slice(0, 10); }\nmodule.exports = { nextDoseDate };\n",
 "api/src/vaccinations/log-vaccination.js": "// POST /pets/:id/vaccinations stores the Record on the Timeline and triggers reminder scheduling.\nconst { onVaccinationLogged } = require('../reminders/schedule-from-vaccination');\nasync function logVaccination(db, petId, body) { const record = await db.insert('records', { pet_id: petId, kind: 'vaccination', ...body }); await onVaccinationLogged(db, { petId, ...body }); return record; }\nmodule.exports = { logVaccination };\n",
 "api/src/devices/register.js": "// POST /devices stores the push token for the signed-in Member's Household.\nasync function registerToken(db, member, token) { await db.upsert('device_tokens', { household_id: member.householdId, token }); }\nmodule.exports = { registerToken };\n",
 "api/src/devices/tokens.js": "// Reads every token registered for a Household.\nasync function tokensFor(db, householdId) { return (await db.find('device_tokens', { household_id: householdId })).map((r) => r.token); }\nmodule.exports = { tokensFor };\n",
 "worker/src/index.js": "// Worker entry: opens the database and starts every consumer.\nrequire('./send-due-reminders');\nrequire('./cleanup-old-jobs');\n",
 "worker/src/cleanup-old-jobs.js": "// Nightly: deletes finished jobs older than 30 days.\nconst { consume } = require('../../shared/queue');\nconsume('jobs.cleanup', async () => {});\n",
 "worker/src/retry-policy.js": "// Backoff used by shared/queue: 1 min, 5 min, 30 min, then the job is dead-lettered.\nmodule.exports = { delays: [60, 300, 1800] };\n",
 "worker/src/push-provider.js": "// Adapter over the push provider SDK; maps provider errors to retryable or permanent.\nasync function send(token, message) { /* provider.send */ }\nmodule.exports = { send };\n",
 "worker/src/locale.js": "// Picks the Household's language for templates; defaults to en.\nfunction localeFor(householdId) { return 'es'; }\nmodule.exports = { localeFor };\n",
 "templates/loader.js": "// Loads templates/*.json and interpolates {{placeholders}}.\nfunction load(name, locale) { const all = require(`./${name}.json`); return all[locale] || all.en; }\nmodule.exports = { load };\n",
 "mobile/src/notifications/permissions.ts": "// Asks for notification permission once, after the first Pet is created.\nexport async function askOnce() { return 'granted'; }\n",
 "mobile/src/notifications/listener.ts": "// Subscribes to notification taps and routes them through handleOpen.\nimport { handleOpen } from './handle-open';\nexport function listen(navigate: (path: string) => void) { /* on tap: */ navigate(handleOpen({ petId: 'p1' })); }\n",
 "mobile/src/navigation/routes.ts": "// Route table: /pets/:id/timeline renders the Timeline; focus=vaccination scrolls to the latest vaccination Record.\nexport const routes = { timeline: '/pets/:id/timeline' };\n",
 "mobile/src/timeline/use-focus.ts": "// Reads the focus query param and scrolls the Timeline to the matching Record.\nexport function useFocus(focus?: string) { return focus === 'vaccination'; }\n",
 "docs/notifications.md": "# Notifications\n\nReminders are created from vaccination Records, queued for their due date, sent by the worker as push notifications and open the pet's Timeline when tapped.\n",
}
for path, text in files.items():
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)
PY
echo '{ "name": "vetapp", "private": true }' > package.json
git add -A && git commit -q -m "initial"
