// Package auth provides authentication middleware for the Go backend.
package auth

import (
	"fmt"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
)

// TokenClaims represents JWT token claims.
type TokenClaims struct {
	Sub           string   `json:"sub"`
	Role          string   `json:"role"`
	TeamIDs       []string `json:"team_ids,omitempty"`
	CurrentTeamID string   `json:"current_team_id,omitempty"`
	Type          string   `json:"type"`
	jwt.RegisteredClaims
}

// JWTMiddleware validates JWT tokens from Flask backend.
// Extracts user_id, role, team_ids from token and adds to Gin context.
func JWTMiddleware(jwtSecret string) gin.HandlerFunc {
	return func(c *gin.Context) {
		// Extract token from Authorization header
		authHeader := c.GetHeader("Authorization")
		if authHeader == "" {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Missing Authorization header"})
			c.Abort()
			return
		}

		// Check Bearer token format
		parts := strings.SplitN(authHeader, " ", 2)
		if len(parts) != 2 || parts[0] != "Bearer" {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid Authorization header format"})
			c.Abort()
			return
		}

		tokenString := parts[1]

		// Parse and validate token
		token, err := jwt.ParseWithClaims(tokenString, &TokenClaims{}, func(token *jwt.Token) (interface{}, error) {
			// Validate signing method
			if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
				return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
			}
			return []byte(jwtSecret), nil
		})

		if err != nil || !token.Valid {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid or expired token"})
			c.Abort()
			return
		}

		// Extract claims
		claims, ok := token.Claims.(*TokenClaims)
		if !ok {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid token claims"})
			c.Abort()
			return
		}

		// Skip refresh tokens (they're used only for refresh endpoint)
		if claims.Type == "refresh" {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Refresh tokens cannot access this endpoint"})
			c.Abort()
			return
		}

		// Add claims to context
		c.Set("user_id", claims.Sub)
		c.Set("role", claims.Role)
		c.Set("team_ids", claims.TeamIDs)
		c.Set("current_team_id", claims.CurrentTeamID)

		c.Next()
	}
}

// GetUserID extracts user_id from context.
func GetUserID(c *gin.Context) string {
	userID, exists := c.Get("user_id")
	if !exists {
		return ""
	}
	if id, ok := userID.(string); ok {
		return id
	}
	return ""
}

// GetRole extracts role from context.
func GetRole(c *gin.Context) string {
	role, exists := c.Get("role")
	if !exists {
		return ""
	}
	if r, ok := role.(string); ok {
		return r
	}
	return ""
}

// GetTeamIDs extracts team_ids from context.
func GetTeamIDs(c *gin.Context) []string {
	teamIDs, exists := c.Get("team_ids")
	if !exists {
		return []string{}
	}
	if ids, ok := teamIDs.([]string); ok {
		return ids
	}
	return []string{}
}

// GetCurrentTeamID extracts current_team_id from context.
func GetCurrentTeamID(c *gin.Context) string {
	teamID, exists := c.Get("current_team_id")
	if !exists {
		return ""
	}
	if id, ok := teamID.(string); ok {
		return id
	}
	return ""
}
