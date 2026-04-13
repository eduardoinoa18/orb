"""
Integration Management API
Handles user requests for new API/product integrations, agent implementation tracking,
and execution with full audit trail logging.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import Optional, List, Any
import json
import logging

from db import get_db_pool

router = APIRouter(prefix="/integration", tags=["integration-management"])
logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Models
# ============================================================================

class IntegrationRequestPayload(BaseModel):
    product_name: str
    api_documentation_url: Optional[str] = None
    use_case: str
    priority: str = "medium"  # low, medium, high, critical
    requested_by: str


class IntegrationRequestApprovalPayload(BaseModel):
    integration_request_id: str
    assigned_agent_id: str
    approval_notes: Optional[str] = None


class AgentImplementationPayload(BaseModel):
    integration_request_id: str
    agent_id: str
    agent_name: str
    action_type: str  # add_endpoint, add_integration, modify_config, etc
    resource_type: str  # api_route, config_file, database_schema, etc
    resource_path: str
    change_summary: str
    change_diff: Optional[dict] = None


class ImplementationAuditApprovalPayload(BaseModel):
    audit_id: str
    approved_by: str
    approval_notes: Optional[str] = None
    execute: bool = False  # Auto-execute the change after approval


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
    permission_scope: str  # database_schema, deployment_config, user_permissions, product_features
    resource_path: Optional[str] = None
    access_level: str  # read, write, admin
    expires_at: Optional[datetime] = None


# ============================================================================
# 1. Integration Request Management
# ============================================================================

@router.post("/request")
async def create_integration_request(
    payload: IntegrationRequestPayload,
    owner_id: str = "default_owner"
) -> dict[str, Any]:
    """
    User requests a new integration for a specific product or API.
    Creates a request record in pending status for admin agents to review.
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """
            INSERT INTO public.integration_requests (
                owner_id, product_name, api_documentation_url, use_case, priority,
                requested_by, status, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, 'pending', now(), now())
            RETURNING id, product_name, status, created_at
            """,
            owner_id, payload.product_name, payload.api_documentation_url,
            payload.use_case, payload.priority, payload.requested_by
        )
        
        if not result:
            raise HTTPException(status_code=500, detail="Failed to create integration request")
        
        logger.info(f"Integration request created: {result['id']} for {payload.product_name}")
        return dict(result)


@router.get("/requests")
async def list_integration_requests(
    status: Optional[str] = None,
    owner_id: str = "default_owner",
    limit: int = 50
) -> list[dict[str, Any]]:
    """
    List integration requests with optional filtering by status.
    Admin agents use this to find pending requests to work on.
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        if status:
            results = await conn.fetch(
                """
                SELECT id, product_name, use_case, status, priority,
                       assigned_agent_id, created_at, approved_at
                FROM public.integration_requests
                WHERE owner_id = $1 AND status = $2
                ORDER BY created_at DESC
                LIMIT $3
                """,
                owner_id, status, limit
            )
        else:
            results = await conn.fetch(
                """
                SELECT id, product_name, use_case, status, priority,
                       assigned_agent_id, created_at, approved_at
                FROM public.integration_requests
                WHERE owner_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                owner_id, limit
            )
        
        return [dict(r) for r in results]


@router.post("/request/{request_id}/approve")
async def approve_integration_request(
    request_id: str,
    payload: IntegrationRequestApprovalPayload
) -> dict[str, Any]:
    """
    Admin or superuser approves an integration request and assigns it to an agent.
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """
            UPDATE public.integration_requests
            SET status = 'approved', assigned_agent_id = $1,
                approved_at = now(), updated_at = now()
            WHERE id = $2
            RETURNING id, product_name, assigned_agent_id, status
            """,
            payload.assigned_agent_id, request_id
        )
        
        if not result:
            raise HTTPException(status_code=404, detail="Integration request not found")
        
        logger.info(f"Integration request {request_id} approved and assigned to {payload.assigned_agent_id}")
        return dict(result)


@router.get("/request/{request_id}")
async def get_integration_request(request_id: str) -> dict[str, Any]:
    """Get detailed information about a specific integration request."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """
            SELECT * FROM public.integration_requests
            WHERE id = $1
            """,
            request_id
        )
        
        if not result:
            raise HTTPException(status_code=404, detail="Integration request not found")
        
        return dict(result)


# ============================================================================
# 2. Agent Implementation Tracking & Audit Logging
# ============================================================================

@router.post("/implementation/log")
async def log_agent_implementation(
    payload: AgentImplementationPayload
) -> dict[str, Any]:
    """
    Agent logs an implementation action (e.g., added new API endpoint).
    Creates audit trail entry with full change tracking.
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """
            INSERT INTO public.agent_implementation_audit (
                integration_request_id, agent_id, agent_name,
                action_type, resource_type, resource_path, change_summary,
                change_diff, status, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'pending_approval', now())
            RETURNING id, agent_name, action_type, status, created_at
            """,
            payload.integration_request_id, payload.agent_id, payload.agent_name,
            payload.action_type, payload.resource_type, payload.resource_path,
            payload.change_summary, json.dumps(payload.change_diff or {})
        )
        
        if not result:
            raise HTTPException(status_code=500, detail="Failed to log implementation")
        
        logger.info(f"Implementation logged: {payload.agent_name} - {payload.action_type} on {payload.resource_path}")
        return dict(result)


@router.get("/audit/logs")
async def get_audit_logs(
    integration_request_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100
) -> list[dict[str, Any]]:
    """
    Retrieve audit logs with optional filtering.
    Used by admins to review agent changes and approve implementations.
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        query = "SELECT * FROM public.agent_implementation_audit WHERE 1=1"
        params = []
        
        if integration_request_id:
            query += " AND integration_request_id = $" + str(len(params) + 1)
            params.append(integration_request_id)
        
        if agent_id:
            query += " AND agent_id = $" + str(len(params) + 1)
            params.append(agent_id)
        
        if status:
            query += " AND status = $" + str(len(params) + 1)
            params.append(status)
        
        query += " ORDER BY created_at DESC LIMIT $" + str(len(params) + 1)
        params.append(limit)
        
        results = await conn.fetch(query, *params)
        return [dict(r) for r in results]


@router.post("/audit/{audit_id}/approve")
async def approve_agent_implementation(
    audit_id: str,
    payload: ImplementationAuditApprovalPayload
) -> dict[str, Any]:
    """
    Admin approves an agent's implementation change.
    Optionally executes the change immediately.
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """
            UPDATE public.agent_implementation_audit
            SET status = 'approved', approved_by = $1,
                approval_notes = $2, approved_at = now()
            WHERE id = $3
            RETURNING id, agent_name, resource_path, status
            """,
            payload.approved_by, payload.approval_notes, audit_id
        )
        
        if not result:
            raise HTTPException(status_code=404, detail="Audit record not found")
        
        if payload.execute:
            # Mark as executed (in production, this would trigger actual deployment)
            await conn.execute(
                """
                UPDATE public.agent_implementation_audit
                SET status = 'executed', executed_at = now()
                WHERE id = $1
                """,
                audit_id
            )
            logger.info(f"Implementation executed: {result['agent_name']} - {result['resource_path']}")
        
        return dict(result)


@router.post("/audit/{audit_id}/reject")
async def reject_agent_implementation(
    audit_id: str,
    rejection_reason: str
) -> dict[str, Any]:
    """Admin rejects an agent's implementation change."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """
            UPDATE public.agent_implementation_audit
            SET status = 'rejected', approval_notes = $1, approved_at = now()
            WHERE id = $2
            RETURNING id, agent_name, status
            """,
            rejection_reason, audit_id
        )
        
        if not result:
            raise HTTPException(status_code=404, detail="Audit record not found")
        
        logger.warning(f"Implementation rejected: {result['agent_name']} - {rejection_reason}")
        return dict(result)


# ============================================================================
# 3. Integration Version Control
# ============================================================================

@router.post("/version")
async def create_integration_version(
    payload: IntegrationVersionPayload
) -> dict[str, Any]:
    """
    Create a version record for a completed integration.
    Stores test results, API endpoints, dependencies, and deployment status.
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """
            INSERT INTO public.integration_versions (
                integration_request_id, version_number, implemented_by_agent_id,
                implementation_date, module_path, test_results, test_coverage_percent,
                api_endpoints_added, dependencies_added, breaking_changes,
                deployment_status, created_at
            )
            VALUES ($1, $2, $3, now(), $4, $5, $6, $7, $8, $9, $10, now())
            RETURNING id, version_number, module_path, test_coverage_percent
            """,
            payload.integration_request_id,
            payload.version_number,
            "agent_system",  # set by executor
            payload.module_path,
            json.dumps(payload.test_results),
            payload.test_coverage_percent,
            payload.api_endpoints_added,
            payload.dependencies_added,
            payload.breaking_changes,
            payload.deployment_status
        )
        
        if not result:
            raise HTTPException(status_code=500, detail="Failed to create integration version")
        
        logger.info(f"Integration version created: {payload.module_path} v{payload.version_number}")
        return dict(result)


@router.get("/versions/{integration_request_id}")
async def get_integration_versions(
    integration_request_id: str
) -> list[dict[str, Any]]:
    """Get all versions of an integration."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        results = await conn.fetch(
            """
            SELECT id, version_number, module_path, test_coverage_percent,
                   deployment_status, implementation_date
            FROM public.integration_versions
            WHERE integration_request_id = $1
            ORDER BY version_number DESC
            """,
            integration_request_id
        )
        
        return [dict(r) for r in results]


# ============================================================================
# 4. Agent Permissions & Access Control
# ============================================================================

@router.post("/permission")
async def grant_agent_permission(
    payload: AgentPermissionPayload
) -> dict[str, Any]:
    """
    Grant an admin agent permission to access/modify specific resources.
    Controls what agents can change in the platform core.
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """
            INSERT INTO public.agent_permissions (
                agent_id, agent_name, permission_scope, resource_path,
                access_level, expires_at, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, now(), now())
            ON CONFLICT (agent_id, permission_scope, resource_path)
            DO UPDATE SET
                access_level = $5, expires_at = $6, updated_at = now()
            RETURNING id, agent_name, permission_scope, access_level
            """,
            payload.agent_id, payload.agent_name, payload.permission_scope,
            payload.resource_path, payload.access_level, payload.expires_at
        )
        
        if not result:
            raise HTTPException(status_code=500, detail="Failed to grant permission")
        
        logger.info(f"Permission granted: {payload.agent_name} - {payload.permission_scope}")
        return dict(result)


@router.get("/permissions/{agent_id}")
async def get_agent_permissions(agent_id: str) -> list[dict[str, Any]]:
    """Get all permissions assigned to an agent."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        results = await conn.fetch(
            """
            SELECT id, permission_scope, resource_path, access_level, expires_at
            FROM public.agent_permissions
            WHERE agent_id = $1 AND (expires_at IS NULL OR expires_at > now())
            ORDER BY permission_scope
            """,
            agent_id
        )
        
        return [dict(r) for r in results]


@router.post("/permissions/{permission_id}/revoke")
async def revoke_agent_permission(permission_id: str) -> dict[str, str]:
    """Revoke a previously granted permission."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """
            DELETE FROM public.agent_permissions
            WHERE id = $1
            RETURNING id
            """,
            permission_id
        )
        
        if not result:
            raise HTTPException(status_code=404, detail="Permission not found")
        
        logger.info(f"Permission revoked: {permission_id}")
        return {"status": "revoked", "permission_id": permission_id}


# ============================================================================
# 5. MCP Server Session Tracking
# ============================================================================

@router.post("/mcp/session/start")
async def start_mcp_session(
    agent_id: str,
    agent_name: str,
    mcp_server_url: str
) -> dict[str, Any]:
    """
    Start a new MCP server session for an agent communicating with Copilot.
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """
            INSERT INTO public.mcp_agent_sessions (
                agent_id, agent_name, session_start_at, mcp_server_url,
                status, created_at
            )
            VALUES ($1, $2, now(), $3, 'active', now())
            RETURNING id, agent_name, status, session_start_at
            """,
            agent_id, agent_name, mcp_server_url
        )
        
        if not result:
            raise HTTPException(status_code=500, detail="Failed to start MCP session")
        
        logger.info(f"MCP session started: {agent_name}")
        return dict(result)


@router.post("/mcp/session/{session_id}/heartbeat")
async def mcp_session_heartbeat(
    session_id: str,
    queries_issued: Optional[int] = None,
    responses_received: Optional[int] = None,
    errors_encountered: Optional[int] = None
) -> dict[str, str]:
    """
    Send heartbeat to keep MCP session active and update stats.
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE public.mcp_agent_sessions
            SET last_heartbeat_at = now(),
                queries_issued = COALESCE(queries_issued, 0) + COALESCE($2, 0),
                responses_received = COALESCE(responses_received, 0) + COALESCE($3, 0),
                errors_encountered = COALESCE(errors_encountered, 0) + COALESCE($4, 0)
            WHERE id = $1
            """,
            session_id, queries_issued or 0, responses_received or 0, errors_encountered or 0
        )
        
        return {"status": "heartbeat_received", "session_id": session_id}


@router.post("/mcp/session/{session_id}/end")
async def end_mcp_session(session_id: str) -> dict[str, Any]:
    """End an MCP session."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """
            UPDATE public.mcp_agent_sessions
            SET session_end_at = now(), status = 'closed'
            WHERE id = $1
            RETURNING id, agent_name, queries_issued, responses_received
            """,
            session_id
        )
        
        if not result:
            raise HTTPException(status_code=404, detail="Session not found")
        
        logger.info(f"MCP session ended: {result['agent_name']}")
        return dict(result)


@router.get("/mcp/sessions/{agent_id}")
async def get_agent_mcp_sessions(agent_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Get recent MCP sessions for an agent."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        results = await conn.fetch(
            """
            SELECT id, agent_name, session_start_at, session_end_at, status,
                   queries_issued, responses_received, errors_encountered
            FROM public.mcp_agent_sessions
            WHERE agent_id = $1
            ORDER BY session_start_at DESC
            LIMIT $2
            """,
            agent_id, limit
        )
        
        return [dict(r) for r in results]
