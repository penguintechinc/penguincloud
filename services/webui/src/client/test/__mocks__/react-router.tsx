/**
 * Mock for react-router — used in jest tests.
 */

import React, { ReactNode } from "react";

const useLocationMock = jest.fn(() => ({ pathname: "/" }));

export const useLocation = useLocationMock;
export const useNavigate = jest.fn();
export const useParams = jest.fn();
export const useSearchParams = jest.fn(() => [
  new URLSearchParams(),
  jest.fn(),
]);

export const Link = React.forwardRef<
  HTMLAnchorElement,
  { to: string; children: ReactNode }
>(({ to, children }, ref) => (
  <a ref={ref} href={to}>
    {children}
  </a>
));
Link.displayName = "Link";

export const BrowserRouter = ({ children }: { children: ReactNode }) => (
  <>{children}</>
);

export const Routes = ({ children }: { children: ReactNode }) => (
  <>{children}</>
);

export const Route = ({ element }: { element?: ReactNode }) => <>{element}</>;

// Renders a marker instead of nothing so tests can assert on the redirect
// target. The previous `{ _to }` destructure was also an unused-binding
// typecheck error (TS6133).
export const Navigate = ({ to }: { to?: string }) => (
  <div data-testid="navigate" data-to={to} />
);

/** Renders nothing by default; Layout tests only assert the surrounding shell. */
export const Outlet = () => <div data-testid="outlet" />;
