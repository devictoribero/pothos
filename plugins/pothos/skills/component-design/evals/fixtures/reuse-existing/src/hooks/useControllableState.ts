import { useCallback, useState } from 'react';

/**
 * Resolves a controlled or uncontrolled value so a component never knows which mode it is in.
 * The change handler fires in both modes.
 */
export function useControllableState<T>(controlled: T | undefined, defaultValue: T, onChange?: (next: T) => void) {
  const [internal, setInternal] = useState(defaultValue);
  const isControlled = controlled !== undefined;
  const setValue = useCallback(
    (next: T) => {
      if (!isControlled) setInternal(next);
      onChange?.(next);
    },
    [isControlled, onChange],
  );
  return [isControlled ? controlled : internal, setValue] as const;
}
