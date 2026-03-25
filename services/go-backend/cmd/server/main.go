// Package main is the entry point for the Go backend server.
package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"runtime"
	"syscall"
	"time"

	"github.com/penguintechinc/project-template/services/go-backend/internal/config"
	"github.com/penguintechinc/project-template/services/go-backend/internal/memory"
	"github.com/penguintechinc/project-template/services/go-backend/internal/server"
	"github.com/penguintechinc/project-template/services/go-backend/internal/xdp"
)

func main() {
	log.SetFlags(log.LstdFlags | log.Lshortfile)
	log.Println("Starting Go high-performance backend...")

	// Load configuration
	cfg := config.Load()

	log.Printf("Configuration loaded:")
	log.Printf("  Environment: %s", cfg.Environment)
	log.Printf("  Host: %s", cfg.Host)
	log.Printf("  Port: %d", cfg.Port)
	log.Printf("  NUMA Enabled: %v", cfg.NUMAEnabled)
	log.Printf("  XDP Enabled: %v", cfg.XDPEnabled)

	// Set GOMAXPROCS based on available CPUs
	numCPU := runtime.NumCPU()
	runtime.GOMAXPROCS(numCPU)
	log.Printf("  GOMAXPROCS: %d", numCPU)

	// Initialize NUMA if enabled
	if cfg.NUMAEnabled {
		initNUMA()
	}

	// Set memlock rlimit for BPF if XDP is enabled
	if cfg.XDPEnabled {
		if err := xdp.SetRLimitMemlock(); err != nil {
			log.Printf("Warning: Failed to set memlock rlimit: %v", err)
		}
	}

	// Create and start server
	srv, err := server.NewServer(cfg)
	if err != nil {
		log.Fatalf("Failed to create server: %v", err)
	}

	// Start server in a goroutine
	go func() {
		log.Printf("Server listening on %s:%d", cfg.Host, cfg.Port)
		if err := srv.Start(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Server failed: %v", err)
		}
	}()

	// Wait for interrupt signal
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	log.Println("Shutting down server...")

	// Give outstanding requests 30 seconds to complete
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		log.Printf("Server forced to shutdown: %v", err)
	}

	log.Println("Server stopped")
}

// initNUMA initializes NUMA-aware settings.
func initNUMA() {
	info := memory.GetNUMAInfo()

	if !info.Available {
		log.Println("NUMA: Not available on this system")
		return
	}

	log.Printf("NUMA: Available with %d nodes", info.NodeCount)
	log.Printf("NUMA: Current node: %d", info.CurrentNode)

	// Log memory per node
	for node, memMB := range info.MemoryMB {
		log.Printf("NUMA: Node %d has %d MB memory", node, memMB)
	}

	// Log CPUs per node
	for node, cpus := range info.CPUsPerNode {
		log.Printf("NUMA: Node %d has CPUs %v", node, cpus)
	}

	// Optionally bind to a specific node (node 0 by default)
	if err := memory.BindToNUMANode(0); err != nil {
		log.Printf("NUMA: Warning - failed to bind to node 0: %v", err)
	} else {
		log.Println("NUMA: Successfully bound to node 0")
	}
}
