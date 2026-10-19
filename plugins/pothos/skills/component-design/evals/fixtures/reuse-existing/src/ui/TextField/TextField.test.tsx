import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TextField } from './TextField';

describe('given a text field with a label', () => {
  it('is found by its label and reports what the user types', async () => {
    const onChange = vi.fn();
    render(<TextField label="Name" onChange={onChange} />);

    await userEvent.type(screen.getByRole('textbox', { name: 'Name' }), 'Kitchen');

    expect(onChange).toHaveBeenCalled();
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
