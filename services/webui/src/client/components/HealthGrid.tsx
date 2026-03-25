import type { ProductConnection } from '../types';
import ProductStatusCard from './ProductStatusCard';

interface HealthGridProps {
  products: ProductConnection[];
  onProductClick?: (product: ProductConnection) => void;
}

export default function HealthGrid({ products, onProductClick }: HealthGridProps) {
  if (products.length === 0) {
    return (
      <div className="text-center py-12 text-dark-400">
        <p className="text-lg mb-2">No products connected</p>
        <p className="text-sm">Connect a PenguinTech product to start monitoring.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
      {products.map((product) => (
        <ProductStatusCard
          key={product.id}
          product={product}
          onClick={onProductClick ? () => onProductClick(product) : undefined}
        />
      ))}
    </div>
  );
}
