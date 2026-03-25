package main

import (
	"context"
	"fmt"
	"log"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/protobuf/types/known/emptypb"

	pb "github.com/penguintechinc/project-template/services/go-backend/internal/grpc/protos"
)

// GRPCClient wraps gRPC service clients
type GRPCClient struct {
	conn      *grpc.ClientConn
	authCli   pb.AuthServiceClient
	teamCli   pb.TeamServiceClient
	healthCli pb.HealthClient
}

// NewGRPCClient creates a new gRPC client
func NewGRPCClient(host string, port int) (*GRPCClient, error) {
	addr := fmt.Sprintf("%s:%d", host, port)
	conn, err := grpc.NewClient(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return nil, fmt.Errorf("failed to connect to %s: %w", addr, err)
	}

	return &GRPCClient{
		conn:      conn,
		authCli:   pb.NewAuthServiceClient(conn),
		teamCli:   pb.NewTeamServiceClient(conn),
		healthCli: pb.NewHealthClient(conn),
	}, nil
}

// ValidateToken validates JWT token
func (c *GRPCClient) ValidateToken(token string) (*pb.TokenResponse, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	fmt.Printf("Validating token: %s...\n", token[:20])
	resp, err := c.authCli.ValidateToken(ctx, &pb.TokenRequest{
		Token: token,
	})
	if err != nil {
		return nil, err
	}

	if resp.Valid {
		fmt.Println("✓ Token valid")
		fmt.Printf("  User: %s\n", resp.UserId)
		fmt.Printf("  Role: %s\n", resp.Role)
		fmt.Printf("  Teams: %v\n", resp.TeamIds)
	} else {
		fmt.Printf("✗ Token invalid: %s\n", resp.Error)
	}

	return resp, nil
}

// GetUser gets user by ID
func (c *GRPCClient) GetUser(userID string) (*pb.UserResponse, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	fmt.Printf("Getting user: %s\n", userID)
	resp, err := c.authCli.GetUser(ctx, &pb.UserRequest{
		UserId: userID,
	})
	if err != nil {
		return nil, err
	}

	if resp.Error == "" {
		fmt.Println("✓ User found")
		fmt.Printf("  ID: %s\n", resp.Id)
		fmt.Printf("  Email: %s\n", resp.Email)
		fmt.Printf("  Name: %s\n", resp.FullName)
		fmt.Printf("  Role: %s\n", resp.Role)
	} else {
		fmt.Printf("✗ Error: %s\n", resp.Error)
	}

	return resp, nil
}

// GetTeam gets team by ID
func (c *GRPCClient) GetTeam(teamID string) (*pb.TeamResponse, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	fmt.Printf("Getting team: %s\n", teamID)
	resp, err := c.teamCli.GetTeam(ctx, &pb.TeamRequest{
		TeamId: teamID,
	})
	if err != nil {
		return nil, err
	}

	if resp.Error == "" {
		fmt.Println("✓ Team found")
		fmt.Printf("  ID: %s\n", resp.Id)
		fmt.Printf("  Name: %s\n", resp.Name)
		fmt.Printf("  Slug: %s\n", resp.Slug)
		fmt.Printf("  Owner: %s\n", resp.Owner)
	} else {
		fmt.Printf("✗ Error: %s\n", resp.Error)
	}

	return resp, nil
}

// ListUserTeams lists teams for user
func (c *GRPCClient) ListUserTeams(userID string) (*pb.TeamListResponse, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	fmt.Printf("Listing teams for user: %s\n", userID)
	resp, err := c.teamCli.ListUserTeams(ctx, &pb.UserRequest{
		UserId: userID,
	})
	if err != nil {
		return nil, err
	}

	if resp.Error == "" {
		fmt.Printf("✓ Found %d teams\n", resp.Total)
		for _, team := range resp.Teams {
			fmt.Printf("  - %s (%s)\n", team.Name, team.Slug)
		}
	} else {
		fmt.Printf("✗ Error: %s\n", resp.Error)
	}

	return resp, nil
}

// HealthCheck checks server health
func (c *GRPCClient) HealthCheck() (*pb.HealthCheckResponse, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	fmt.Println("Checking health...")
	resp, err := c.healthCli.Check(ctx, &emptypb.Empty{})
	if err != nil {
		return nil, err
	}

	if resp.Status == pb.HealthCheckResponse_SERVING {
		fmt.Println("✓ Server is serving")
	} else {
		fmt.Println("✗ Server is not serving")
	}

	return resp, nil
}

// Close closes the connection
func (c *GRPCClient) Close() error {
	return c.conn.Close()
}

func main() {
	fmt.Println("=== gRPC Client Example ===\n")

	client, err := NewGRPCClient("localhost", 50052)
	if err != nil {
		log.Fatalf("Failed to create client: %v", err)
	}
	defer client.Close()

	// Health check
	_, err = client.HealthCheck()
	if err != nil {
		log.Printf("Health check error: %v", err)
	}
	fmt.Println()

	// Validate token
	_, err = client.ValidateToken("example_jwt_token_here")
	if err != nil {
		log.Printf("Validate token error: %v", err)
	}
	fmt.Println()

	// Get user
	_, err = client.GetUser("user_123")
	if err != nil {
		log.Printf("Get user error: %v", err)
	}
	fmt.Println()

	// Get team
	_, err = client.GetTeam("team_456")
	if err != nil {
		log.Printf("Get team error: %v", err)
	}
	fmt.Println()

	// List user teams
	_, err = client.ListUserTeams("user_123")
	if err != nil {
		log.Printf("List teams error: %v", err)
	}
}
