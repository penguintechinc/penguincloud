package health

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

// Metrics holds Prometheus metrics for health polling.
type Metrics struct {
	ChecksTotal       *prometheus.CounterVec
	CheckDuration     *prometheus.HistogramVec
	EndpointsTotal    prometheus.Gauge
	EndpointsByStatus *prometheus.GaugeVec
}

// NewMetrics creates and registers health polling metrics.
func NewMetrics(namespace string) *Metrics {
	return &Metrics{
		ChecksTotal: promauto.NewCounterVec(
			prometheus.CounterOpts{
				Namespace: namespace,
				Subsystem: "health",
				Name:      "checks_total",
				Help:      "Total number of health checks performed",
			},
			[]string{"product_type", "status"},
		),
		CheckDuration: promauto.NewHistogramVec(
			prometheus.HistogramOpts{
				Namespace: namespace,
				Subsystem: "health",
				Name:      "check_duration_seconds",
				Help:      "Health check duration in seconds",
				Buckets:   []float64{0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10},
			},
			[]string{"product_type"},
		),
		EndpointsTotal: promauto.NewGauge(
			prometheus.GaugeOpts{
				Namespace: namespace,
				Subsystem: "health",
				Name:      "endpoints_total",
				Help:      "Total registered health check endpoints",
			},
		),
		EndpointsByStatus: promauto.NewGaugeVec(
			prometheus.GaugeOpts{
				Namespace: namespace,
				Subsystem: "health",
				Name:      "endpoints_by_status",
				Help:      "Number of endpoints by health status",
			},
			[]string{"status"},
		),
	}
}

// RecordCheck records a health check result.
func (m *Metrics) RecordCheck(productType, status string, durationSec float64) {
	m.ChecksTotal.WithLabelValues(productType, status).Inc()
	m.CheckDuration.WithLabelValues(productType).Observe(durationSec)
}

// UpdateEndpointCounts updates the endpoint gauge metrics from a HealthMatrix.
func (m *Metrics) UpdateEndpointCounts(matrix HealthMatrix) {
	m.EndpointsTotal.Set(float64(matrix.Summary.Total))
	m.EndpointsByStatus.WithLabelValues("healthy").Set(float64(matrix.Summary.Healthy))
	m.EndpointsByStatus.WithLabelValues("degraded").Set(float64(matrix.Summary.Degraded))
	m.EndpointsByStatus.WithLabelValues("unhealthy").Set(float64(matrix.Summary.Unhealthy))
	m.EndpointsByStatus.WithLabelValues("unknown").Set(float64(matrix.Summary.Unknown))
}
