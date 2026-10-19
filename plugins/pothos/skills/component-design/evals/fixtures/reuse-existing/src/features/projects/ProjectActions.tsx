import { Button } from '../../ui';

export type ProjectActionsProps = {
  onArchive: () => void;
  onDelete: () => void;
  isDeleting?: boolean;
};

/** The actions available on a project page header. */
export function ProjectActions({ onArchive, onDelete, isDeleting = false }: ProjectActionsProps) {
  return (
    <div role="group" aria-label="Project actions">
      <Button onClick={onArchive}>Archive</Button>
      <Button variant="danger" isPending={isDeleting} onClick={onDelete}>
        Delete
      </Button>
    </div>
  );
}
