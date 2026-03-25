package health

import (
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"
)

// Handlers provides HTTP endpoints for the health polling engine.
type Handlers struct {
	store  *Store
	poller *Poller
}

// NewHandlers creates new health API handlers.
func NewHandlers(store *Store, poller *Poller) *Handlers {
	return &Handlers{store: store, poller: poller}
}

// GetAll handles GET /api/v1/health — returns health matrix for all endpoints.
func (h *Handlers) GetAll(c *gin.Context) {
	tenantIDStr := c.Query("tenant_id")
	if tenantIDStr != "" {
		tenantID, err := strconv.Atoi(tenantIDStr)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid tenant_id"})
			return
		}
		c.JSON(http.StatusOK, h.store.GetByTenant(tenantID))
		return
	}
	c.JSON(http.StatusOK, h.store.GetAll())
}

// GetProduct handles GET /api/v1/health/:id — returns health for one endpoint.
func (h *Handlers) GetProduct(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.Atoi(idStr)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid id"})
		return
	}

	ep, found := h.store.Get(id)
	if !found {
		c.JSON(http.StatusNotFound, gin.H{"error": "endpoint not found"})
		return
	}
	c.JSON(http.StatusOK, ep)
}

// Register handles POST /api/v1/health/register — registers an endpoint for polling.
func (h *Handlers) Register(c *gin.Context) {
	var cfg EndpointConfig
	if err := c.ShouldBindJSON(&cfg); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if cfg.ID == 0 || cfg.BaseURL == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "id and base_url are required"})
		return
	}

	if cfg.HealthEndpoint == "" {
		cfg.HealthEndpoint = "/healthz"
	}

	h.poller.RegisterEndpoint(cfg)
	c.JSON(http.StatusOK, gin.H{"status": "registered", "id": cfg.ID})
}

// Remove handles DELETE /api/v1/health/:id — removes an endpoint from polling.
func (h *Handlers) Remove(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.Atoi(idStr)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid id"})
		return
	}

	h.poller.RemoveEndpoint(id)
	c.JSON(http.StatusOK, gin.H{"status": "removed", "id": id})
}

// Summary handles GET /api/v1/health/summary — returns summary counts.
func (h *Handlers) Summary(c *gin.Context) {
	matrix := h.store.GetAll()
	c.JSON(http.StatusOK, matrix.Summary)
}
