// Package server provides the HTTP server for the Go backend.
package server

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus/promhttp"

	"github.com/penguintechinc/project-template/services/go-backend/internal/auth"
	"github.com/penguintechinc/project-template/services/go-backend/internal/background"
	"github.com/penguintechinc/project-template/services/go-backend/internal/config"
	"github.com/penguintechinc/project-template/services/go-backend/internal/health"
	"github.com/penguintechinc/project-template/services/go-backend/internal/license"
	"github.com/penguintechinc/project-template/services/go-backend/internal/memory"
	"github.com/penguintechinc/project-template/services/go-backend/internal/metrics"
)

// Server represents the HTTP server.
type Server struct {
	config         *config.Config
	router         *gin.Engine
	httpServer     *http.Server
	handlers       *Handlers
	metrics        *metrics.Metrics
	memPool        *memory.MemoryPool
	healthStore    *health.Store
	healthPoller   *health.Poller
	healthHandlers *health.Handlers
}

// NewServer creates a new HTTP server instance.
func NewServer(cfg *config.Config) (*Server, error) {
	// Initialize license manager
	licenseManager := license.GetManager()
	if !licenseManager.Validate() {
		if os.Getenv("RELEASE_MODE") == "true" {
			return nil, fmt.Errorf("license validation failed in RELEASE_MODE")
		}
	}
	fmt.Printf("License Status: %v\n", licenseManager.GetStatus())

	// Start background tasks (keepalive)
	keepaliveManager := background.GetKeepaliveManager()
	keepaliveManager.Start()

	// Set Gin mode based on environment
	if cfg.Environment == "production" {
		gin.SetMode(gin.ReleaseMode)
	}

	router := gin.New()

	// Add recovery middleware
	router.Use(gin.Recovery())

	// Initialize metrics
	m := metrics.NewMetrics("go_backend")

	// Add logging and metrics middleware
	router.Use(loggingMiddleware())
	router.Use(metricsMiddleware(m))

	// Initialize memory pool if enabled
	var memPool *memory.MemoryPool
	if cfg.MemoryPoolSlots > 0 {
		var err error
		memPool, err = memory.NewMemoryPool(cfg.MemoryPoolSlots, cfg.MemoryPoolSlotSize)
		if err != nil {
			return nil, fmt.Errorf("failed to create memory pool: %w", err)
		}
	}

	// Initialize handlers
	handlers := NewHandlers(cfg.Version, memPool, cfg.XDPEnabled, cfg.XDPMode, cfg.XDPInterface)

	// Initialize health polling engine
	healthStore := health.NewStore()
	healthMetrics := health.NewMetrics("go_backend")
	healthPoller := health.NewPoller(healthStore, healthMetrics, health.DefaultPollerConfig())
	healthHandlers := health.NewHandlers(healthStore, healthPoller)

	server := &Server{
		config:         cfg,
		router:         router,
		handlers:       handlers,
		metrics:        m,
		memPool:        memPool,
		healthStore:    healthStore,
		healthPoller:   healthPoller,
		healthHandlers: healthHandlers,
	}

	// Register routes
	server.registerRoutes()

	// Start health poller
	server.healthPoller.Start()

	return server, nil
}

// registerRoutes sets up all HTTP routes.
func (s *Server) registerRoutes() {
	// Health check endpoints (unprotected)
	s.router.GET("/healthz", s.handlers.HealthCheck)
	s.router.GET("/readyz", s.handlers.ReadinessCheck)

	// Metrics endpoint (unprotected)
	s.router.GET("/metrics", gin.WrapH(promhttp.Handler()))

	// API v1 routes
	v1 := s.router.Group("/api/v1")
	{
		// Unprotected endpoints
		v1.GET("/status", s.handlers.Status)
		v1.GET("/license/status", s.handlers.LicenseStatus)

		// Protected endpoints (require JWT authentication)
		jwtSecret := os.Getenv("JWT_SECRET_KEY")
		if jwtSecret == "" {
			jwtSecret = "default-secret-key" // Should use strong secret in production
		}

		protected := v1.Group("")
		protected.Use(auth.JWTMiddleware(jwtSecret))
		{
			protected.GET("/hello", s.handlers.Hello)

			// Memory pool endpoints
			protected.POST("/packet/forward", s.handlers.PacketForward)
			protected.GET("/memory/stats", s.handlers.MemoryPoolStats)

			// NUMA information
			protected.GET("/numa/info", s.handlers.NUMAInfo)

			// Team endpoints
			protected.GET("/teams/:id/stats", s.handlers.TeamStats)

			// Health polling endpoints
			protected.GET("/health", s.healthHandlers.GetAll)
			protected.GET("/health/summary", s.healthHandlers.Summary)
			protected.GET("/health/:id", s.healthHandlers.GetProduct)
			protected.POST("/health/register", s.healthHandlers.Register)
			protected.DELETE("/health/:id", s.healthHandlers.Remove)
		}
	}
}

// Start starts the HTTP server.
func (s *Server) Start() error {
	addr := fmt.Sprintf("%s:%d", s.config.Host, s.config.Port)

	s.httpServer = &http.Server{
		Addr:         addr,
		Handler:      s.router,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	return s.httpServer.ListenAndServe()
}

// Shutdown gracefully shuts down the server.
func (s *Server) Shutdown(ctx context.Context) error {
	// Stop background tasks
	keepaliveManager := background.GetKeepaliveManager()
	keepaliveManager.Stop()

	// Stop health poller
	if s.healthPoller != nil {
		s.healthPoller.Stop()
	}

	// Close memory pool
	if s.memPool != nil {
		s.memPool.Close()
	}

	// Shutdown HTTP server
	if s.httpServer != nil {
		return s.httpServer.Shutdown(ctx)
	}

	return nil
}

// loggingMiddleware provides request logging.
func loggingMiddleware() gin.HandlerFunc {
	return gin.LoggerWithConfig(gin.LoggerConfig{
		SkipPaths: []string{"/healthz", "/readyz", "/metrics"},
	})
}

// metricsMiddleware records request metrics.
func metricsMiddleware(m *metrics.Metrics) gin.HandlerFunc {
	return func(c *gin.Context) {
		start := time.Now()

		m.HTTPActiveRequests.Inc()
		defer m.HTTPActiveRequests.Dec()

		c.Next()

		duration := time.Since(start).Seconds()
		status := fmt.Sprintf("%d", c.Writer.Status())

		m.RecordHTTPRequest(c.Request.Method, c.FullPath(), status, duration)
	}
}
