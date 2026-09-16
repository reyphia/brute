import { render, screen } from '@testing-library/react';
import App from './App';

test('shows a setup message when Firebase env vars are missing', () => {
  // .env isn't injected in the test environment, so this reflects the
  // out-of-the-box state before the user has filled it in.
  render(<App />);
  const heading = screen.getByText(/firebase is not configured/i);
  expect(heading).toBeInTheDocument();
});
