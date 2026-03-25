// Package health provides a concurrent health polling engine for monitoring
// PenguinTech product endpoints across all tenants.
package health

import (
	"sync"
	"time"
)

// Status represents the health status of a product endpoint.
type Status string

const (
	StatusHealthy   Status = "healthy"
	StatusDegraded  Status = "degraded"
	StatusUnhealthy Status = "unhealthy"
	StatusUnknown   Status = "unknown"
)

// EndpointConfig holds the configuration for a health check endpoint.
type EndpointConfig struct {
	ID              int    `json:"id"`
	TenantID        int    `json:"tenant_id"`
	ProductType     string `json:"product_type"`
	DisplayName     string `json:"display_name"`
	BaseURL         string `json:"base_url"`
	HealthEndpoint  string `json:"health_endpoint"`
	AuthType        string `json:"auth_type"`
	AuthCredentials string `json:"auth_credentials"`
}

// EndpointHealth holds the health status of a single endpoint.
type EndpointHealth struct {
	ID             int           `json:"id"`
	TenantID       int           `json:"tenant_id"`
	ProductType    string        `json:"product_type"`
	DisplayName    string        `json:"display_name"`
	Status         Status        `json:"status"`
	ResponseTimeMs int64         `json:"response_time_ms"`
	LastCheck      time.Time     `json:"last_check"`
	LastHealthy    time.Time     `json:"last_healthy,omitempty"`
	ErrorMessage   string        `json:"error_message,omitempty"`
	CheckCount     int64         `json:"check_count"`
	FailCount      int64         `json:"fail_count"`
	UptimePercent  float64       `json:"uptime_percent"`
}

// HealthMatrix holds the aggregated health data across all endpoints.
type HealthMatrix struct {
	Endpoints  []EndpointHealth       `json:"endpoints"`
	Summary    HealthSummary          `json:"summary"`
	LastUpdate time.Time              `json:"last_update"`
}

// HealthSummary holds aggregated health counts.
type HealthSummary struct {
	Total     int `json:"total"`
	Healthy   int `json:"healthy"`
	Degraded  int `json:"degraded"`
	Unhealthy int `json:"unhealthy"`
	Unknown   int `json:"unknown"`
}

// Store provides thread-safe storage for health check results.
type Store struct {
	mu        sync.RWMutex
	endpoints map[int]*EndpointHealth
}

// NewStore creates a new health store.
func NewStore() *Store {
	return &Store{
		endpoints: make(map[int]*EndpointHealth),
	}
}

// Update stores the health check result for an endpoint.
func (s *Store) Update(id int, status Status, responseTimeMs int64, errMsg string) {
	s.mu.Lock()
	defer s.mu.Unlock()

	ep, exists := s.endpoints[id]
	if !exists {
		ep = &EndpointHealth{ID: id}
		s.endpoints[id] = ep
	}

	ep.Status = status
	ep.ResponseTimeMs = responseTimeMs
	ep.LastCheck = time.Now()
	ep.ErrorMessage = errMsg
	ep.CheckCount++

	if status == StatusHealthy {
		ep.LastHealthy = time.Now()
	} else {
		ep.FailCount++
	}

	if ep.CheckCount > 0 {
		ep.UptimePercent = float64(ep.CheckCount-ep.FailCount) / float64(ep.CheckCount) * 100
	}
}

// Register adds or updates an endpoint's metadata in the store.
func (s *Store) Register(cfg EndpointConfig) {
	s.mu.Lock()
	defer s.mu.Unlock()

	ep, exists := s.endpoints[cfg.ID]
	if !exists {
		ep = &EndpointHealth{
			ID:       cfg.ID,
			Status:   StatusUnknown,
		}
		s.endpoints[cfg.ID] = ep
	}

	ep.TenantID = cfg.TenantID
	ep.ProductType = cfg.ProductType
	ep.DisplayName = cfg.DisplayName
}

// Remove deletes an endpoint from the store.
func (s *Store) Remove(id int) {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.endpoints, id)
}

// Get returns the health status for a single endpoint.
func (s *Store) Get(id int) (EndpointHealth, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	ep, exists := s.endpoints[id]
	if !exists {
		return EndpointHealth{}, false
	}
	return *ep, true
}

// GetAll returns health data for all endpoints.
func (s *Store) GetAll() HealthMatrix {
	s.mu.RLock()
	defer s.mu.RUnlock()

	matrix := HealthMatrix{
		Endpoints:  make([]EndpointHealth, 0, len(s.endpoints)),
		LastUpdate: time.Now(),
	}

	for _, ep := range s.endpoints {
		matrix.Endpoints = append(matrix.Endpoints, *ep)
		matrix.Summary.Total++
		switch ep.Status {
		case StatusHealthy:
			matrix.Summary.Healthy++
		case StatusDegraded:
			matrix.Summary.Degraded++
		case StatusUnhealthy:
			matrix.Summary.Unhealthy++
		default:
			matrix.Summary.Unknown++
		}
	}

	return matrix
}

// GetByTenant returns health data for a specific tenant's endpoints.
func (s *Store) GetByTenant(tenantID int) HealthMatrix {
	s.mu.RLock()
	defer s.mu.RUnlock()

	matrix := HealthMatrix{
		Endpoints:  make([]EndpointHealth, 0),
		LastUpdate: time.Now(),
	}

	for _, ep := range s.endpoints {
		if ep.TenantID != tenantID {
			continue
		}
		matrix.Endpoints = append(matrix.Endpoints, *ep)
		matrix.Summary.Total++
		switch ep.Status {
		case StatusHealthy:
			matrix.Summary.Healthy++
		case StatusDegraded:
			matrix.Summary.Degraded++
		case StatusUnhealthy:
			matrix.Summary.Unhealthy++
		default:
			matrix.Summary.Unknown++
		}
	}

	return matrix
}

// EndpointCount returns the number of registered endpoints.
func (s *Store) EndpointCount() int {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return len(s.endpoints)
}
