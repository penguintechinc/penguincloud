// Package metrics provides Prometheus metrics for the Go backend.
package metrics

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

// Metrics holds all Prometheus metrics for the application.
type Metrics struct {
	// HTTP metrics
	HTTPRequestsTotal    *prometheus.CounterVec
	HTTPRequestDuration  *prometheus.HistogramVec
	HTTPActiveRequests   prometheus.Gauge

	// XDP metrics
	XDPPacketsReceived   prometheus.Counter
	XDPPacketsSent       prometheus.Counter
	XDPPacketsDropped    prometheus.Counter
	XDPBytesReceived     prometheus.Counter
	XDPBytesSent         prometheus.Counter
	XDPProcessingTime    prometheus.Histogram

	// Memory pool metrics
	MemoryPoolTotal      prometheus.Gauge
	MemoryPoolUsed       prometheus.Gauge
	MemoryPoolFree       prometheus.Gauge
	MemoryPoolAllocations prometheus.Counter
	MemoryPoolReleases   prometheus.Counter
	MemoryPoolPeakUsage  prometheus.Gauge

	// NUMA metrics
	NUMANodeID           prometheus.Gauge
	NUMAAvailable        prometheus.Gauge
	NUMAMemoryMB         *prometheus.GaugeVec

	// System metrics
	GoRoutines           prometheus.Gauge
	HeapAlloc            prometheus.Gauge
	HeapSys              prometheus.Gauge
	GCPauseNS            prometheus.Gauge
}

// NewMetrics creates and registers all metrics.
func NewMetrics(namespace string) *Metrics {
	if namespace == "" {
		namespace = "go_backend"
	}

	m := &Metrics{
		// HTTP metrics
		HTTPRequestsTotal: promauto.NewCounterVec(
			prometheus.CounterOpts{
				Namespace: namespace,
				Name:      "http_requests_total",
				Help:      "Total number of HTTP requests",
			},
			[]string{"method", "endpoint", "status"},
		),

		HTTPRequestDuration: promauto.NewHistogramVec(
			prometheus.HistogramOpts{
				Namespace: namespace,
				Name:      "http_request_duration_seconds",
				Help:      "HTTP request duration in seconds",
				Buckets:   prometheus.DefBuckets,
			},
			[]string{"method", "endpoint"},
		),

		HTTPActiveRequests: promauto.NewGauge(
			prometheus.GaugeOpts{
				Namespace: namespace,
				Name:      "http_active_requests",
				Help:      "Number of active HTTP requests",
			},
		),

		// XDP metrics
		XDPPacketsReceived: promauto.NewCounter(
			prometheus.CounterOpts{
				Namespace: namespace,
				Name:      "xdp_packets_received_total",
				Help:      "Total number of packets received via XDP",
			},
		),

		XDPPacketsSent: promauto.NewCounter(
			prometheus.CounterOpts{
				Namespace: namespace,
				Name:      "xdp_packets_sent_total",
				Help:      "Total number of packets sent via XDP",
			},
		),

		XDPPacketsDropped: promauto.NewCounter(
			prometheus.CounterOpts{
				Namespace: namespace,
				Name:      "xdp_packets_dropped_total",
				Help:      "Total number of packets dropped",
			},
		),

		XDPBytesReceived: promauto.NewCounter(
			prometheus.CounterOpts{
				Namespace: namespace,
				Name:      "xdp_bytes_received_total",
				Help:      "Total bytes received via XDP",
			},
		),

		XDPBytesSent: promauto.NewCounter(
			prometheus.CounterOpts{
				Namespace: namespace,
				Name:      "xdp_bytes_sent_total",
				Help:      "Total bytes sent via XDP",
			},
		),

		XDPProcessingTime: promauto.NewHistogram(
			prometheus.HistogramOpts{
				Namespace: namespace,
				Name:      "xdp_processing_time_nanoseconds",
				Help:      "Packet processing time in nanoseconds",
				Buckets:   []float64{100, 500, 1000, 5000, 10000, 50000, 100000},
			},
		),

		// Memory pool metrics
		MemoryPoolTotal: promauto.NewGauge(
			prometheus.GaugeOpts{
				Namespace: namespace,
				Name:      "memory_pool_slots_total",
				Help:      "Total number of memory pool slots",
			},
		),

		MemoryPoolUsed: promauto.NewGauge(
			prometheus.GaugeOpts{
				Namespace: namespace,
				Name:      "memory_pool_slots_used",
				Help:      "Number of memory pool slots in use",
			},
		),

		MemoryPoolFree: promauto.NewGauge(
			prometheus.GaugeOpts{
				Namespace: namespace,
				Name:      "memory_pool_slots_free",
				Help:      "Number of free memory pool slots",
			},
		),

		MemoryPoolAllocations: promauto.NewCounter(
			prometheus.CounterOpts{
				Namespace: namespace,
				Name:      "memory_pool_allocations_total",
				Help:      "Total number of memory pool allocations",
			},
		),

		MemoryPoolReleases: promauto.NewCounter(
			prometheus.CounterOpts{
				Namespace: namespace,
				Name:      "memory_pool_releases_total",
				Help:      "Total number of memory pool releases",
			},
		),

		MemoryPoolPeakUsage: promauto.NewGauge(
			prometheus.GaugeOpts{
				Namespace: namespace,
				Name:      "memory_pool_peak_usage",
				Help:      "Peak memory pool usage",
			},
		),

		// NUMA metrics
		NUMANodeID: promauto.NewGauge(
			prometheus.GaugeOpts{
				Namespace: namespace,
				Name:      "numa_node_id",
				Help:      "Current NUMA node ID",
			},
		),

		NUMAAvailable: promauto.NewGauge(
			prometheus.GaugeOpts{
				Namespace: namespace,
				Name:      "numa_available",
				Help:      "Whether NUMA is available (1=yes, 0=no)",
			},
		),

		NUMAMemoryMB: promauto.NewGaugeVec(
			prometheus.GaugeOpts{
				Namespace: namespace,
				Name:      "numa_memory_mb",
				Help:      "Memory available per NUMA node in MB",
			},
			[]string{"node"},
		),

		// System metrics
		GoRoutines: promauto.NewGauge(
			prometheus.GaugeOpts{
				Namespace: namespace,
				Name:      "goroutines",
				Help:      "Number of goroutines",
			},
		),

		HeapAlloc: promauto.NewGauge(
			prometheus.GaugeOpts{
				Namespace: namespace,
				Name:      "heap_alloc_bytes",
				Help:      "Heap allocation in bytes",
			},
		),

		HeapSys: promauto.NewGauge(
			prometheus.GaugeOpts{
				Namespace: namespace,
				Name:      "heap_sys_bytes",
				Help:      "Heap system memory in bytes",
			},
		),

		GCPauseNS: promauto.NewGauge(
			prometheus.GaugeOpts{
				Namespace: namespace,
				Name:      "gc_pause_ns",
				Help:      "Last GC pause duration in nanoseconds",
			},
		),
	}

	return m
}

// RecordHTTPRequest records metrics for an HTTP request.
func (m *Metrics) RecordHTTPRequest(method, endpoint, status string, durationSeconds float64) {
	m.HTTPRequestsTotal.WithLabelValues(method, endpoint, status).Inc()
	m.HTTPRequestDuration.WithLabelValues(method, endpoint).Observe(durationSeconds)
}

// UpdateMemoryPoolStats updates memory pool metrics.
func (m *Metrics) UpdateMemoryPoolStats(total, used, free int, allocs, releases uint64, peak int32) {
	m.MemoryPoolTotal.Set(float64(total))
	m.MemoryPoolUsed.Set(float64(used))
	m.MemoryPoolFree.Set(float64(free))
	m.MemoryPoolPeakUsage.Set(float64(peak))
}

// UpdateNUMAStats updates NUMA-related metrics.
func (m *Metrics) UpdateNUMAStats(nodeID int, available bool, memoryByNode map[int]int64) {
	m.NUMANodeID.Set(float64(nodeID))
	if available {
		m.NUMAAvailable.Set(1)
	} else {
		m.NUMAAvailable.Set(0)
	}

	for node, memMB := range memoryByNode {
		m.NUMAMemoryMB.WithLabelValues(string(rune('0' + node))).Set(float64(memMB))
	}
}
