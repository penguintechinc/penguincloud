package killkrill

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"time"
)

// Client for KillKrill integration
type Client struct {
	apiURL       string
	grpcURL      string
	clientID     string
	clientSecret string
	enabled      bool
	httpClient   *http.Client
	logQueue     []map[string]interface{}
	metricQueue  []map[string]interface{}
	token        string
	tokenExpiry  time.Time
}

// LogEntry represents a structured log entry in ECS format
type LogEntry struct {
	Timestamp   string                 `json:"@timestamp"`
	Level       string                 `json:"log.level"`
	Message     string                 `json:"message"`
	ServiceName string                 `json:"service.name"`
	Extra       map[string]interface{} `json:"-"`
}

// MetricEntry represents a metric entry
type MetricEntry struct {
	Name      string            `json:"name"`
	Value     float64           `json:"value"`
	Type      string            `json:"type"`
	Timestamp string            `json:"timestamp"`
	Service   string            `json:"service"`
	Labels    map[string]string `json:"labels,omitempty"`
}

// NewClient creates a new KillKrill client
func NewClient(apiURL, grpcURL, clientID, clientSecret string, enabled bool) *Client {
	return &Client{
		apiURL:       apiURL,
		grpcURL:      grpcURL,
		clientID:     clientID,
		clientSecret: clientSecret,
		enabled:      enabled,
		httpClient: &http.Client{
			Timeout: 10 * time.Second,
		},
		logQueue:    make([]map[string]interface{}, 0),
		metricQueue: make([]map[string]interface{}, 0),
	}
}

// Setup initializes the KillKrill connection
func (c *Client) Setup(ctx context.Context) error {
	if !c.enabled {
		log.Println("KillKrill disabled")
		return nil
	}

	if err := c.authenticate(ctx); err != nil {
		log.Printf("Failed to authenticate with KillKrill: %v", err)
		c.enabled = false
		return nil // Graceful degradation
	}

	// Start background flush worker
	go c.flushWorker(ctx)

	log.Println("KillKrill client initialized")
	return nil
}

// authenticate obtains OAuth2 token
func (c *Client) authenticate(ctx context.Context) error {
	payload := map[string]string{
		"client_id":     c.clientID,
		"client_secret": c.clientSecret,
		"grant_type":    "client_credentials",
	}

	jsonData, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to marshal auth payload: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, "POST", c.apiURL+"/auth/token", bytes.NewBuffer(jsonData))
	if err != nil {
		return err
	}

	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("auth request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("auth failed with status %d", resp.StatusCode)
	}

	var result map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return fmt.Errorf("failed to decode auth response: %w", err)
	}

	token, ok := result["access_token"].(string)
	if !ok {
		return fmt.Errorf("no access token in response")
	}

	expiresIn, _ := result["expires_in"].(float64)
	c.token = token
	c.tokenExpiry = time.Now().Add(time.Duration(expiresIn) * time.Second)

	return nil
}

// Log queues a log entry
func (c *Client) Log(level, message string, extra map[string]interface{}) {
	if !c.enabled {
		return
	}

	entry := map[string]interface{}{
		"@timestamp":   time.Now().UTC().Format(time.RFC3339) + "Z",
		"log.level":    level,
		"message":      message,
		"service.name": "go-backend",
	}

	for k, v := range extra {
		entry[k] = v
	}

	c.logQueue = append(c.logQueue, entry)
}

// Metric queues a metric entry
func (c *Client) Metric(name string, value float64, metricType string, labels map[string]string) {
	if !c.enabled {
		return
	}

	entry := map[string]interface{}{
		"name":      name,
		"value":     value,
		"type":      metricType,
		"timestamp": time.Now().UTC().Format(time.RFC3339) + "Z",
		"service":   "go-backend",
	}

	if labels != nil {
		entry["labels"] = labels
	}

	c.metricQueue = append(c.metricQueue, entry)
}

// HealthCheck verifies KillKrill availability
func (c *Client) HealthCheck(ctx context.Context) bool {
	if !c.enabled {
		return false
	}

	req, err := http.NewRequestWithContext(ctx, "GET", c.apiURL+"/health", nil)
	if err != nil {
		log.Printf("Health check request creation failed: %v", err)
		return false
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		log.Printf("KillKrill health check failed: %v", err)
		return false
	}
	defer resp.Body.Close()

	return resp.StatusCode == http.StatusOK
}

// flushWorker periodically flushes queued logs and metrics
func (c *Client) flushWorker(ctx context.Context) {
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			// Flush remaining items before exiting
			c.flush(ctx)
			return
		case <-ticker.C:
			c.flush(ctx)
		}
	}
}

// flush sends queued items to KillKrill
func (c *Client) flush(ctx context.Context) {
	if !c.enabled || (len(c.logQueue) == 0 && len(c.metricQueue) == 0) {
		return
	}

	// Ensure token is valid
	if time.Now().After(c.tokenExpiry) {
		if err := c.authenticate(ctx); err != nil {
			log.Printf("Token refresh failed: %v", err)
			return
		}
	}

	if len(c.logQueue) > 0 {
		if err := c.sendLogs(ctx); err != nil {
			log.Printf("Failed to send logs: %v", err)
		} else {
			c.logQueue = make([]map[string]interface{}, 0)
		}
	}

	if len(c.metricQueue) > 0 {
		if err := c.sendMetrics(ctx); err != nil {
			log.Printf("Failed to send metrics: %v", err)
		} else {
			c.metricQueue = make([]map[string]interface{}, 0)
		}
	}
}

// sendLogs sends queued logs to KillKrill
func (c *Client) sendLogs(ctx context.Context) error {
	if len(c.logQueue) == 0 {
		return nil
	}

	jsonData, err := json.Marshal(c.logQueue)
	if err != nil {
		return fmt.Errorf("failed to marshal logs: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, "POST", c.apiURL+"/api/v1/logs", bytes.NewBuffer(jsonData))
	if err != nil {
		return err
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+c.token)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("log request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("log submission failed with status %d: %s", resp.StatusCode, string(body))
	}

	return nil
}

// sendMetrics sends queued metrics to KillKrill
func (c *Client) sendMetrics(ctx context.Context) error {
	if len(c.metricQueue) == 0 {
		return nil
	}

	jsonData, err := json.Marshal(c.metricQueue)
	if err != nil {
		return fmt.Errorf("failed to marshal metrics: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, "POST", c.apiURL+"/api/v1/metrics", bytes.NewBuffer(jsonData))
	if err != nil {
		return err
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+c.token)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("metric request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("metric submission failed with status %d: %s", resp.StatusCode, string(body))
	}

	return nil
}

// Helper functions for common metrics
func TrackAPIRequest(c *Client, endpoint, method string, status int, durationMs float64) {
	labels := map[string]string{
		"endpoint": endpoint,
		"status":   fmt.Sprintf("%d", status),
	}
	c.Metric("api.request."+method, 1, "counter", labels)
	c.Metric("api.request.duration_ms", durationMs, "histogram", labels)
}

func TrackUserAction(c *Client, action, userID, teamID string) {
	labels := map[string]string{"user_id": userID}
	if teamID != "" {
		labels["team_id"] = teamID
	}
	c.Metric("user.action."+action, 1, "counter", labels)
}

func TrackFeatureUsage(c *Client, featureName, teamID string) {
	c.Metric("feature.usage."+featureName, 1, "counter", map[string]string{"team_id": teamID})
}
