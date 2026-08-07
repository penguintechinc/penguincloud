/**
 * Test double for lucide-react.
 *
 * Renders each icon as a bare <svg> carrying a data-testid, so component tests
 * can assert on icon presence without pulling in the real icon set.
 */
import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number | string };

export const ChevronUp = (props: IconProps) => (
  <svg data-testid="icon-chevronup" {...props} />
);
export const ChevronDown = (props: IconProps) => (
  <svg data-testid="icon-chevrondown" {...props} />
);
export const AlertCircle = (props: IconProps) => (
  <svg data-testid="icon-alertcircle" {...props} />
);
export const AlertTriangle = (props: IconProps) => (
  <svg data-testid="icon-alerttriangle" {...props} />
);
