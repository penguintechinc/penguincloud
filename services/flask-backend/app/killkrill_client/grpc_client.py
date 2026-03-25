"""
gRPC client implementation for Killkrill receiver communication.
"""

from typing import Any, List

import grpc
import structlog

from .exceptions import ConnectionError, SubmissionError

logger = structlog.get_logger(__name__)


class GRPCSubmitter:
    """Handles gRPC submissions to Killkrill receivers."""

    def __init__(self, grpc_url: str, jwt_token: str) -> None:
        """
        Initialize gRPC submitter.

        Args:
            grpc_url: gRPC endpoint URL (host:port)
            jwt_token: JWT authentication token
        """
        self.grpc_url = grpc_url
        self.jwt_token = jwt_token
        self.channel: grpc.Channel | None = None
        self.stub: Any | None = None
        self._connected = False

    def connect(self) -> bool:
        """
        Establish gRPC connection.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Create secure channel with TLS
            credentials = grpc.ssl_channel_credentials()
            self.channel = grpc.secure_channel(self.grpc_url, credentials)

            # TODO: Import generated gRPC stub when proto files are compiled
            # from killkrill.grpc.protos import receiver_pb2_grpc
            # self.stub = receiver_pb2_grpc.ReceiverServiceStub(self.channel)

            # Test connection with health check
            if self.health_check():
                self._connected = True
                logger.info("grpc_connection_established", url=self.grpc_url)
                return True

            return False

        except grpc.RpcError as e:
            logger.warning("grpc_connection_failed", url=self.grpc_url, error=str(e))
            return False

    def disconnect(self) -> None:
        """Close gRPC connection."""
        if self.channel:
            self.channel.close()
            self._connected = False
            logger.info("grpc_connection_closed", url=self.grpc_url)

    def health_check(self) -> bool:
        """
        Check gRPC connection health.

        Returns:
            True if healthy, False otherwise
        """
        try:
            if not self.channel:
                return False

            # Use gRPC health check protocol
            grpc.channel_ready_future(self.channel).result(timeout=5)
            return True

        except grpc.FutureTimeoutError:
            logger.warning("grpc_health_check_timeout", url=self.grpc_url)
            return False
        except Exception as e:
            logger.warning("grpc_health_check_failed", url=self.grpc_url, error=str(e))
            return False

    def submit_logs(self, logs: List[dict]) -> bool:
        """
        Submit logs via gRPC.

        Args:
            logs: List of log entries

        Returns:
            True if submission successful

        Raises:
            SubmissionError: If submission fails
            ConnectionError: If not connected
        """
        if not self._connected:
            raise ConnectionError("gRPC client not connected")

        try:
            # TODO: Implement actual gRPC log submission when proto is compiled
            # request = receiver_pb2.LogSubmissionRequest(logs=logs)
            # metadata = [("authorization", f"Bearer {self.jwt_token}")]
            # response = self.stub.SubmitLogs(request, metadata=metadata)

            logger.info("grpc_logs_submitted", count=len(logs))
            return True

        except grpc.RpcError as e:
            logger.error("grpc_log_submission_failed", error=str(e), code=e.code())
            raise SubmissionError(f"gRPC log submission failed: {e.details()}")

    def submit_metrics(self, metrics: List[dict]) -> bool:
        """
        Submit metrics via gRPC.

        Args:
            metrics: List of metric entries

        Returns:
            True if submission successful

        Raises:
            SubmissionError: If submission fails
            ConnectionError: If not connected
        """
        if not self._connected:
            raise ConnectionError("gRPC client not connected")

        try:
            # TODO: Implement actual gRPC metrics submission when proto is compiled
            # request = receiver_pb2.MetricSubmissionRequest(metrics=metrics)
            # metadata = [("authorization", f"Bearer {self.jwt_token}")]
            # response = self.stub.SubmitMetrics(request, metadata=metadata)

            logger.info("grpc_metrics_submitted", count=len(metrics))
            return True

        except grpc.RpcError as e:
            logger.error("grpc_metric_submission_failed", error=str(e), code=e.code())
            raise SubmissionError(f"gRPC metric submission failed: {e.details()}")

    def __enter__(self) -> "GRPCSubmitter":
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.disconnect()
