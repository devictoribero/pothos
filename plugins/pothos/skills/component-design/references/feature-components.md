# Feature components

A feature component renders one concept of one product (an entity, a process, a capability) and composes primitives. Everything in SKILL.md applies; this adds what only business components need.

## Language and context

- Names, copy and test names use the product's term, from the glossary, then copy, then domain types. The request's words are not a source: tickets often use the API's vocabulary.
- Each feature component belongs to one **bounded context** (`jobs/components/JobCard`). Other contexts are reached only through their public entry, from one place (a data-layer file or the container). A view that shows another context's component receives it as a slot.
- The **shared kernel** (ids, money, dates, the actor) is small and explicit.
- Translate another context's type into a local one only when you need a different shape or words; a one-to-one mapper without a reason is ceremony.

## Layers

Dependencies point one way: screen → feature (container → view → primitives) → primitives → platform. The view never imports the data layer; the container wires them. Domain functions import nothing from React, the UI or the API.


| Layer | Holds | Never |
|---|---|---|
| Domain | rules and derived facts as pure functions (`canStartJob(job, actor, today)`); closed unions per entity state | UI, framework or API imports; reading time or identity |
| Data | fetching, mutations, subscriptions; DTO → domain mapping | leaking transport shapes upward |
| View | domain values and callbacks in, primitives out | fetching, business rules in markup, roles |
| Container | wires data into the view; computes facts needing external inputs (today, actor); UI states | anything beyond wiring |

- Props are domain values; handlers are **intentions** in domain words (`onStartJob`), not `onClick`.
- Each intention has pending and failed inputs (`isStarting`, `startFailure`), shown next to what failed, cleared on retry.
- **Optimistic** when frequent, cheap to undo and rarely refused (quantity, save toggle); **wait** when irreversible or validated (pay, assign) and keep the launching dialog open. Removing an item waits and leaves Undo.
- **Data on screen wins over a failed refresh**: show the error only when there is nothing to show.
- **UI states**: without a frame (a card, a row), the container renders loading/empty/failed with primitives. With a frame (a sheet, a section), the view receives the resource as a union and renders each case inside it.
- **Navigation** is a route descriptor from a pure function, rendered with the project's `Link`; `on<Open>` callbacks are for side effects.
- **Permissions** are domain functions taking the actor; the container passes the result.
- **Processes** (an intention plus a draft): the draft is view state; derive the selection from current options every render; the connected component renders the entry button and mounts the process only while open. `open` follows the "Each state" row of the skill: controlled by default (`open` + `onOpenChange`, `defaultOpen` through the project's controllable-state hook), so a screen can start the process from elsewhere without a second trigger inside the component.
- **Small features** (under about 50 lines, no intentions) may keep container and view in one file.
- **Business rules beat the request**: keep the documented rule, draft the spec change, ask.

Exports: a context's public entry exports the connected component and its public domain types; the view only for its own stories and tests.

## Spec template

Lives next to the component; a business spec goes where the project keeps specs and is linked. One fact per bullet in States, Permissions and Accessibility; each gets a test in the layer that owns it.

````markdown
## <ComponentName>

**Purpose:** <the concept, one line>
**Kind:** entity view | process | capability | screen
**Context:** <bounded context> · depends on <contexts through their public entry, or "none">

**Usage**
```tsx
<how a screen mounts it>
```

**Terms**
| The request said | The product says | Source |
|---|---|---|

**States**
- Domain: <closed set and what each shows>
- UI: <loading / empty / failed, rendered by the container or the view inside its frame>
- Intentions: <intention → pending and failure, optimistic or not>

**Permissions**
- <action → who, decided by which domain function>

**Accessibility**
- <landmark or heading; names; focus after each intention; announcements>

**Decisions**
- <decision>. <why>. <to confirm with whom>

**Assumptions**
- <what could not be verified and where it is confined>

**Out of scope**
````

## Example: a job card across layers

```tsx
// jobs/domain/job.ts
export type Job =
  | { status: 'unscheduled'; id: string; title: string }
  | { status: 'scheduled'; id: string; title: string; jobLead: JobLead; startsOn: Date }
  | { status: 'inProgress'; id: string; title: string; jobLead: JobLead; startedOn: Date };
export const canStartJob = (job: Job, actor: Actor, today: Date) =>
  job.status === 'scheduled' && job.startsOn <= today && job.jobLead.id === actor.id;

// jobs/components/JobCard/JobCardContainer.tsx
export function JobCardContainer({ jobId }: { jobId: string }) {
  const actor = useActor();
  const { job, isLoading, error, refetch } = useJob(jobId);   // maps JobDto → Job
  const start = useStartJob();
  if (!job) {
    if (isLoading) return <MediaCard.Skeleton />;
    if (error) return <ErrorState message={t('jobs.loadFailed')} action={<Button onClick={refetch}>{t('common.retry')}</Button>} />;
    return <EmptyState message={t('jobs.notFound')} />;
  }
  return <JobCard job={job} canStart={canStartJob(job, actor, new Date())}
    isStarting={start.isPending} hasStartFailed={start.hasFailed} onStartJob={() => start.start(job.id)} />;
}
```

The view renders `job.status` with an exhaustive `switch` over `MediaCard` parts and never sees the DTO.
