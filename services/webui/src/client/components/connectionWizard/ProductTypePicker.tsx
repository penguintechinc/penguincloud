/**
 * Step 1 of the connection wizard: pick a product type, grouped by category.
 */

import type { ProductType } from "../../types";

interface ProductTypePickerProps {
  productTypes: ProductType[];
  selectedType: ProductType | null;
  onSelect: (productType: ProductType) => void;
}

/** Buckets the flat catalogue into `{ category: types[] }`. */
export function groupByCategory(
  productTypes: ProductType[],
): Record<string, ProductType[]> {
  const categories: Record<string, ProductType[]> = {};
  productTypes.forEach((pt) => {
    if (!categories[pt.category]) categories[pt.category] = [];
    categories[pt.category].push(pt);
  });
  return categories;
}

export default function ProductTypePicker({
  productTypes,
  selectedType,
  onSelect,
}: ProductTypePickerProps) {
  const categories = groupByCategory(productTypes);

  return (
    <div>
      <p className="text-slate-400 mb-4">Select the product type to connect:</p>
      {Object.entries(categories).map(([category, types]) => (
        <div key={category} className="mb-4">
          <h3 className="text-sm font-medium text-slate-400 uppercase mb-2">
            {category}
          </h3>
          <div className="grid grid-cols-2 gap-2">
            {types.map((pt) => (
              <button
                key={pt.product_type}
                onClick={() => onSelect(pt)}
                className={`text-left p-3 rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-sky-500 ${
                  selectedType?.product_type === pt.product_type
                    ? "border-amber-400 bg-slate-800"
                    : "border-slate-700 hover:border-slate-600"
                }`}
              >
                <div className="text-sm font-medium text-amber-400">
                  {pt.display_name}
                </div>
                <div className="text-xs text-slate-500">{pt.category}</div>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
