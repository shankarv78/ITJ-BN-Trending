"""
Service Controller - Manages service lifecycle operations.

Handles:
- Checking service status (via port and health endpoint)
- Stopping services (SIGTERM -> SIGKILL)
- Starting services (nohup subprocess)
- Restarting services (stop + start + health check)
"""

import os
import signal
import subprocess
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass
from pathlib import Path

import httpx

from .config import (
    SERVICES, ServiceConfig, PM_DIR,
    GRACEFUL_SHUTDOWN_TIMEOUT, HEALTH_CHECK_TIMEOUT, HEALTH_CHECK_INTERVAL,
    RESTART_COOLDOWN
)

logger = logging.getLogger(__name__)


@dataclass
class ServiceStatus:
    """Status of a service."""
    key: str
    name: str
    port: int
    status: str  # 'online', 'offline', 'starting', 'stopping', 'unknown'
    pid: Optional[int] = None
    uptime: Optional[str] = None
    health_details: Optional[dict] = None
    last_checked: Optional[str] = None
    description: str = ""


@dataclass
class RestartResult:
    """Result of a restart operation."""
    success: bool
    message: str
    service_key: str
    old_pid: Optional[int] = None
    new_pid: Optional[int] = None
    duration_seconds: float = 0.0


class ServiceController:
    """Controls service lifecycle operations."""

    def __init__(self):
        self._last_restart: dict[str, datetime] = {}
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=5.0)
        return self._http_client

    async def close(self):
        """Close HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    def _get_pid_file_path(self, config: ServiceConfig) -> Path:
        """Get full path to PID file."""
        return PM_DIR / config.pid_file

    def _read_pid(self, config: ServiceConfig) -> Optional[int]:
        """Read PID from file."""
        pid_file = self._get_pid_file_path(config)
        if not pid_file.exists():
            return None
        try:
            pid = int(pid_file.read_text().strip())
            # Check if process actually exists
            os.kill(pid, 0)
            return pid
        except (ValueError, OSError, ProcessLookupError):
            return None

    def _write_pid(self, config: ServiceConfig, pid: int):
        """Write PID to file."""
        pid_file = self._get_pid_file_path(config)
        pid_file.write_text(str(pid))

    def _remove_pid(self, config: ServiceConfig):
        """Remove PID file."""
        pid_file = self._get_pid_file_path(config)
        if pid_file.exists():
            pid_file.unlink()

    def _is_port_in_use(self, port: int) -> bool:
        """Check if a port is in use."""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', port)) == 0

    def _get_pid_by_port(self, port: int) -> Optional[int]:
        """Get PID of process using a port."""
        try:
            result = subprocess.run(
                ['lsof', '-ti', f':{port}'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                # May return multiple PIDs, take first
                return int(result.stdout.strip().split('\n')[0])
        except (subprocess.TimeoutExpired, ValueError):
            pass
        return None

    async def _check_health(self, config: ServiceConfig) -> tuple[bool, Optional[dict]]:
        """Check if service is healthy via HTTP endpoint."""
        if not config.health_url:
            # No health URL, just check port
            return self._is_port_in_use(config.port), None

        try:
            client = await self._get_client()
            response = await client.get(config.health_url)
            if response.status_code == 200:
                try:
                    return True, response.json()
                except Exception:
                    return True, {"status": "ok"}
            return False, {"status_code": response.status_code}
        except Exception as e:
            return False, {"error": str(e)}

    async def get_status(self, service_key: str) -> ServiceStatus:
        """Get status of a single service."""
        if service_key not in SERVICES:
            return ServiceStatus(
                key=service_key,
                name="Unknown",
                port=0,
                status="unknown",
                description="Service not found"
            )

        config = SERVICES[service_key]
        pid = self._read_pid(config)

        # Check if port is in use
        port_in_use = self._is_port_in_use(config.port)

        # If PID file doesn't match running process, try to find by port
        if not pid and port_in_use:
            pid = self._get_pid_by_port(config.port)

        # Determine status
        if port_in_use:
            is_healthy, health_details = await self._check_health(config)
            status = "online" if is_healthy else "degraded"
        else:
            status = "offline"
            health_details = None

        return ServiceStatus(
            key=service_key,
            name=config.name,
            port=config.port,
            status=status,
            pid=pid,
            health_details=health_details,
            last_checked=datetime.now().isoformat(),
            description=config.description
        )

    async def get_all_status(self) -> list[ServiceStatus]:
        """Get status of all services."""
        statuses = []
        for key in SERVICES:
            status = await self.get_status(key)
            statuses.append(status)
        return statuses

    async def stop_service(self, service_key: str, force: bool = False) -> RestartResult:
        """Stop a service."""
        if service_key not in SERVICES:
            return RestartResult(
                success=False,
                message=f"Unknown service: {service_key}",
                service_key=service_key
            )

        config = SERVICES[service_key]
        start_time = datetime.now()

        # Get current PID
        pid = self._read_pid(config)
        if not pid:
            pid = self._get_pid_by_port(config.port)

        if not pid:
            return RestartResult(
                success=True,
                message=f"{config.name} is not running",
                service_key=service_key
            )

        old_pid = pid
        logger.info(f"[SERVICE_MANAGER] Stopping {config.name} (PID: {pid})")

        try:
            # Send SIGTERM first (graceful shutdown)
            os.kill(pid, signal.SIGTERM)

            # Wait for process to exit
            for _ in range(GRACEFUL_SHUTDOWN_TIMEOUT):
                await asyncio.sleep(1)
                try:
                    os.kill(pid, 0)  # Check if still running
                except OSError:
                    # Process exited
                    self._remove_pid(config)
                    duration = (datetime.now() - start_time).total_seconds()
                    return RestartResult(
                        success=True,
                        message=f"{config.name} stopped gracefully",
                        service_key=service_key,
                        old_pid=old_pid,
                        duration_seconds=duration
                    )

            # Still running, force kill if requested or default
            if force or True:  # Always force after timeout
                logger.warning(f"[SERVICE_MANAGER] Force killing {config.name}")
                os.kill(pid, signal.SIGKILL)
                await asyncio.sleep(0.5)

            self._remove_pid(config)
            duration = (datetime.now() - start_time).total_seconds()
            return RestartResult(
                success=True,
                message=f"{config.name} force stopped",
                service_key=service_key,
                old_pid=old_pid,
                duration_seconds=duration
            )

        except ProcessLookupError:
            self._remove_pid(config)
            return RestartResult(
                success=True,
                message=f"{config.name} was not running",
                service_key=service_key
            )
        except Exception as e:
            return RestartResult(
                success=False,
                message=f"Failed to stop {config.name}: {str(e)}",
                service_key=service_key,
                old_pid=old_pid
            )

    async def start_service(self, service_key: str) -> RestartResult:
        """Start a service."""
        if service_key not in SERVICES:
            return RestartResult(
                success=False,
                message=f"Unknown service: {service_key}",
                service_key=service_key
            )

        config = SERVICES[service_key]
        start_time = datetime.now()

        # Check if already running
        if self._is_port_in_use(config.port):
            existing_pid = self._get_pid_by_port(config.port)
            return RestartResult(
                success=False,
                message=f"{config.name} is already running on port {config.port}",
                service_key=service_key,
                old_pid=existing_pid
            )

        logger.info(f"[SERVICE_MANAGER] Starting {config.name}")

        # Prepare environment
        env = os.environ.copy()
        if config.env_vars:
            env.update(config.env_vars)

        # Prepare log file
        log_dir = PM_DIR / "logs"
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / f"{service_key}.log"

        try:
            # Start process with nohup
            with open(log_file, 'a') as log:
                process = subprocess.Popen(
                    config.start_cmd,
                    shell=True,
                    cwd=str(config.working_dir),
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True  # Detach from parent
                )

            new_pid = process.pid
            self._write_pid(config, new_pid)
            logger.info(f"[SERVICE_MANAGER] Started {config.name} with PID {new_pid}")

            # Wait for health check
            for i in range(HEALTH_CHECK_TIMEOUT):
                await asyncio.sleep(HEALTH_CHECK_INTERVAL)

                # First check if process is still alive
                try:
                    os.kill(new_pid, 0)
                except OSError:
                    # Process died
                    self._remove_pid(config)
                    return RestartResult(
                        success=False,
                        message=f"{config.name} exited immediately after start. Check logs at {log_file}",
                        service_key=service_key,
                        new_pid=new_pid
                    )

                # Then check health
                is_healthy, _ = await self._check_health(config)
                if is_healthy:
                    duration = (datetime.now() - start_time).total_seconds()
                    return RestartResult(
                        success=True,
                        message=f"{config.name} started successfully",
                        service_key=service_key,
                        new_pid=new_pid,
                        duration_seconds=duration
                    )

            # Timeout waiting for health
            duration = (datetime.now() - start_time).total_seconds()
            return RestartResult(
                success=False,
                message=f"{config.name} started but health check timed out after {HEALTH_CHECK_TIMEOUT}s",
                service_key=service_key,
                new_pid=new_pid,
                duration_seconds=duration
            )

        except Exception as e:
            logger.exception(f"[SERVICE_MANAGER] Failed to start {config.name}")
            return RestartResult(
                success=False,
                message=f"Failed to start {config.name}: {str(e)}",
                service_key=service_key
            )

    async def restart_service(self, service_key: str) -> RestartResult:
        """Restart a service (stop + start)."""
        if service_key not in SERVICES:
            return RestartResult(
                success=False,
                message=f"Unknown service: {service_key}",
                service_key=service_key
            )

        # Check cooldown
        last_restart = self._last_restart.get(service_key)
        if last_restart:
            elapsed = (datetime.now() - last_restart).total_seconds()
            if elapsed < RESTART_COOLDOWN:
                remaining = int(RESTART_COOLDOWN - elapsed)
                return RestartResult(
                    success=False,
                    message=f"Cooldown active. Please wait {remaining}s before restarting {SERVICES[service_key].name}",
                    service_key=service_key
                )

        config = SERVICES[service_key]
        start_time = datetime.now()
        old_pid = self._read_pid(config) or self._get_pid_by_port(config.port)

        logger.info(f"[SERVICE_MANAGER] Restarting {config.name}")

        # Stop service
        stop_result = await self.stop_service(service_key)
        if not stop_result.success and "not running" not in stop_result.message.lower():
            return stop_result

        # Brief pause before starting
        await asyncio.sleep(1)

        # Start service
        start_result = await self.start_service(service_key)

        # Update cooldown
        self._last_restart[service_key] = datetime.now()

        duration = (datetime.now() - start_time).total_seconds()
        return RestartResult(
            success=start_result.success,
            message=start_result.message,
            service_key=service_key,
            old_pid=old_pid,
            new_pid=start_result.new_pid,
            duration_seconds=duration
        )


# Global controller instance
controller = ServiceController()
