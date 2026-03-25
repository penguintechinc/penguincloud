"""Example gRPC client for Flask backend services.

This example demonstrates how to communicate with gRPC services
exposed by the Flask backend on port 50051.
"""

import grpc
import os
import sys
from datetime import datetime

# Add proto package to path
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../services/flask-backend/app/grpc")
)

try:
    from protos import template_pb2, template_pb2_grpc
except ImportError:
    print("Error: Proto files not compiled")
    print("Run: python -m grpc_tools.protoc -I./services/flask-backend/app/grpc/protos")
    print("       --python_out=./services/flask-backend/app/grpc")
    print("       --grpc_python_out=./services/flask-backend/app/grpc")
    print("       ./services/flask-backend/app/grpc/protos/template.proto")
    sys.exit(1)


class GRPCClient:
    """Client for gRPC services."""

    def __init__(self, host="localhost", port=50051):
        self.channel = grpc.insecure_channel(f"{host}:{port}")
        self.auth_stub = template_pb2_grpc.AuthServiceStub(self.channel)
        self.team_stub = template_pb2_grpc.TeamServiceStub(self.channel)
        self.health_stub = template_pb2_grpc.HealthStub(self.channel)

    def validate_token(self, token):
        """Validate JWT token."""
        print(f"Validating token: {token[:20]}...")
        request = template_pb2.TokenRequest(token=token)
        response = self.auth_stub.ValidateToken(request)

        if response.valid:
            print("✓ Token valid")
            print(f"  User: {response.user_id}")
            print(f"  Role: {response.role}")
            print(f"  Teams: {', '.join(response.team_ids) or 'none'}")
        else:
            print(f"✗ Token invalid: {response.error}")

        return response

    def get_user(self, user_id):
        """Get user by ID."""
        print(f"Getting user: {user_id}")
        request = template_pb2.UserRequest(user_id=user_id)
        response = self.auth_stub.GetUser(request)

        if response.error:
            print(f"✗ Error: {response.error}")
        else:
            print("✓ User found")
            print(f"  ID: {response.id}")
            print(f"  Email: {response.email}")
            print(f"  Name: {response.full_name}")
            print(f"  Role: {response.role}")

        return response

    def get_team(self, team_id):
        """Get team by ID."""
        print(f"Getting team: {team_id}")
        request = template_pb2.TeamRequest(team_id=team_id)
        response = self.team_stub.GetTeam(request)

        if response.error:
            print(f"✗ Error: {response.error}")
        else:
            print("✓ Team found")
            print(f"  ID: {response.id}")
            print(f"  Name: {response.name}")
            print(f"  Slug: {response.slug}")
            print(f"  Owner: {response.owner_id}")

        return response

    def list_user_teams(self, user_id):
        """List teams for user."""
        print(f"Listing teams for user: {user_id}")
        request = template_pb2.UserRequest(user_id=user_id)
        response = self.team_stub.ListUserTeams(request)

        if response.error:
            print(f"✗ Error: {response.error}")
        else:
            print(f"✓ Found {response.total} teams")
            for team in response.teams:
                print(f"  - {team.name} ({team.slug})")

        return response

    def health_check(self):
        """Check server health."""
        print("Checking health...")
        from google.protobuf.empty_pb2 import Empty

        request = Empty()
        response = self.health_stub.Check(request)

        if response.status == template_pb2.HealthCheckResponse.SERVING:
            print("✓ Server is serving")
        else:
            print("✗ Server is not serving")

        return response

    def close(self):
        """Close connection."""
        self.channel.close()


def main():
    """Example usage."""
    print("=== gRPC Client Example ===\n")

    # Create client
    client = GRPCClient(host="localhost", port=50051)

    try:
        # Health check
        client.health_check()
        print()

        # Validate token (replace with actual token)
        client.validate_token("example_jwt_token_here")
        print()

        # Get user
        client.get_user("user_123")
        print()

        # Get team
        client.get_team("team_456")
        print()

        # List user teams
        client.list_user_teams("user_123")
        print()

    except grpc.RpcError as e:
        print(f"gRPC error: {e.code()} - {e.details()}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
