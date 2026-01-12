"""
Local Admin API for Gateway Service

Provides REST endpoints for:
- GET  /health       - Service health and metrics
- POST /rules        - Update rules engine config (hot reload)
- POST /config       - Update selected config values
- GET  /logs         - Retrieve recent logs

Security:
- Binds to localhost only (127.0.0.1)
- Optional Bearer token authentication for POST requests
"""

import logging
from typing import Optional, Dict, Any, List
from functools import wraps

from fastapi import FastAPI, HTTPException, Header, Query, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .runtime import RuntimeState
from .rules import Rules, RulesConfig

logger = logging.getLogger(__name__)


# -------------------- Request/Response Models --------------------

class HealthResponse(BaseModel):
    """Health check response."""
    up: bool
    uptime_s: float
    mqtt_connected: bool
    uart_connected: bool
    counters: Dict[str, int]


class LogEntry(BaseModel):
    """Single log entry."""
    ts: float
    level: str
    message: str


class LogsResponse(BaseModel):
    """Logs response."""
    logs: List[LogEntry]
    count: int


class RulesUpdateRequest(BaseModel):
    """Request to update rules configuration."""
    lock: Optional[bool] = Field(None, description="Enable/disable global lock")
    cooldown_user_s: Optional[int] = Field(None, ge=0, le=300, description="Per-user cooldown (0-300s)")
    cooldown_global_s: Optional[int] = Field(None, ge=0, le=60, description="Global cooldown (0-60s)")
    dedupe_ttl_s: Optional[int] = Field(None, ge=0, le=600, description="Dedupe TTL (0-600s)")


class RulesResponse(BaseModel):
    """Current rules configuration."""
    lock: bool
    cooldown_user_s: int
    cooldown_global_s: int
    dedupe_ttl_s: int


class ConfigUpdateRequest(BaseModel):
    """Request to update selected config values."""
    log_level: Optional[str] = Field(None, pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")


class ConfigResponse(BaseModel):
    """Current configuration snapshot."""
    site: str
    uart_port: str
    mqtt_host: str
    mqtt_port: int
    log_level: str
    api_auth_enabled: bool


class GenericResponse(BaseModel):
    """Generic success response."""
    ok: bool
    message: str


# -------------------- API Factory --------------------

def make_app(
    runtime: RuntimeState,
    rules: Rules,
    config: Any,  # gateway Config object
    api_token: Optional[str] = None
) -> FastAPI:
    """
    Create FastAPI application with injected dependencies.
    
    Args:
        runtime: RuntimeState for health/logs
        rules: Rules engine instance
        config: Gateway config (for /config endpoint)
        api_token: Optional API token (empty string = no auth)
    
    Returns:
        Configured FastAPI app
    """
    
    app = FastAPI(
        title="WFMS Gateway Admin API",
        description="Local administration API for the WFMS Gateway Service",
        version="1.0.0",
        docs_url="/docs",
        redoc_url=None,  # Disable ReDoc
    )
    
    # -------------------- Auth Dependency --------------------
    
    async def verify_token(authorization: Optional[str] = Header(None)):
        """Verify Bearer token for protected endpoints."""
        if not api_token:
            # No token configured = no auth required
            return True
        
        if not authorization:
            raise HTTPException(
                status_code=401,
                detail="Authorization header required",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Expect "Bearer <token>"
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(
                status_code=401,
                detail="Invalid authorization header format",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        if parts[1] != api_token:
            raise HTTPException(
                status_code=403,
                detail="Invalid token"
            )
        
        return True
    
    # -------------------- Endpoints --------------------
    
    @app.get("/health", response_model=HealthResponse, tags=["Health"])
    async def get_health():
        """
        Get service health and metrics.
        
        Returns current status including:
        - Whether MQTT is connected
        - Uptime in seconds
        - Message counters
        """
        return runtime.get_health()
    
    @app.get("/logs", response_model=LogsResponse, tags=["Logs"])
    async def get_logs(
        limit: int = Query(50, ge=1, le=200, description="Max logs to return"),
        level: Optional[str] = Query(None, pattern="^(DEBUG|INFO|WARNING|ERROR)$")
    ):
        """
        Get recent log entries.
        
        Logs are returned newest-first. Use `level` to filter.
        """
        logs = runtime.get_logs(limit=limit, level=level)
        return LogsResponse(logs=logs, count=len(logs))
    
    @app.get("/rules", response_model=RulesResponse, tags=["Rules"])
    async def get_rules():
        """Get current rules configuration."""
        cfg = rules.config
        return RulesResponse(
            lock=cfg.lock,
            cooldown_user_s=cfg.cooldown_user_s,
            cooldown_global_s=cfg.cooldown_global_s,
            dedupe_ttl_s=cfg.dedupe_ttl_s
        )
    
    @app.post("/rules", response_model=RulesResponse, tags=["Rules"])
    async def update_rules(
        req: RulesUpdateRequest,
        _: bool = Depends(verify_token)
    ):
        """
        Update rules configuration (hot reload).
        
        Only provided fields are updated. Requires Bearer token.
        """
        current = rules.config
        
        new_config = RulesConfig(
            lock=req.lock if req.lock is not None else current.lock,
            cooldown_user_s=req.cooldown_user_s if req.cooldown_user_s is not None else current.cooldown_user_s,
            cooldown_global_s=req.cooldown_global_s if req.cooldown_global_s is not None else current.cooldown_global_s,
            dedupe_ttl_s=req.dedupe_ttl_s if req.dedupe_ttl_s is not None else current.dedupe_ttl_s
        )
        
        rules.update_config(new_config)
        
        logger.info(f"Rules updated via Admin API: lock={new_config.lock}, "
                   f"cooldown_user={new_config.cooldown_user_s}s")
        runtime.add_log("INFO", f"Rules updated: lock={new_config.lock}")
        
        return RulesResponse(
            lock=new_config.lock,
            cooldown_user_s=new_config.cooldown_user_s,
            cooldown_global_s=new_config.cooldown_global_s,
            dedupe_ttl_s=new_config.dedupe_ttl_s
        )
    
    @app.get("/config", response_model=ConfigResponse, tags=["Config"])
    async def get_config():
        """Get current configuration snapshot (read-only)."""
        return ConfigResponse(
            site=config.site,
            uart_port=config.uart_port,
            mqtt_host=config.mqtt_host,
            mqtt_port=config.mqtt_port,
            log_level=config.log_level,
            api_auth_enabled=config.api_auth_enabled
        )
    
    @app.post("/config", response_model=GenericResponse, tags=["Config"])
    async def update_config(
        req: ConfigUpdateRequest,
        _: bool = Depends(verify_token)
    ):
        """
        Update selected configuration values.
        
        Currently supports: log_level. Requires Bearer token.
        """
        changes = []
        
        if req.log_level:
            # Update log level dynamically
            import logging as logging_module
            level = getattr(logging_module, req.log_level)
            logging_module.getLogger().setLevel(level)
            config.log_level = req.log_level
            changes.append(f"log_level={req.log_level}")
            logger.info(f"Log level changed to {req.log_level}")
        
        if not changes:
            return GenericResponse(ok=True, message="No changes applied")
        
        runtime.add_log("INFO", f"Config updated: {', '.join(changes)}")
        return GenericResponse(ok=True, message=f"Updated: {', '.join(changes)}")
    
    # -------------------- Lifespan Events --------------------
    
    @app.on_event("startup")
    async def on_startup():
        logger.info("Admin API starting...")
    
    @app.on_event("shutdown")
    async def on_shutdown():
        logger.info("Admin API shutting down...")
    
    return app


# -------------------- Uvicorn Runner --------------------

def run_api_server(
    app: FastAPI,
    host: str = "127.0.0.1",
    port: int = 8080,
    log_level: str = "warning"
) -> None:
    """
    Run the API server (blocking).
    
    Note: This is typically called in a daemon thread.
    """
    import uvicorn
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level,
        access_log=False  # Disable access logging (we have our own)
    )
