package health

import (
	"context"
	"crypto/tls"
	"fmt"
	"log"
	"net/http"
	"sync"
	"time"
)

// PollerConfig holds configuration for the health poller.
type PollerConfig struct {
	Interval    time.Duration
	Timeout     time.Duration
	Concurrency int
}

// DefaultPollerConfig returns the default poller configuration.
func DefaultPollerConfig() PollerConfig {
	return PollerConfig{
		Interval:    15 * time.Second,
		Timeout:     5 * time.Second,
		Concurrency: 50,
	}
}

// Poller runs periodic health checks against all registered endpoints.
type Poller struct {
	store      *Store
	config     PollerConfig
	metrics    *Metrics
	client     *http.Client
	mu         sync.RWMutex
	endpoints  map[int]EndpointConfig
	cancel     context.CancelFunc
	wg         sync.WaitGroup
}

// NewPoller creates a new health poller.
func NewPoller(store *Store, metrics *Metrics, cfg PollerConfig) *Poller {
	client := &http.Client{
		Timeout: cfg.Timeout,
		Transport: &http.Transport{
			MaxIdleConns:        cfg.Concurrency * 2,
			MaxIdleConnsPerHost: 2,
			IdleConnTimeout:     30 * time.Second,
			TLSClientConfig: &tls.Config{
				InsecureSkipVerify: false,
			},
		},
	}

	return &Poller{
		store:     store,
		config:    cfg,
		metrics:   metrics,
		client:    client,
		endpoints: make(map[int]EndpointConfig),
	}
}

// Start begins the polling loop.
func (p *Poller) Start() {
	ctx, cancel := context.WithCancel(context.Background())
	p.cancel = cancel

	p.wg.Add(1)
	go func() {
		defer p.wg.Done()
		log.Printf("Health poller started (interval=%s, concurrency=%d)",
			p.config.Interval, p.config.Concurrency)

		// Run immediately on start
		p.pollAll(ctx)

		ticker := time.NewTicker(p.config.Interval)
		defer ticker.Stop()

		for {
			select {
			case <-ctx.Done():
				log.Println("Health poller stopped")
				return
			case <-ticker.C:
				p.pollAll(ctx)
			}
		}
	}()
}

// Stop halts the polling loop and waits for in-flight checks to complete.
func (p *Poller) Stop() {
	if p.cancel != nil {
		p.cancel()
	}
	p.wg.Wait()
}

// RegisterEndpoint adds an endpoint to the polling list.
func (p *Poller) RegisterEndpoint(cfg EndpointConfig) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.endpoints[cfg.ID] = cfg
	p.store.Register(cfg)
	log.Printf("Health poller: registered endpoint %d (%s at %s)",
		cfg.ID, cfg.ProductType, cfg.BaseURL)
}

// RemoveEndpoint removes an endpoint from the polling list.
func (p *Poller) RemoveEndpoint(id int) {
	p.mu.Lock()
	defer p.mu.Unlock()
	delete(p.endpoints, id)
	p.store.Remove(id)
	log.Printf("Health poller: removed endpoint %d", id)
}

// pollAll runs health checks against all registered endpoints concurrently.
func (p *Poller) pollAll(ctx context.Context) {
	p.mu.RLock()
	configs := make([]EndpointConfig, 0, len(p.endpoints))
	for _, cfg := range p.endpoints {
		configs = append(configs, cfg)
	}
	p.mu.RUnlock()

	if len(configs) == 0 {
		return
	}

	// Use a semaphore to limit concurrency
	sem := make(chan struct{}, p.config.Concurrency)
	var wg sync.WaitGroup

	for _, cfg := range configs {
		select {
		case <-ctx.Done():
			return
		default:
		}

		wg.Add(1)
		sem <- struct{}{}

		go func(ep EndpointConfig) {
			defer wg.Done()
			defer func() { <-sem }()
			p.checkEndpoint(ctx, ep)
		}(cfg)
	}

	wg.Wait()
}

// checkEndpoint performs a single health check against one endpoint.
func (p *Poller) checkEndpoint(ctx context.Context, cfg EndpointConfig) {
	healthURL := fmt.Sprintf("%s%s", cfg.BaseURL, cfg.HealthEndpoint)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, healthURL, nil)
	if err != nil {
		p.store.Update(cfg.ID, StatusUnhealthy, 0, fmt.Sprintf("invalid request: %v", err))
		if p.metrics != nil {
			p.metrics.RecordCheck(cfg.ProductType, string(StatusUnhealthy), 0)
		}
		return
	}

	// Add auth headers based on auth type
	switch cfg.AuthType {
	case "bearer":
		if cfg.AuthCredentials != "" {
			req.Header.Set("Authorization", "Bearer "+cfg.AuthCredentials)
		}
	case "api_key":
		if cfg.AuthCredentials != "" {
			req.Header.Set("X-API-Key", cfg.AuthCredentials)
		}
	case "basic":
		if cfg.AuthCredentials != "" {
			req.Header.Set("Authorization", "Basic "+cfg.AuthCredentials)
		}
	}

	start := time.Now()
	resp, err := p.client.Do(req)
	durationMs := time.Since(start).Milliseconds()

	if err != nil {
		p.store.Update(cfg.ID, StatusUnhealthy, durationMs, err.Error())
		if p.metrics != nil {
			p.metrics.RecordCheck(cfg.ProductType, string(StatusUnhealthy), float64(durationMs)/1000)
		}
		return
	}
	defer resp.Body.Close()

	var status Status
	switch {
	case resp.StatusCode >= 200 && resp.StatusCode < 300:
		status = StatusHealthy
	case resp.StatusCode == 429 || (resp.StatusCode >= 500 && resp.StatusCode < 600):
		status = StatusDegraded
	default:
		status = StatusUnhealthy
	}

	errMsg := ""
	if status != StatusHealthy {
		errMsg = fmt.Sprintf("HTTP %d", resp.StatusCode)
	}

	p.store.Update(cfg.ID, status, durationMs, errMsg)
	if p.metrics != nil {
		p.metrics.RecordCheck(cfg.ProductType, string(status), float64(durationMs)/1000)
	}
}
