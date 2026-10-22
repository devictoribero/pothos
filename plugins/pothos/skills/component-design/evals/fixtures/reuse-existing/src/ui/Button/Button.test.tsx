import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Button } from './Button';

describe('given a button with a click handler', () => {
  it('calls the handler when the user clicks it', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Save</Button>);

    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('does not submit a surrounding form by default', () => {
    render(<Button>Save</Button>);

    expect(screen.getByRole('button', { name: 'Save' })).toHaveAttribute('type', 'button');
  });

  it('is a native button with the visible text as its name', () => {
    render(<Button onClick={vi.fn()}>Save</Button>);

    expect(screen.getByRole('button', { name: 'Save' })).toBeInstanceOf(HTMLButtonElement);
  });
});

describe('given a button with native attributes and events', () => {
  it('passes every native attribute and event through to the element', async () => {
    const user = userEvent.setup();
    const onFocus = vi.fn();
    render(<Button aria-describedby="hint" onFocus={onFocus}>Save</Button>);

    await user.tab();

    expect(screen.getByRole('button', { name: 'Save' })).toHaveAttribute('aria-describedby', 'hint');
    expect(onFocus).toHaveBeenCalledTimes(1);
  });
});

describe('given a pending button', () => {
  it('is aria-busy and aria-disabled', () => {
    render(<Button isPending>Save</Button>);
    const button = screen.getByRole('button', { name: 'Save' });

    expect(button).toHaveAttribute('aria-busy', 'true');
    expect(button).toHaveAttribute('aria-disabled', 'true');
  });

  it('does nothing when the user clicks it', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<Button isPending onClick={onClick}>Save</Button>);

    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(onClick).not.toHaveBeenCalled();
  });

  it('keeps the button in the tab order', async () => {
    const user = userEvent.setup();
    render(<Button isPending>Save</Button>);

    await user.tab();

    expect(screen.getByRole('button', { name: 'Save' })).toHaveFocus();
  });
});
