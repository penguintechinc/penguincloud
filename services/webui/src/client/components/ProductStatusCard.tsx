import type { ProductConnection } from '../types';

interface ProductStatusCardProps {
  product: ProductConnection;
  onClick?: () => void;
}

const statusColors: Record<string, string> = {
  healthy: 'text-green-400',
  degraded: 'text-yellow-400',
  unhealthy: 'text-red-400',
  unknown: 'text-dark-400',
};

const statusDots: Record<string, string> = {
  healthy: 'bg-green-400',
  degraded: 'bg-yellow-400',
  unhealthy: 'bg-red-400',
  unknown: 'bg-dark-400',
};

export default function ProductStatusCard({ product, onClick }: ProductStatusCardProps) {
  const status = product.health_status || 'unknown';

  return (
    <div
      onClick={onClick}
      className={`card p-4 ${onClick ? 'cursor-pointer hover:border-gold-400/50' : ''} transition-colors`}
    >
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-medium text-gold-400 truncate">{product.display_name}</h3>
        <div className="flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full ${statusDots[status]}`} />
          <span className={`text-xs ${statusColors[status]}`}>{status}</span>
        </div>
      </div>
      <div className="text-xs text-dark-400 truncate">{product.product_type}</div>
      <div className="text-xs text-dark-500 truncate mt-1">{product.base_url}</div>
      {product.last_health_check && (
        <div className="text-xs text-dark-500 mt-1">
          Last check: {new Date(product.last_health_check).toLocaleTimeString()}
        </div>
      )}
    </div>
  );
}
