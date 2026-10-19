import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProjectActions } from './ProjectActions';

describe('given the actions of a project', () => {
  it('archives the project when the user presses Archive', async () => {
    const onArchive = vi.fn();
    render(<ProjectActions onArchive={onArchive} onDelete={vi.fn()} />);

    await userEvent.click(screen.getByRole('button', { name: 'Archive' }));

    expect(onArchive).toHaveBeenCalledTimes(1);
  });
});
