package background

import (
	"log"
	"sync"
	"time"

	"github.com/penguintechinc/project-template/services/go-backend/internal/license"
)

// KeepaliveManager manages license keepalive background task.
type KeepaliveManager struct {
	ticker  *time.Ticker
	done    chan bool
	once    sync.Once
	running bool
}

var (
	keepaliveInstance *KeepaliveManager
	keepaliveLock     sync.Mutex
)

// GetKeepaliveManager returns singleton keepalive manager instance.
func GetKeepaliveManager() *KeepaliveManager {
	keepaliveLock.Lock()
	defer keepaliveLock.Unlock()

	if keepaliveInstance == nil {
		keepaliveInstance = &KeepaliveManager{
			done: make(chan bool),
		}
	}

	return keepaliveInstance
}

// Start starts the keepalive background task.
func (km *KeepaliveManager) Start() {
	km.once.Do(func() {
		km.running = true
		go km.loop()
		log.Println("License keepalive task started")
	})
}

// Stop stops the keepalive background task.
func (km *KeepaliveManager) Stop() {
	if km.running {
		km.running = false
		km.done <- true
		if km.ticker != nil {
			km.ticker.Stop()
		}
		log.Println("License keepalive task stopped")
	}
}

// loop runs the keepalive check loop.
func (km *KeepaliveManager) loop() {
	// Keepalive every 1 hour
	km.ticker = time.NewTicker(1 * time.Hour)
	defer km.ticker.Stop()

	for {
		select {
		case <-km.ticker.C:
			km.performKeepalive()

		case <-km.done:
			return
		}
	}
}

// performKeepalive sends a keepalive to the license server.
func (km *KeepaliveManager) performKeepalive() {
	licenseManager := license.GetManager()

	// Prepare usage statistics
	usageStats := map[string]interface{}{
		"timestamp": time.Now().UTC().Unix(),
	}

	// Send keepalive
	if success := licenseManager.Checkin(usageStats); success {
		log.Println("License keepalive sent successfully")
	} else {
		log.Println("WARNING: License keepalive failed")
	}
}
