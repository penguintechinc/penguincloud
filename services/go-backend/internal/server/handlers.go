// Package server provides HTTP handlers for the Go backend.
package server

import (
	"net/http"
	"runtime"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/penguintechinc/project-template/services/go-backend/internal/license"
	"github.com/penguintechinc/project-template/services/go-backend/internal/memory"
	"github.com/penguintechinc/project-template/services/go-backend/internal/xdp"
)

// HealthResponse is the response for health check endpoints.
type HealthResponse struct {
	Status    string `json:"status"`
	Timestamp string `json:"timestamp"`
}

// StatusResponse is the response for the status endpoint.
type StatusResponse struct {
	Status       string            `json:"status"`
	Service      string            `json:"service"`
	Version      string            `json:"version"`
	Timestamp    string            `json:"timestamp"`
	Uptime       string            `json:"uptime"`
	GoVersion    string            `json:"go_version"`
	NumCPU       int               `json:"num_cpu"`
	NumGoroutine int               `json:"num_goroutine"`
	NUMA         *NUMAStatus       `json:"numa,omitempty"`
	XDP          *XDPStatus        `json:"xdp,omitempty"`
	MemoryPool   *MemoryPoolStatus `json:"memory_pool,omitempty"`
}

// NUMAStatus represents NUMA topology status.
type NUMAStatus struct {
	Available   bool          `json:"available"`
	NodeCount   int           `json:"node_count"`
	CurrentNode int           `json:"current_node"`
	MemoryMB    map[int]int64 `json:"memory_mb,omitempty"`
}

// XDPStatus represents XDP availability status.
type XDPStatus struct {
	Supported bool   `json:"supported"`
	Mode      string `json:"mode,omitempty"`
	Interface string `json:"interface,omitempty"`
}

// MemoryPoolStatus represents memory pool status.
type MemoryPoolStatus struct {
	TotalSlots  int   `json:"total_slots"`
	UsedSlots   int   `json:"used_slots"`
	FreeSlots   int   `json:"free_slots"`
	SlotSize    int   `json:"slot_size"`
	TotalMemory int   `json:"total_memory_bytes"`
	PeakUsage   int32 `json:"peak_usage"`
}

// Handlers holds all HTTP handlers and their dependencies.
type Handlers struct {
	startTime  time.Time
	version    string
	memoryPool *memory.MemoryPool
	xdpEnabled bool
	xdpMode    string
	xdpIface   string
	dbClient   interface{} // *db.Client (avoid import cycle)
}

// NewHandlers creates a new Handlers instance.
func NewHandlers(version string, memPool *memory.MemoryPool, xdpEnabled bool, xdpMode, xdpIface string) *Handlers {
	return &Handlers{
		startTime:  time.Now(),
		version:    version,
		memoryPool: memPool,
		xdpEnabled: xdpEnabled,
		xdpMode:    xdpMode,
		xdpIface:   xdpIface,
		dbClient:   nil,
	}
}

// SetDBClient sets the database client.
func (h *Handlers) SetDBClient(dbClient interface{}) {
	h.dbClient = dbClient
}

// HealthCheck handles GET /healthz
func (h *Handlers) HealthCheck(c *gin.Context) {
	c.JSON(http.StatusOK, HealthResponse{
		Status:    "healthy",
		Timestamp: time.Now().UTC().Format(time.RFC3339),
	})
}

// ReadinessCheck handles GET /readyz
func (h *Handlers) ReadinessCheck(c *gin.Context) {
	c.JSON(http.StatusOK, HealthResponse{
		Status:    "ready",
		Timestamp: time.Now().UTC().Format(time.RFC3339),
	})
}

// Status handles GET /api/v1/status
func (h *Handlers) Status(c *gin.Context) {
	numaInfo := memory.GetNUMAInfo()

	response := StatusResponse{
		Status:       "running",
		Service:      "go-backend",
		Version:      h.version,
		Timestamp:    time.Now().UTC().Format(time.RFC3339),
		Uptime:       time.Since(h.startTime).String(),
		GoVersion:    runtime.Version(),
		NumCPU:       runtime.NumCPU(),
		NumGoroutine: runtime.NumGoroutine(),
		NUMA: &NUMAStatus{
			Available:   numaInfo.Available,
			NodeCount:   numaInfo.NodeCount,
			CurrentNode: numaInfo.CurrentNode,
			MemoryMB:    numaInfo.MemoryMB,
		},
		XDP: &XDPStatus{
			Supported: xdp.IsXDPSupported(),
			Mode:      h.xdpMode,
			Interface: h.xdpIface,
		},
	}

	if h.memoryPool != nil {
		stats := h.memoryPool.Stats()
		response.MemoryPool = &MemoryPoolStatus{
			TotalSlots:  stats.TotalSlots,
			UsedSlots:   stats.UsedSlots,
			FreeSlots:   stats.FreeSlots,
			SlotSize:    stats.SlotSize,
			TotalMemory: stats.TotalMemory,
			PeakUsage:   stats.PeakUsage,
		}
	}

	c.JSON(http.StatusOK, response)
}

// Hello handles GET /api/v1/hello
func (h *Handlers) Hello(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"message":   "Hello from Go high-performance backend!",
		"timestamp": time.Now().UTC().Format(time.RFC3339),
		"service":   "go-backend",
	})
}

// PacketForward handles POST /api/v1/packet/forward
// This is an example endpoint demonstrating memory pool usage.
func (h *Handlers) PacketForward(c *gin.Context) {
	if h.memoryPool == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{
			"error": "Memory pool not initialized",
		})
		return
	}

	// Acquire a buffer from the pool
	slotIdx, buffer, err := h.memoryPool.Acquire()
	if err != nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{
			"error": "Memory pool exhausted",
		})
		return
	}

	// Simulate packet processing
	// In a real implementation, this would process actual packet data
	_ = buffer

	// Release the buffer back to the pool
	if err := h.memoryPool.Release(slotIdx); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"error": "Failed to release buffer",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message":   "Packet processed successfully",
		"slot_used": slotIdx,
		"timestamp": time.Now().UTC().Format(time.RFC3339),
	})
}

// MemoryPoolStats handles GET /api/v1/memory/stats
func (h *Handlers) MemoryPoolStats(c *gin.Context) {
	if h.memoryPool == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{
			"error": "Memory pool not initialized",
		})
		return
	}

	stats := h.memoryPool.Stats()

	c.JSON(http.StatusOK, gin.H{
		"total_slots":  stats.TotalSlots,
		"used_slots":   stats.UsedSlots,
		"free_slots":   stats.FreeSlots,
		"slot_size":    stats.SlotSize,
		"total_memory": stats.TotalMemory,
		"total_allocs": stats.TotalAllocs,
		"total_frees":  stats.TotalFrees,
		"peak_usage":   stats.PeakUsage,
		"utilization":  float64(stats.UsedSlots) / float64(stats.TotalSlots) * 100,
	})
}

// NUMAInfo handles GET /api/v1/numa/info
func (h *Handlers) NUMAInfo(c *gin.Context) {
	info := memory.GetNUMAInfo()

	c.JSON(http.StatusOK, gin.H{
		"available":     info.Available,
		"node_count":    info.NodeCount,
		"current_node":  info.CurrentNode,
		"cpus_per_node": info.CPUsPerNode,
		"memory_mb":     info.MemoryMB,
	})
}

// TeamStatsResponse represents team statistics response.
type TeamStatsResponse struct {
	TeamID      string `json:"team_id"`
	Name        string `json:"name"`
	MemberCount int    `json:"member_count"`
	IsActive    bool   `json:"is_active"`
	CreatedAt   string `json:"created_at"`
	Timestamp   string `json:"timestamp"`
}

// TeamStats handles GET /api/v1/teams/:id/stats
// Example endpoint demonstrating JWT authentication and database queries.
func (h *Handlers) TeamStats(c *gin.Context) {
	teamID := c.Param("id")
	if teamID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Team ID required"})
		return
	}

	// Check if user is authenticated (JWT middleware handles this)
	userID := c.GetString("user_id")
	if userID == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	// Database client would be used here for actual queries
	// For now, return example response
	response := TeamStatsResponse{
		TeamID:      teamID,
		Name:        "Example Team",
		MemberCount: 5,
		IsActive:    true,
		CreatedAt:   time.Now().Add(-30 * 24 * time.Hour).UTC().Format(time.RFC3339),
		Timestamp:   time.Now().UTC().Format(time.RFC3339),
	}

	c.JSON(http.StatusOK, response)
}

// LicenseStatus handles GET /api/v1/license/status
// Returns current license status (admin only)
func (h *Handlers) LicenseStatus(c *gin.Context) {
	licenseManager := license.GetManager()
	status := licenseManager.GetStatus()
	c.JSON(http.StatusOK, status)
}
