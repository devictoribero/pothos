import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Button } from './Button';

describe('given a button with a click handler', () => {
  it('calls the handler when the user clicks it', async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Save</Button>);

    await userEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('does not submit a surrounding form by default', () => {
    render(<Button>Save</Button>);

    expect(screen.getByRole('button', { name: 'Save' })).toHaveAttribute('type', 'button');
  });
});

describe('given a pending button', () => {
  it('announces busy and ignores clicks', async () => {
    const onClick = vi.fn();
    render(<Button isPending onClick={onClick}>Save</Button>);
    const button = screen.getByRole('button', { name: 'Save' });

    await userEvent.click(button);

    expect(button).toHaveAttribute('aria-busy', 'true');
    expect(button).toHaveAttribute('aria-disabled', 'true');
    expect(onClick).not.toHaveBeenCalled();
  });

  it('keeps the button in the tab order', async () => {
    render(<Button isPending>Save</Button>);

    await userEvent.tab();

    expect(screen.getByRole('button', { name: 'Save' })).toHaveFocus();
  });
});
