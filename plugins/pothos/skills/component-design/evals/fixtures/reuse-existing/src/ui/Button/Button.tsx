import { forwardRef, type ButtonHTMLAttributes, type MouseEvent } from 'react';
import styles from './Button.module.css';

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  /** `primary` for the one main action of a region, `danger` for destructive actions. */
  variant?: 'primary' | 'secondary' | 'danger';
  /** The action is running: the button announces busy, stays focusable and ignores clicks. */
  isPending?: boolean;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', isPending = false, type = 'button', className, onClick, children, ...rest },
  ref,
) {
  const handleClick = (event: MouseEvent<HTMLButtonElement>) => {
    if (isPending) {
      event.preventDefault();
      return;
    }
    onClick?.(event);
  };
  return (
    <button
      ref={ref}
      type={type}
      className={[styles.root, styles[variant], className].filter(Boolean).join(' ')}
      aria-busy={isPending || undefined}
      aria-disabled={isPending || undefined}
      onClick={handleClick}
      {...rest}
    >
      {children}
    </button>
  );
});
