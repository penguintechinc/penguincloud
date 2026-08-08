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
export const ChevronRight = (props: IconProps) => (
  <svg data-testid="icon-chevronright" {...props} />
);
export const AlertCircle = (props: IconProps) => (
  <svg data-testid="icon-alertcircle" {...props} />
);
export const AlertTriangle = (props: IconProps) => (
  <svg data-testid="icon-alerttriangle" {...props} />
);
export const Menu = (props: IconProps) => (
  <svg data-testid="icon-menu" {...props} />
);
export const X = (props: IconProps) => <svg data-testid="icon-x" {...props} />;

// Sidebar category icons (components/layout/menuCategories.ts).
export const Home = (props: IconProps) => (
  <svg data-testid="icon-home" {...props} />
);
export const Activity = (props: IconProps) => (
  <svg data-testid="icon-activity" {...props} />
);
export const Building = (props: IconProps) => (
  <svg data-testid="icon-building" {...props} />
);
export const Users = (props: IconProps) => (
  <svg data-testid="icon-users" {...props} />
);
export const Zap = (props: IconProps) => (
  <svg data-testid="icon-zap" {...props} />
);
export const Lock = (props: IconProps) => (
  <svg data-testid="icon-lock" {...props} />
);
export const Settings = (props: IconProps) => (
  <svg data-testid="icon-settings" {...props} />
);
export const Database = (props: IconProps) => (
  <svg data-testid="icon-database" {...props} />
);
export const Shield = (props: IconProps) => (
  <svg data-testid="icon-shield" {...props} />
);
export const Radio = (props: IconProps) => (
  <svg data-testid="icon-radio" {...props} />
);
export const Gauge = (props: IconProps) => (
  <svg data-testid="icon-gauge" {...props} />
);
