/**
 * Breadcrumbs — Route-derived breadcrumb navigation.
 * Parses current pathname to build a breadcrumb trail.
 */

import { useLocation, Link } from "react-router";
import { ChevronRight } from "lucide-react";

interface Breadcrumb {
  label: string;
  href?: string;
  active?: boolean;
}

export function Breadcrumbs() {
  const location = useLocation();

  // Parse pathname into breadcrumbs
  const getBreadcrumbs = (): Breadcrumb[] => {
    const pathname = location.pathname;

    // Root
    if (pathname === "/") {
      return [{ label: "Dashboard", href: "/", active: true }];
    }

    const parts = pathname.split("/").filter((p) => p);
    const breadcrumbs: Breadcrumb[] = [{ label: "Dashboard", href: "/" }];

    // Build breadcrumb path
    let currentPath = "";
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      currentPath += `/${part}`;

      // Humanize the label
      const label = formatLabel(part);

      if (i === parts.length - 1) {
        // Last item is active
        breadcrumbs.push({ label, active: true });
      } else {
        breadcrumbs.push({ label, href: currentPath });
      }
    }

    return breadcrumbs;
  };

  // Convert URL segment to human-readable label
  const formatLabel = (segment: string): string => {
    // Remove IDs (just hyphens)
    if (/^\d+$/.test(segment)) return segment;

    // Title case and replace hyphens with spaces
    return segment
      .split("-")
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ");
  };

  const breadcrumbs = getBreadcrumbs();

  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1">
      {breadcrumbs.map((breadcrumb, index) => (
        <div key={index} className="flex items-center gap-1">
          {index > 0 && (
            <ChevronRight className="w-4 h-4 text-slate-500 mx-1" />
          )}
          {breadcrumb.active ? (
            <span className="text-sm text-amber-400 font-medium">
              {breadcrumb.label}
            </span>
          ) : (
            <Link
              to={breadcrumb.href || "/"}
              className="text-sm text-slate-300 hover:text-amber-400 transition-colors"
            >
              {breadcrumb.label}
            </Link>
          )}
        </div>
      ))}
    </nav>
  );
}
