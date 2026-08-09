/**
 * Labelled facts for a detail drawer's overview tab.
 *
 * Promoted from the Gough and Nest copies on the third product needing it, as
 * both of those files instructed.
 *
 * `testId` is REQUIRED rather than defaulted. The two copies this replaces
 * hardcoded `gough-facts` and `nest-facts`, and each product's drawer test
 * scopes its assertions to that node; a shared default would have made the two
 * lists indistinguishable the moment a screen rendered both.
 */

/** One labelled fact. A null/empty value renders as a dash, never blank. */
export type Fact = [label: string, value: string | null | undefined];

interface FactListProps {
  facts: Fact[];
  testId: string;
}

/**
 * A blank cell reads as a layout bug; a dash reads as "the product did not
 * report one", which is the true statement. That rendering is asserted once
 * here rather than re-decided per product.
 */
export function FactList({ facts, testId }: FactListProps) {
  return (
    <dl className="grid grid-cols-2 gap-y-2 text-sm" data-testid={testId}>
      {facts.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-slate-400">{label}</dt>
          <dd className="text-slate-200">{value || "—"}</dd>
        </div>
      ))}
    </dl>
  );
}
