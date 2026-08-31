import { useState, useEffect } from "react";
import { useParams } from "react-router";
import { productsApi } from "../../hooks/useApi";
import Card from "../../components/Card";
import ProductCapabilities, { type SchemaState } from "./ProductCapabilities";
import type { ProductConnection } from "../../types";

/**
 * Generic fallback screen for any connected product without a dedicated,
 * manifest-driven set of management screens (gough/nest/tobogganing have
 * their own). Renders the product's own health/info plus an honest state for
 * its capabilities — never an empty tab list that could be mistaken for a
 * product with no capabilities to show.
 */
export default function ProductPage() {
  const { id } = useParams<{ id: string }>();
  const productId = Number(id);
  const [product, setProduct] = useState<ProductConnection | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [schemaState, setSchemaState] = useState<SchemaState>({
    status: "loading",
  });

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setSchemaState({ status: "loading" });

    productsApi
      .get(productId)
      .then((prod) => {
        if (!cancelled) setProduct(prod);
      })
      .catch(() => {
        console.error("[ProductPage] Failed to fetch product", { productId });
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    productsApi
      .schema(productId)
      .then((schema) => {
        if (!cancelled) setSchemaState({ status: "loaded", schema });
      })
      .catch(() => {
        if (!cancelled) setSchemaState({ status: "error" });
      });

    return () => {
      cancelled = true;
    };
  }, [productId]);

  if (isLoading)
    return <div className="animate-pulse h-64 bg-slate-700 rounded" />;
  if (!product) return <p className="text-slate-400">Product not found.</p>;

  const statusColor: Record<string, string> = {
    healthy: "text-green-400",
    degraded: "text-yellow-400",
    unhealthy: "text-red-400",
    unknown: "text-slate-400",
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-amber-400">
          {product.display_name}
        </h1>
        <p className="text-slate-400 mt-1">
          {product.product_type} —{" "}
          <span
            className={statusColor[product.health_status] || "text-slate-400"}
          >
            {product.health_status}
          </span>
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card title="Product Info">
          <dl className="space-y-2">
            <div className="flex justify-between">
              <dt className="text-slate-400">Type</dt>
              <dd className="text-slate-200">{product.product_type}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-400">Base URL</dt>
              <dd className="text-slate-200 truncate ml-4">
                {product.base_url}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-400">Health</dt>
              <dd className={statusColor[product.health_status]}>
                {product.health_status}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-400">Last Check</dt>
              <dd className="text-slate-200">
                {product.last_health_check
                  ? new Date(product.last_health_check).toLocaleString()
                  : "Never"}
              </dd>
            </div>
          </dl>
        </Card>

        <Card title="Capabilities">
          <ProductCapabilities schemaState={schemaState} />
        </Card>
      </div>
    </div>
  );
}
