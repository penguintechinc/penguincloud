// Package db provides database access for the Go backend.
package db

import (
	"fmt"
	"time"

	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

// Client provides database operations.
type Client struct {
	db *gorm.DB
}

// Config holds database configuration.
type Config struct {
	Host     string
	Port     int
	User     string
	Password string
	DBName   string
	SSLMode  string
}

// User represents a user record (read-only copy of Flask schema).
type User struct {
	ID        int    `gorm:"primaryKey"`
	Email     string `gorm:"uniqueIndex"`
	FullName  string
	Role      string
	IsActive  bool
	CreatedAt time.Time
	UpdatedAt time.Time
}

// Team represents a team record (read-only copy of Flask schema).
type Team struct {
	ID        int `gorm:"primaryKey"`
	Name      string
	Slug      string `gorm:"uniqueIndex"`
	OwnerID   int
	IsActive  bool
	CreatedAt time.Time
	UpdatedAt time.Time
}

// TeamMember represents a team membership record.
type TeamMember struct {
	ID        int `gorm:"primaryKey"`
	TeamID    int
	UserID    int
	Role      string
	CreatedAt time.Time
	UpdatedAt time.Time
}

// NewClient creates a new database client.
func NewClient(cfg *Config) (*Client, error) {
	dsn := fmt.Sprintf(
		"host=%s port=%d user=%s password=%s dbname=%s sslmode=%s",
		cfg.Host, cfg.Port, cfg.User, cfg.Password, cfg.DBName, cfg.SSLMode,
	)

	db, err := gorm.Open(postgres.Open(dsn), &gorm.Config{})
	if err != nil {
		return nil, fmt.Errorf("failed to connect to database: %w", err)
	}

	return &Client{db: db}, nil
}

// GetUserByID retrieves a user by ID.
func (c *Client) GetUserByID(userID string) (*User, error) {
	var user User
	if err := c.db.Where("id = ?", userID).First(&user).Error; err != nil {
		if err == gorm.ErrRecordNotFound {
			return nil, nil
		}
		return nil, fmt.Errorf("failed to get user: %w", err)
	}
	return &user, nil
}

// GetTeamByID retrieves a team by ID.
func (c *Client) GetTeamByID(teamID string) (*Team, error) {
	var team Team
	if err := c.db.Where("id = ?", teamID).First(&team).Error; err != nil {
		if err == gorm.ErrRecordNotFound {
			return nil, nil
		}
		return nil, fmt.Errorf("failed to get team: %w", err)
	}
	return &team, nil
}

// GetTeamMembers retrieves all members of a team.
func (c *Client) GetTeamMembers(teamID string) ([]TeamMember, error) {
	var members []TeamMember
	if err := c.db.Where("team_id = ?", teamID).Find(&members).Error; err != nil {
		return nil, fmt.Errorf("failed to get team members: %w", err)
	}
	return members, nil
}

// GetUserTeams retrieves all teams a user belongs to.
func (c *Client) GetUserTeams(userID string) ([]Team, error) {
	var teams []Team
	if err := c.db.
		Joins("JOIN team_members ON teams.id = team_members.team_id").
		Where("team_members.user_id = ?", userID).
		Find(&teams).Error; err != nil {
		return nil, fmt.Errorf("failed to get user teams: %w", err)
	}
	return teams, nil
}

// IsTeamMember checks if a user is a member of a team.
func (c *Client) IsTeamMember(teamID, userID string) (bool, error) {
	var count int64
	if err := c.db.
		Model(&TeamMember{}).
		Where("team_id = ? AND user_id = ?", teamID, userID).
		Count(&count).Error; err != nil {
		return false, fmt.Errorf("failed to check team membership: %w", err)
	}
	return count > 0, nil
}

// GetTeamMemberRole gets a user's role in a team.
func (c *Client) GetTeamMemberRole(teamID, userID string) (string, error) {
	var member TeamMember
	if err := c.db.
		Where("team_id = ? AND user_id = ?", teamID, userID).
		First(&member).Error; err != nil {
		if err == gorm.ErrRecordNotFound {
			return "", nil
		}
		return "", fmt.Errorf("failed to get team member role: %w", err)
	}
	return member.Role, nil
}

// Close closes the database connection.
func (c *Client) Close() error {
	db, err := c.db.DB()
	if err != nil {
		return err
	}
	return db.Close()
}
