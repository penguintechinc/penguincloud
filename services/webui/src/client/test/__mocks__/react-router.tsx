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

export const Navigate = ({ _to }: { _to?: string }) => <></>;
