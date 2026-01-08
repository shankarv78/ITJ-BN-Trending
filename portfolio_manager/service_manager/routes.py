"""
Service Manager API Routes

REST API endpoints for service management.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from .config import SERVICE_MANAGER_API_KEY, SERVICES
from .service_controller import controller, ServiceStatus, RestartResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/services", tags=["Services"])

security = HTTPBearer(auto_error=False)


# ============================================================
# Request/Response Models
# ============================================================

class ServiceStatusResponse(BaseModel):
    """Response model for service status."""
    key: str
    name: str
    port: int
    status: str
    pid: Optional[int] = None
    uptime: Optional[str] = None
    health_details: Optional[dict] = None
    last_checked: Optional[str] = None
    description: str = ""


class AllServicesResponse(BaseModel):
    """Response model for all services status."""
    services: list[ServiceStatusResponse]
    timestamp: str


class ActionResponse(BaseModel):
    """Response model for service actions."""
    success: bool
    message: str
    service_key: str
    old_pid: Optional[int] = None
    new_pid: Optional[int] = None
    duration_seconds: float = 0.0


# ============================================================
# Authentication
# ============================================================

async def verify_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> bool:
    """
    Verify API key for protected endpoints.

    In dev mode (API key = "dev-key-change-in-production"), allows all requests.
    In production, requires valid API key.
    """
    # Dev mode bypass
    if SERVICE_MANAGER_API_KEY == "dev-key-change-in-production":
        logger.warning("[SECURITY] Running in dev mode - API key not enforced")
        return True

    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Use Authorization: Bearer <api_key>"
        )

    if credentials.credentials != SERVICE_MANAGER_API_KEY:
        logger.warning("[SECURITY] Invalid API key attempt")
        raise HTTPException(
            status_code=403,
            detail="Invalid API key"
        )

    return True


# ============================================================
# Status Endpoints (No auth required)
# ============================================================

@router.get("/status", response_model=AllServicesResponse)
async def get_all_services_status():
    """
    Get status of all managed services.

    Returns list of all services with their current status.
    No authentication required.
    """
    statuses = await controller.get_all_status()
    return AllServicesResponse(
        services=[
            ServiceStatusResponse(
                key=s.key,
                name=s.name,
                port=s.port,
                status=s.status,
                pid=s.pid,
                uptime=s.uptime,
                health_details=s.health_details,
                last_checked=s.last_checked,
                description=s.description
            )
            for s in statuses
        ],
        timestamp=datetime.now().isoformat()
    )


@router.get("/{service_key}/status", response_model=ServiceStatusResponse)
async def get_service_status(service_key: str):
    """
    Get status of a specific service.

    Args:
        service_key: Service identifier (frontend, pm, margin_monitor, openalgo)

    Returns:
        Service status details
    """
    if service_key not in SERVICES:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown service: {service_key}. Available: {list(SERVICES.keys())}"
        )

    status = await controller.get_status(service_key)
    return ServiceStatusResponse(
        key=status.key,
        name=status.name,
        port=status.port,
        status=status.status,
        pid=status.pid,
        uptime=status.uptime,
        health_details=status.health_details,
        last_checked=status.last_checked,
        description=status.description
    )


# ============================================================
# Action Endpoints (Auth required)
# ============================================================

@router.post("/{service_key}/restart", response_model=ActionResponse, dependencies=[Depends(verify_api_key)])
async def restart_service(service_key: str):
    """
    Restart a service.

    Performs graceful shutdown (SIGTERM), waits for exit, then starts service.
    Requires API key authentication.

    Args:
        service_key: Service identifier (frontend, pm, margin_monitor, openalgo)

    Returns:
        Action result with old/new PIDs
    """
    if service_key not in SERVICES:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown service: {service_key}. Available: {list(SERVICES.keys())}"
        )

    logger.info(f"[API] Restart requested for {service_key}")

    result = await controller.restart_service(service_key)

    if not result.success:
        # Still return 200 but with success=false
        # This allows the frontend to show the error message
        logger.warning(f"[API] Restart failed for {service_key}: {result.message}")

    return ActionResponse(
        success=result.success,
        message=result.message,
        service_key=result.service_key,
        old_pid=result.old_pid,
        new_pid=result.new_pid,
        duration_seconds=result.duration_seconds
    )


@router.post("/{service_key}/stop", response_model=ActionResponse, dependencies=[Depends(verify_api_key)])
async def stop_service(service_key: str):
    """
    Stop a service.

    Sends SIGTERM for graceful shutdown, falls back to SIGKILL if needed.
    Requires API key authentication.

    Args:
        service_key: Service identifier (frontend, pm, margin_monitor, openalgo)

    Returns:
        Action result
    """
    if service_key not in SERVICES:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown service: {service_key}. Available: {list(SERVICES.keys())}"
        )

    logger.info(f"[API] Stop requested for {service_key}")

    result = await controller.stop_service(service_key)

    return ActionResponse(
        success=result.success,
        message=result.message,
        service_key=result.service_key,
        old_pid=result.old_pid,
        duration_seconds=result.duration_seconds
    )


@router.post("/{service_key}/start", response_model=ActionResponse, dependencies=[Depends(verify_api_key)])
async def start_service(service_key: str):
    """
    Start a service.

    Starts the service and waits for health check to pass.
    Requires API key authentication.

    Args:
        service_key: Service identifier (frontend, pm, margin_monitor, openalgo)

    Returns:
        Action result with new PID
    """
    if service_key not in SERVICES:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown service: {service_key}. Available: {list(SERVICES.keys())}"
        )

    logger.info(f"[API] Start requested for {service_key}")

    result = await controller.start_service(service_key)

    return ActionResponse(
        success=result.success,
        message=result.message,
        service_key=result.service_key,
        new_pid=result.new_pid,
        duration_seconds=result.duration_seconds
    )
