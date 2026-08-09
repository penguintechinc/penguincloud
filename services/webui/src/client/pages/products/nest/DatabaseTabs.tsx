import type { DetailDrawerTab } from "../../../components/kit";
import { FactList } from "./NestUi";
import { useNestSnapshots } from "./useNest";
import type { NestDatabase } from "./types";

/** Bytes as an operator reads them; snapshots report raw byte counts. */
function humanBytes(bytes: number | null | undefined): string | null {
  if (bytes === null || bytes === undefined) return null;
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KiB", "MiB", "GiB", "TiB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(1)} ${units[unit]}`;
}

/**
 * Snapshots taken from one data-resource.
 *
 * Filtered on `sourcePVC`, the edge Nest publishes on a VolumeSnapshot — the
 * same edge the adapter maps onto `parent_id`. Without it this tab would have
 * to list every snapshot in the tenant and let the operator work out which
 * belong to the resource they opened.
 */
function SnapshotsTab({ database }: { database: NestDatabase }) {
  const { data, isLoading, error } = useNestSnapshots();

  if (isLoading) {
    return (
      <div
        className="animate-pulse h-16 bg-slate-700 rounded"
        data-testid="nest-snapshots-loading"
      />
    );
  }
  if (error) {
    return (
      <p className="text-sm text-red-400" data-testid="nest-snapshots-error">
        Could not read snapshots for this resource.
      </p>
    );
  }

  const mine = (data ?? []).filter(
    (snapshot) => snapshot.sourcePVC === database.name,
  );
  if (mine.length === 0) {
    return (
      <p className="text-sm text-slate-400" data-testid="nest-snapshots-empty">
        No snapshots have been taken from this resource.
      </p>
    );
  }

  return (
    <ul className="space-y-2" data-testid="nest-snapshots">
      {mine.map((snapshot) => (
        <li
          key={snapshot.name}
          className="border border-slate-700 rounded p-2 text-sm"
        >
          <div className="flex justify-between gap-4">
            <span className="text-slate-200">{snapshot.name}</span>
            <span
              className={
                snapshot.readyToUse ? "text-emerald-400" : "text-amber-400"
              }
            >
              {snapshot.readyToUse ? "ready" : "pending"}
            </span>
          </div>
          <p className="text-xs text-slate-400">
            {humanBytes(snapshot.sizeBytes) ?? "size not reported"}
            {snapshot.creationTime ? ` · ${snapshot.creationTime}` : ""}
          </p>
        </li>
      ))}
    </ul>
  );
}

/**
 * Detail drawer tabs for one data-resource.
 *
 * Health is its own tab rather than a line in Overview because `healthMessage`
 * is free prose from the last probe and can be long; inlining it would push the
 * identifying facts off the top of the drawer.
 */
export function DatabaseTabs(database: NestDatabase | null): DetailDrawerTab[] {
  if (!database) return [];

  return [
    {
      id: "overview",
      label: "Overview",
      content: (
        <FactList
          facts={[
            ["Phase", database.phase],
            ["Type", database.resourceType],
            ["Engine", database.engineType],
            ["Storage class", database.storageClass],
            ["Namespace", database.namespace],
            [
              "Size",
              database.sizeGi === null || database.sizeGi === undefined
                ? null
                : `${database.sizeGi} GiB`,
            ],
            ["Origination", database.origination],
            ["Created", database.createdAt],
          ]}
        />
      ),
    },
    {
      id: "health",
      label: "Health",
      content: (
        <FactList
          facts={[
            ["State", database.healthState],
            ["Message", database.healthMessage],
            ["Last checked", database.healthLastCheck],
            ["External provider", database.externalProvider],
            ["External endpoint", database.externalEndpoint],
            ["External region", database.externalRegion],
          ]}
        />
      ),
    },
    {
      id: "snapshots",
      label: "Snapshots",
      content: <SnapshotsTab database={database} />,
    },
  ];
}
