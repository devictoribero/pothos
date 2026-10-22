import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TextField } from './TextField';

describe('given a text field with a label', () => {
  it('is labelled by the visible label', () => {
    render(<TextField label="Name" />);

    expect(screen.getByLabelText('Name')).toBe(screen.getByRole('textbox'));
  });

  it('reports what the user types', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<TextField label="Name" onChange={onChange} />);

    await user.type(screen.getByRole('textbox', { name: 'Name' }), 'Kitchen');

    expect(onChange).toHaveBeenCalledTimes(7);
    expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue('Kitchen');
  });
});

describe('given a text field with a controlled value', () => {
  it('shows the value the consumer controls, as on a native input', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<TextField label="Name" value="Kitchen" onChange={onChange} />);

    await user.type(screen.getByRole('textbox', { name: 'Name' }), '!');

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue('Kitchen');
  });
});

describe('given a text field with a default value', () => {
  it('works uncontrolled with defaultValue', async () => {
    const user = userEvent.setup();
    render(<TextField label="Name" defaultValue="Kitchen" />);

    await user.type(screen.getByRole('textbox', { name: 'Name' }), '!');

    expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue('Kitchen!');
  });
});

describe('given a text field with native attributes and events', () => {
  it('passes every native attribute and event through to the input', async () => {
    const user = userEvent.setup();
    const onBlur = vi.fn();
    render(<TextField label="Name" maxLength={5} onBlur={onBlur} />);

    await user.tab();
    await user.tab();

    expect(screen.getByRole('textbox', { name: 'Name' })).toHaveAttribute('maxlength', '5');
    expect(onBlur).toHaveBeenCalledTimes(1);
  });
});

describe('given a text field with an error', () => {
  it('is invalid and described by the announced message', () => {
    render(<TextField label="Name" error="Name is required" />);
    const input = screen.getByRole('textbox', { name: 'Name' });

    expect(input).toBeInvalid();
    expect(input).toHaveAccessibleDescription('Name is required');
    expect(screen.getByRole('alert')).toHaveTextContent('Name is required');
  });
});
