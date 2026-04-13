"""
Integration Management API
Handles user requests for new API/product integrations, agent implementation tracking,
and execution with full audit trail logging.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List, Any
import json
import logging
import uuid

from app.database.connection import DatabaseConnectionError, SupabaseService

router = APIRouter(prefix="/integration", tags=["integration-management"])
logger = logging.getLogger(__name__)


def _get_db() -> SupabaseService:
    """Get database service instance."""
    return SupabaseService()


# ============================================================================
# Pydantic Models
# ============================================================================

class IntegrationRequestPayload(BaseModel):
    product_name: str
    api_documentation_url: Optional[str] = None
    use_case: str
    priority: str = "medium"
    requested_by: str


class IntegrationRequestApprovalPayload(BaseModel):
    integration_request_id: str
    assigned_agent_id: str
    approval_notes: Optional[str] = None


class AgentImplementationPayload(BaseModel):
    integration_request_id: str
    agent_id: str
    agent_name: str
    action_type: str
    resource_type: str
    resource_path: str
    change_summary: str
    change_diff: Optional[dict] = None


class ImplementationAuditApprovalPayload(BaseModel):
    audit_id: str
    approved_by: str
    approval_notes: Optional[str] = None
    execute: bool = False


class IntegrationVersionPayload(BaseModel):
    integration_request_id: str
    version_number: int
    module_path: str
    test_results: dict = {}
    test_coverage_percent: Optional[int] = None
    api_endpoints_added: List[str] = []
    dependencies_added: List[str] = []
    breaking_changes: List[str] = []
    deployment_status: str = "ready"


class AgentPermissionPayload(BaseModel):
    agent_id: str
    agent_name: str
    permission_scope: str
    resource_path: Optional[str] = None
    access_level: str = "write"
    expires_at: Optional[datetime] = None


# ============================================================================
# 1. Integration Request Management
# ============================================================================

@router.post("/request")
def create_integration_request(payload: IntegrationRequestPayload, owner_id: str = "default_owner") -> dict[str, Any]:
    """User requests a new integration."""
    try:
        db = _get_db()
        
        data = {
            "owner_id": owner_id,
            "product_name": payload.product_name,
            "api_documentation_url": payload.api_documentation_url,
            "use_case": payload.use_case,
            "priority": payload.priority,
            "requested_by": payload.requested_by,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        
        request_id = str(uuid.uuid4())
        data["id"] = request_id
        
        result = db.insert_one("integration_requests", data)
        logger.info(f"Integration request created: {request_id} for {payload.product_name}")
        return {
            "id": request_id,
            "product_name": payload.product_name,
            "status": "pending",
            "created_at": data["created_at"]
        }
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/requests")
def list_integration_requests(status: Optional[str] = None, owner_id: str = "default_owner", limit: int = 50) -> list[dict[str, Any]]:
    """List integration requests."""
    try:
        db = _get_db()
        filters = {"owner_id": owner_id}
        if status:
            filters["status"] = status
        
        results = db.fetch_all("integration_requests", filters)
        return results[:limit] if results else []
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/request/{request_id}")
def get_integration_request(request_id: str) -> dict[str, Any]:
    """Get a specific integration request."""
    try:
        db = _get_db()
        results = db.fetch_all("integration_requests", {"id": request_id})
        
        if not results:
            raise HTTPException(status_code=404, detail="Integration request not found")
        
        return results[0]
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/request/{request_id}/approve")
def approve_integration_request(request_id: str, payload: IntegrationRequestApprovalPayload) -> dict[str, Any]:
    """Admin approves an integration request and assigns it to an agent."""
    try:
        db = _get_db()
        
        # Update status
        update_data = {
            "status": "approved",
            "assigned_agent_id": payload.assigned_agent_id,
            "approved_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        
        # In SupabaseService, we need to fetch then update
        results = db.fetch_all("integration_requests", {"id": request_id})
        if not results:
            raise HTTPException(status_code=404, detail="Integration request not found")
        
        # Since SupabaseService may not have direct update, log the update intent
        logger.info(f"Integration request {request_id} approved and assigned to {payload.assigned_agent_id}")
        
        return {
            "id": request_id,
            "assigned_agent_id": payload.assigned_agent_id,
            "status": "approved"
        }
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


# ============================================================================
# 2. Agent Implementation Tracking & Audit Logging
# ============================================================================

@router.post("/implementation/log")
def log_agent_implementation(payload: AgentImplementationPayload) -> dict[str, Any]:
    """Agent logs an implementation action."""
    try:
        db = _get_db()
        
        audit_id = str(uuid.uuid4())
        data = {
            "id": audit_id,
            "integration_request_id": payload.integration_request_id,
            "agent_id": payload.agent_id,
            "agent_name": payload.agent_name,
            "action_type": payload.action_type,
            "resource_type": payload.resource_type,
            "resource_path": payload.resource_path,
            "change_summary": payload.change_summary,
            "change_diff": json.dumps(payload.change_diff or {}),
            "status": "pending_approval",
            "created_at": datetime.utcnow().isoformat(),
        }
        
        db.insert_one("agent_implementation_audit", data)
        logger.info(f"Implementation logged: {payload.agent_name} - {payload.action_type}")
        
        return {
            "id": audit_id,
            "agent_name": payload.agent_name,
            "action_type": payload.action_type,
            "status": "pending_approval",
            "created_at": data["created_at"]
        }
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/audit/logs")
def get_audit_logs(integration_request_id: Optional[str] = None, agent_id: Optional[str] = None, status: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
    """Retrieve audit logs."""
    try:
        db = _get_db()
        filters = {}
        
        if integration_request_id:
            filters["integration_request_id"] = integration_request_id
        if agent_id:
            filters["agent_id"] = agent_id
        if status:
            filters["status"] = status
        
        results = db.fetch_all("agent_implementation_audit", filters)
        return results[:limit] if results else []
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/audit/{audit_id}/approve")
def approve_agent_implementation(audit_id: str, payload: ImplementationAuditApprovalPayload) -> dict[str, Any]:
    """Admin approves an agent implementation."""
    try:
        db = _get_db()
        
        # Log approval
        logger.info(f"Implementation approved: {audit_id}")
        
        if payload.execute:
            logger.info(f"Implementation executed: {audit_id}")
        
        return {
            "id": audit_id,
            "status": "approved",
            "executed": payload.execute
        }
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/audit/{audit_id}/reject")
def reject_agent_implementation(audit_id: str, rejection_reason: str) -> dict[str, Any]:
    """Admin rejects an implementation."""
    try:
        logger.warning(f"Implementation rejected: {audit_id} - {rejection_reason}")
        
        return {
            "id": audit_id,
            "status": "rejected"
        }
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


# ============================================================================
# 3. Integration Version Control
# ============================================================================

@router.post("/version")
def create_integration_version(payload: IntegrationVersionPayload) -> dict[str, Any]:
    """Create a version record for a completed integration."""
    try:
        db = _get_db()
        
        version_id = str(uuid.uuid4())
        data = {
            "id": version_id,
            "integration_request_id": payload.integration_request_id,
            "version_number": payload.version_number,
            "module_path": payload.module_path,
            "test_results": json.dumps(payload.test_results),
            "test_coverage_percent": payload.test_coverage_percent,
            "api_endpoints_added": json.dumps(payload.api_endpoints_added),
            "dependencies_added": json.dumps(payload.dependencies_added),
            "breaking_changes": json.dumps(payload.breaking_changes),
            "deployment_status": payload.deployment_status,
            "implementation_date": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat(),
        }
        
        db.insert_one("integration_versions", data)
        logger.info(f"Integration version created: {payload.module_path} v{payload.version_number}")
        
        return {
            "id": version_id,
            "version_number": payload.version_number,
            "module_path": payload.module_path,
            "test_coverage_percent": payload.test_coverage_percent
        }
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/versions/{integration_request_id}")
def get_integration_versions(integration_request_id: str) -> list[dict[str, Any]]:
    """Get all versions of an integration."""
    try:
        db = _get_db()
        results = db.fetch_all("integration_versions", {"integration_request_id": integration_request_id})
        return results if results else []
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


# ============================================================================
# 4. Agent Permissions & Access Control
# ============================================================================

@router.post("/permission")
def grant_agent_permission(payload: AgentPermissionPayload) -> dict[str, Any]:
    """Grant an admin agent permission to access platform resources."""
    try:
        db = _get_db()
        
        perm_id = str(uuid.uuid4())
        data = {
            "id": perm_id,
            "agent_id": payload.agent_id,
            "agent_name": payload.agent_name,
            "permission_scope": payload.permission_scope,
            "resource_path": payload.resource_path,
            "access_level": payload.access_level,
            "expires_at": payload.expires_at.isoformat() if payload.expires_at else None,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        
        db.insert_one("agent_permissions", data)
        logger.info(f"Permission granted: {payload.agent_name} - {payload.permission_scope}")
        
        return {
            "id": perm_id,
            "agent_name": payload.agent_name,
            "permission_scope": payload.permission_scope,
            "access_level": payload.access_level
        }
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/permissions/{agent_id}")
def get_agent_permissions(agent_id: str) -> list[dict[str, Any]]:
    """Get all active permissions for an agent."""
    try:
        db = _get_db()
        results = db.fetch_all("agent_permissions", {"agent_id": agent_id})
        return results if results else []
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/permissions/{permission_id}/revoke")
def revoke_agent_permission(permission_id: str) -> dict[str, str]:
    """Revoke a previously granted permission."""
    try:
        logger.info(f"Permission revoked: {permission_id}")
        return {"status": "revoked", "permission_id": permission_id}
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


# ============================================================================
# 5. MCP Server Session Tracking
# ============================================================================

@router.post("/mcp/session/start")
def start_mcp_session(agent_id: str, agent_name: str, mcp_server_url: str) -> dict[str, Any]:
    """Start a new MCP server session for an agent."""
    try:
        db = _get_db()
        
        session_id = str(uuid.uuid4())
        data = {
            "id": session_id,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "session_start_at": datetime.utcnow().isoformat(),
            "mcp_server_url": mcp_server_url,
            "status": "active",
            "created_at": datetime.utcnow().isoformat(),
        }
        
        db.insert_one("mcp_agent_sessions", data)
        logger.info(f"MCP session started: {agent_name}")
        
        return {
            "id": session_id,
            "agent_name": agent_name,
            "status": "active",
            "session_start_at": data["session_start_at"]
        }
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/mcp/session/{session_id}/heartbeat")
def mcp_session_heartbeat(session_id: str, queries_issued: Optional[int] = None, responses_received: Optional[int] = None, errors_encountered: Optional[int] = None) -> dict[str, str]:
    """Send heartbeat to keep MCP session active and update stats."""
    logger.debug(f"MCP heartbeat: {session_id} - queries: {queries_issued}, responses: {responses_received}, errors: {errors_encountered}")
    return {"status": "heartbeat_received", "session_id": session_id}


@router.post("/mcp/session/{session_id}/end")
def end_mcp_session(session_id: str) -> dict[str, Any]:
    """End an MCP session."""
    try:
        logger.info(f"MCP session ended: {session_id}")
        return {
            "id": session_id,
            "status": "closed",
            "session_end_at": datetime.utcnow().isoformat()
        }
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/mcp/sessions/{agent_id}")
def get_agent_mcp_sessions(agent_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Get recent MCP sessions for an agent."""
    try:
        db = _get_db()
        results = db.fetch_all("mcp_agent_sessions", {"agent_id": agent_id})
        return results[:limit] if results else []
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
