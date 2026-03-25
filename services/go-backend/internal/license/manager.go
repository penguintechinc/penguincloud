package license

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"sync"
	"time"
)

// Manager handles license validation and feature gating.
type Manager struct {
	licenseKey      string
	serverURL       string
	productName     string
	releaseMode     bool
	client          *http.Client
	validationCache map[string]interface{}
	featuresCache   map[string]interface{}
	cacheMutex      sync.RWMutex
	cacheExpiry     int64
	fullCacheExpiry int64
	once            sync.Once
	instance        *Manager
}

var (
	managerInstance *Manager
	managerLock     sync.Mutex
)

// GetManager returns singleton license manager instance.
func GetManager() *Manager {
	managerLock.Lock()
	defer managerLock.Unlock()

	if managerInstance == nil {
		managerInstance = &Manager{
			licenseKey:      os.Getenv("LICENSE_KEY"),
			serverURL:       getEnvOrDefault("LICENSE_SERVER_URL", "https://license.penguintech.io"),
			productName:     getEnvOrDefault("PRODUCT_NAME", "project-template"),
			releaseMode:     os.Getenv("RELEASE_MODE") == "true",
			client:          &http.Client{Timeout: 5 * time.Second},
			validationCache: make(map[string]interface{}),
			featuresCache:   make(map[string]interface{}),
		}
	}

	return managerInstance
}

// Validate validates license on startup.
func (m *Manager) Validate() bool {
	if !m.releaseMode {
		log.Println("License validation skipped (RELEASE_MODE=false)")
		return true
	}

	if m.licenseKey == "" {
		log.Println("ERROR: LICENSE_KEY not set")
		return false
	}

	payload := map[string]string{
		"license_key":  m.licenseKey,
		"product_name": m.productName,
	}

	data, err := json.Marshal(payload)
	if err != nil {
		log.Printf("ERROR: Failed to marshal license validation request: %v\n", err)
		return false
	}

	resp, err := m.client.Post(
		fmt.Sprintf("%s/api/v2/validate", m.serverURL),
		"application/json",
		bytes.NewBuffer(data),
	)
	if err != nil {
		log.Printf("ERROR: License validation request failed: %v\n", err)
		return false
	}
	defer resp.Body.Close()

	var result map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		log.Printf("ERROR: Failed to decode license validation response: %v\n", err)
		return false
	}

	if valid, ok := result["valid"].(bool); ok && valid {
		m.cacheMutex.Lock()
		m.validationCache = result
		m.fullCacheExpiry = time.Now().Unix() + (7 * 24 * 3600)
		m.cacheMutex.Unlock()

		tier := "unknown"
		if tierVal, ok := result["tier"].(string); ok {
			tier = tierVal
		}
		expiresAt := "unknown"
		if expiresVal, ok := result["expires_at"].(string); ok {
			expiresAt = expiresVal
		}

		log.Printf("License validated. Tier: %s, Expires: %s\n", tier, expiresAt)
		return true
	}

	log.Printf("ERROR: License validation failed: %v\n", result)
	return false
}

// IsFeatureEnabled checks if a feature is enabled.
func (m *Manager) IsFeatureEnabled(featureName string) bool {
	if !m.releaseMode {
		return true
	}

	// Refresh cache if expired
	if time.Now().Unix() > m.cacheExpiry {
		m.refreshFeatures()
	}

	m.cacheMutex.RLock()
	features, ok := m.featuresCache["features"].(map[string]interface{})
	m.cacheMutex.RUnlock()

	if !ok {
		return false
	}

	feature, ok := features[featureName].(map[string]interface{})
	if !ok {
		return false
	}

	enabled, ok := feature["enabled"].(bool)
	return ok && enabled
}

// refreshFeatures refreshes feature cache from server.
func (m *Manager) refreshFeatures() {
	payload := map[string]string{
		"license_key":  m.licenseKey,
		"product_name": m.productName,
	}

	data, err := json.Marshal(payload)
	if err != nil {
		log.Printf("WARNING: Failed to marshal features request: %v\n", err)
		return
	}

	resp, err := m.client.Post(
		fmt.Sprintf("%s/api/v2/features", m.serverURL),
		"application/json",
		bytes.NewBuffer(data),
	)
	if err != nil {
		log.Printf("WARNING: Failed to refresh features: %v\n", err)
		return
	}
	defer resp.Body.Close()

	var result map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		log.Printf("WARNING: Failed to decode features response: %v\n", err)
		return
	}

	m.cacheMutex.Lock()
	m.featuresCache = result
	m.cacheExpiry = time.Now().Unix() + (5 * 60) // 5 minutes
	m.cacheMutex.Unlock()
}

// GetTier returns the license tier.
func (m *Manager) GetTier() string {
	m.cacheMutex.RLock()
	defer m.cacheMutex.RUnlock()

	tier, ok := m.validationCache["tier"].(string)
	if !ok {
		return "community"
	}
	return tier
}

// GetLimits returns usage limits.
func (m *Manager) GetLimits() map[string]interface{} {
	m.cacheMutex.RLock()
	defer m.cacheMutex.RUnlock()

	limits, ok := m.validationCache["limits"].(map[string]interface{})
	if !ok {
		return make(map[string]interface{})
	}
	return limits
}

// Checkin sends keepalive to license server.
func (m *Manager) Checkin(usageStats map[string]interface{}) bool {
	if !m.releaseMode || m.licenseKey == "" {
		return true
	}

	payload := map[string]interface{}{
		"license_key":  m.licenseKey,
		"product_name": m.productName,
		"timestamp":    time.Now().UTC().Format(time.RFC3339),
	}

	if usageStats != nil {
		payload["usage_stats"] = usageStats
	}

	data, err := json.Marshal(payload)
	if err != nil {
		log.Printf("WARNING: Failed to marshal checkin request: %v\n", err)
		return false
	}

	resp, err := m.client.Post(
		fmt.Sprintf("%s/api/v2/keepalive", m.serverURL),
		"application/json",
		bytes.NewBuffer(data),
	)
	if err != nil {
		log.Printf("WARNING: Checkin failed: %v\n", err)
		return false
	}
	defer resp.Body.Close()

	return resp.StatusCode >= 200 && resp.StatusCode < 300
}

// GetStatus returns current license status.
func (m *Manager) GetStatus() map[string]interface{} {
	m.cacheMutex.RLock()
	defer m.cacheMutex.RUnlock()

	valid := len(m.validationCache) > 0
	features := m.featuresCache["features"]
	if features == nil {
		features = make(map[string]interface{})
	}

	expiresAt := "unknown"
	if exp, ok := m.validationCache["expires_at"]; ok {
		expiresAt = exp
	}

	limits := m.validationCache["limits"]
	if limits == nil {
		limits = make(map[string]interface{})
	}

	return map[string]interface{}{
		"valid":      valid,
		"tier":       m.GetTier(),
		"features":   features,
		"expires_at": expiresAt,
		"limits":     limits,
	}
}

// Helper function
func getEnvOrDefault(key, defaultValue string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return defaultValue
}
