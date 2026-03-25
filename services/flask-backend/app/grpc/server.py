"""gRPC server implementation for Flask backend."""

import logging
import os
import threading
from concurrent import futures

import grpc
import jwt

# Import generated proto classes (will be available after proto compilation)
try:
    from . import protos

    HAS_PROTO = True
except ImportError:
    HAS_PROTO = False
    logging.warning("Proto files not compiled. Run: python -m grpc_tools.protoc")

logger = logging.getLogger(__name__)


class AuthServicer:
    """Implementation of AuthService."""

    def __init__(self, app):
        self.app = app

    def ValidateToken(self, request, context):
        """Validate JWT token and return token info."""
        if not HAS_PROTO:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details("Proto not initialized")
            return {}

        try:
            token = request.token
            secret = os.getenv("JWT_SECRET_KEY", "dev-secret")

            payload = jwt.decode(token, secret, algorithms=["HS256"])

            return protos.template_pb2.TokenResponse(
                valid=True,
                user_id=payload.get("sub"),
                role=payload.get("role"),
                team_ids=payload.get("team_ids", []),
                current_team_id=payload.get("current_team_id", ""),
            )
        except jwt.InvalidTokenError as e:
            return protos.template_pb2.TokenResponse(valid=False, error=str(e))

    def GetUser(self, request, context):
        """Get user by ID."""
        if not HAS_PROTO:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return {}

        try:
            with self.app.app_context():
                # Import here to avoid circular imports
                from app import db

                user = db.User.query.get(request.user_id)

                if not user:
                    context.set_code(grpc.StatusCode.NOT_FOUND)
                    context.set_details(f"User {request.user_id} not found")
                    return protos.template_pb2.UserResponse(error="User not found")

                return protos.template_pb2.UserResponse(
                    id=user.id,
                    email=user.email,
                    full_name=user.full_name or "",
                    role=user.role or "viewer",
                    created_at=user.created_at,
                )
        except Exception as e:
            logger.error(f"GetUser error: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            return protos.template_pb2.UserResponse(error=str(e))


class TeamServicer:
    """Implementation of TeamService."""

    def __init__(self, app):
        self.app = app

    def GetTeam(self, request, context):
        """Get team by ID."""
        if not HAS_PROTO:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return {}

        try:
            with self.app.app_context():
                from app import db

                team = db.Team.query.get(request.team_id)

                if not team:
                    context.set_code(grpc.StatusCode.NOT_FOUND)
                    context.set_details(f"Team {request.team_id} not found")
                    return protos.template_pb2.TeamResponse(error="Team not found")

                return protos.template_pb2.TeamResponse(
                    id=team.id,
                    name=team.name,
                    slug=team.slug,
                    description=team.description or "",
                    owner_id=team.owner_id,
                    is_active=team.is_active,
                    created_at=team.created_at,
                    updated_at=team.updated_at,
                )
        except Exception as e:
            logger.error(f"GetTeam error: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            return protos.template_pb2.TeamResponse(error=str(e))

    def ListUserTeams(self, request, context):
        """List teams for a user."""
        if not HAS_PROTO:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            return {}

        try:
            with self.app.app_context():
                from app import db

                # Get team memberships for user
                memberships = db.TeamMember.query.filter_by(
                    user_id=request.user_id
                ).all()

                teams = []
                for membership in memberships:
                    team = db.Team.query.get(membership.team_id)
                    if team:
                        teams.append(
                            protos.template_pb2.TeamResponse(
                                id=team.id,
                                name=team.name,
                                slug=team.slug,
                                description=team.description or "",
                                owner_id=team.owner_id,
                                is_active=team.is_active,
                                created_at=team.created_at,
                                updated_at=team.updated_at,
                            )
                        )

                return protos.template_pb2.TeamListResponse(
                    teams=teams, total=len(teams)
                )
        except Exception as e:
            logger.error(f"ListUserTeams error: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            return protos.template_pb2.TeamListResponse(error=str(e))


class HealthServicer:
    """Implementation of Health service."""

    def Check(self, request, context):
        """Health check."""
        return protos.template_pb2.HealthCheckResponse(
            status=protos.template_pb2.HealthCheckResponse.SERVING
        )

    def Watch(self, request, context):
        """Health check stream."""
        yield protos.template_pb2.HealthCheckResponse(
            status=protos.template_pb2.HealthCheckResponse.SERVING
        )


class GRPCServer:
    """gRPC server wrapper."""

    def __init__(self, app, port=50051):
        self.app = app
        self.port = port
        self.server = None
        self.thread = None

    def start(self):
        """Start gRPC server in background thread."""
        if not HAS_PROTO:
            logger.warning("Skipping gRPC server - proto not compiled")
            return

        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

        if HAS_PROTO:
            protos.template_pb2_grpc.add_AuthServiceServicer_to_server(
                AuthServicer(self.app), self.server
            )
            protos.template_pb2_grpc.add_TeamServiceServicer_to_server(
                TeamServicer(self.app), self.server
            )
            protos.template_pb2_grpc.add_HealthServicer_to_server(
                HealthServicer(), self.server
            )

        self.server.add_insecure_port(f"[::]:{self.port}")

        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()
        logger.info(f"gRPC server started on port {self.port}")

    def _run_server(self):
        """Run server (blocking)."""
        try:
            self.server.start()
            self.server.wait_for_termination()
        except Exception as e:
            logger.error(f"gRPC server error: {e}")

    def stop(self):
        """Stop gRPC server."""
        if self.server:
            self.server.stop(grace=5)
            if self.thread:
                self.thread.join(timeout=10)
            logger.info("gRPC server stopped")


def create_grpc_server(app):
    """Factory function to create and start gRPC server."""
    if not os.getenv("GRPC_ENABLED", "false").lower() == "true":
        logger.info("gRPC disabled (GRPC_ENABLED=false)")
        return None

    port = int(os.getenv("GRPC_PORT", "50051"))
    server = GRPCServer(app, port)
    server.start()
    return server
