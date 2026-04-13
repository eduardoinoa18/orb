"""Per-User Dashboard Customization Engine.

Every owner gets their own dashboard layout — tabs, widgets, theme, and
feature toggles. Commander and agents can modify the layout via conversation.

Database table: `dashboard_configs` with columns:
  - owner_id (uuid, primary key)
  - config (jsonb) → stores full DashboardConfig
  - updated_at (timestamptz)

When no config exists, a sensible default is returned based on the owner's plan.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.database.connection import DatabaseConnectionError, SupabaseService

logger = logging.getLogger("orb.dashboard_config")

router = APIRouter(prefix="/dashboard-config", tags=["Dashboard Customization"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class WidgetConfig(BaseModel):
    """A single dashboard widget."""
    id: str = Field(..., description="Unique widget identifier")
    type: str = Field(..., description="Widget type: stat, chart, list, calendar, chat, crm, agents, activity, custom")
    title: str = Field(default="", description="Display title")
    size: str = Field(default="md", description="sm | md | lg | full")
    position: int = Field(default=0, description="Sort order within the tab")
    visible: bool = Field(default=True)
    config: dict[str, Any] = Field(default_factory=dict, description="Widget-specific settings")


class TabConfig(BaseModel):
    """A dashboard tab containing widgets."""
    id: str = Field(..., description="Unique tab identifier")
    label: str = Field(..., description="Tab display label")
    icon: str = Field(default="layout", description="Lucide icon name")
    position: int = Field(default=0, description="Sort order")
    visible: bool = Field(default=True)
    widgets: list[WidgetConfig] = Field(default_factory=list)


class ThemeConfig(BaseModel):
    """Owner's visual theme preferences."""
    accent_color: str = Field(default="#8B5CF6", description="Primary accent (hex)")
    sidebar_style: str = Field(default="dark", description="dark | light | glass")
    card_style: str = Field(default="bordered", description="bordered | filled | glass")
    density: str = Field(default="comfortable", description="compact | comfortable | spacious")
    font_preference: str = Field(default="system", description="system | inter | mono")


class DashboardConfig(BaseModel):
    """Complete per-owner dashboard configuration."""
    tabs: list[TabConfig] = Field(default_factory=list)
    theme: ThemeConfig = Field(default_factory=ThemeConfig)
    active_tab: str = Field(default="overview", description="Default active tab ID")
    commander_position: str = Field(default="sidebar", description="sidebar | tab | floating | hidden")
    show_agent_avatars: bool = Field(default=True)
    quick_actions: list[str] = Field(default_factory=list, description="Pinned quick action IDs")


class UpdateRequest(BaseModel):
    """Partial update to dashboard config."""
    tabs: list[TabConfig] | None = None
    theme: ThemeConfig | None = None
    active_tab: str | None = None
    commander_position: str | None = None
    show_agent_avatars: bool | None = None
    quick_actions: list[str] | None = None


class AddTabRequest(BaseModel):
    """Request to add a single tab."""
    label: str
    icon: str = "layout"
    widgets: list[WidgetConfig] = Field(default_factory=list)


class AddWidgetRequest(BaseModel):
    """Request to add a widget to a tab."""
    tab_id: str
    widget: WidgetConfig


class RemoveTabRequest(BaseModel):
    """Request to remove a tab."""
    tab_id: str


class ReorderTabsRequest(BaseModel):
    """Request to reorder tabs."""
    tab_ids: list[str] = Field(..., description="Tab IDs in desired order")


# ---------------------------------------------------------------------------
# Default configs per plan tier
# ---------------------------------------------------------------------------

def _default_config(plan: str = "starter") -> DashboardConfig:
    """Generate a sensible default config based on the user's plan."""

    # Core tab — everyone gets this
    overview_widgets = [
        WidgetConfig(id="w-active-agents", type="stat", title="Active Agents", size="sm", position=0),
        WidgetConfig(id="w-pending-approvals", type="stat", title="Pending Approvals", size="sm", position=1),
        WidgetConfig(id="w-daily-cost", type="stat", title="Daily AI Cost", size="sm", position=2),
        WidgetConfig(id="w-activity", type="activity", title="Recent Activity", size="lg", position=3),
    ]
    overview_tab = TabConfig(id="overview", label="Overview", icon="layout-dashboard", position=0, widgets=overview_widgets)

    # Commander tab
    commander_tab = TabConfig(
        id="commander", label="Commander", icon="message-circle", position=1,
        widgets=[WidgetConfig(id="w-chat", type="chat", title="Commander Chat", size="full", position=0)],
    )

    # Agents tab
    agents_tab = TabConfig(
        id="agents", label="Agents", icon="bot", position=2,
        widgets=[WidgetConfig(id="w-agent-grid", type="agents", title="Your Agents", size="full", position=0)],
    )

    tabs = [overview_tab, commander_tab, agents_tab]

    # Professional and above get extra tabs
    if plan in ("professional", "enterprise", "master_owner"):
        tabs.append(TabConfig(
            id="crm", label="CRM", icon="users", position=3,
            widgets=[
                WidgetConfig(id="w-crm-leads", type="crm", title="Recent Leads", size="lg", position=0,
                             config={"source": "followupboss", "view": "leads"}),
                WidgetConfig(id="w-crm-tasks", type="list", title="Pending Tasks", size="md", position=1,
                             config={"source": "followupboss", "view": "tasks"}),
            ],
        ))
        tabs.append(TabConfig(
            id="calendar", label="Calendar", icon="calendar", position=4,
            widgets=[
                WidgetConfig(id="w-cal-upcoming", type="calendar", title="Upcoming Events", size="full", position=0),
            ],
        ))

    if plan in ("enterprise", "master_owner"):
        tabs.append(TabConfig(
            id="analytics", label="Analytics", icon="bar-chart-3", position=5,
            widgets=[
                WidgetConfig(id="w-cost-chart", type="chart", title="AI Cost Trend", size="lg", position=0),
                WidgetConfig(id="w-agent-perf", type="chart", title="Agent Performance", size="md", position=1),
            ],
        ))

    return DashboardConfig(
        tabs=tabs,
        theme=ThemeConfig(),
        active_tab="overview",
        commander_position="sidebar",
        show_agent_avatars=True,
        quick_actions=["send_message", "check_leads", "view_calendar"],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_owner_id(request: Request) -> str:
    payload = getattr(request.state, "token_payload", {})
    owner_id = payload.get("sub") or payload.get("owner_id")
    if not owner_id:
        raise HTTPException(status_code=401, detail="Missing owner_id")
    return owner_id


def _get_db() -> SupabaseService:
    return SupabaseService()


def _load_config(owner_id: str) -> DashboardConfig:
    """Load config from DB or return defaults."""
    try:
        db = _get_db()
        rows = db.fetch_all("dashboard_configs", {"owner_id": owner_id})
        if rows and rows[0].get("config"):
            raw = rows[0]["config"]
            if isinstance(raw, str):
                raw = json.loads(raw)
            return DashboardConfig(**raw)
    except (DatabaseConnectionError, Exception) as e:
        logger.warning("Could not load dashboard config for %s: %s", owner_id, e)

    # Get owner plan for default config
    plan = "starter"
    try:
        db = _get_db()
        owner_rows = db.fetch_all("owners", {"id": owner_id})
        if owner_rows:
            plan = owner_rows[0].get("plan", "starter")
    except Exception:
        pass

    return _default_config(plan)


def _save_config(owner_id: str, config: DashboardConfig) -> None:
    """Persist config to DB (upsert)."""
    try:
        db = _get_db()
        config_json = config.model_dump()
        # Try update first
        rows = db.fetch_all("dashboard_configs", {"owner_id": owner_id})
        if rows:
            db.update_many("dashboard_configs", {"owner_id": owner_id}, {"config": json.dumps(config_json)})
        else:
            db.insert_one("dashboard_configs", {"owner_id": owner_id, "config": json.dumps(config_json)})
    except DatabaseConnectionError as e:
        logger.error("Failed to save dashboard config: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable") from e


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
def get_dashboard_config(request: Request) -> dict[str, Any]:
    """Get the current owner's full dashboard config."""
    owner_id = _get_owner_id(request)
    config = _load_config(owner_id)
    return config.model_dump()


@router.put("")
def update_dashboard_config(payload: UpdateRequest, request: Request) -> dict[str, Any]:
    """Update the dashboard config (full or partial merge)."""
    owner_id = _get_owner_id(request)
    config = _load_config(owner_id)

    if payload.tabs is not None:
        config.tabs = payload.tabs
    if payload.theme is not None:
        config.theme = payload.theme
    if payload.active_tab is not None:
        config.active_tab = payload.active_tab
    if payload.commander_position is not None:
        config.commander_position = payload.commander_position
    if payload.show_agent_avatars is not None:
        config.show_agent_avatars = payload.show_agent_avatars
    if payload.quick_actions is not None:
        config.quick_actions = payload.quick_actions

    _save_config(owner_id, config)
    return config.model_dump()


@router.post("/tabs")
def add_tab(payload: AddTabRequest, request: Request) -> dict[str, Any]:
    """Add a new tab to the dashboard."""
    owner_id = _get_owner_id(request)
    config = _load_config(owner_id)

    # Generate unique tab ID
    tab_id = payload.label.lower().replace(" ", "_").replace("-", "_")
    existing_ids = {t.id for t in config.tabs}
    if tab_id in existing_ids:
        tab_id = f"{tab_id}_{len(config.tabs)}"

    new_tab = TabConfig(
        id=tab_id,
        label=payload.label,
        icon=payload.icon,
        position=len(config.tabs),
        widgets=payload.widgets,
    )
    config.tabs.append(new_tab)
    _save_config(owner_id, config)

    return {"tab_id": tab_id, "config": config.model_dump()}


@router.delete("/tabs/{tab_id}")
def remove_tab(tab_id: str, request: Request) -> dict[str, Any]:
    """Remove a tab from the dashboard."""
    owner_id = _get_owner_id(request)
    config = _load_config(owner_id)

    # Don't allow removing core tabs
    protected = {"overview", "commander"}
    if tab_id in protected:
        raise HTTPException(status_code=400, detail=f"Cannot remove the '{tab_id}' tab.")

    config.tabs = [t for t in config.tabs if t.id != tab_id]
    # Re-index positions
    for i, tab in enumerate(config.tabs):
        tab.position = i

    _save_config(owner_id, config)
    return {"removed": tab_id, "config": config.model_dump()}


@router.post("/tabs/{tab_id}/widgets")
def add_widget(tab_id: str, payload: AddWidgetRequest, request: Request) -> dict[str, Any]:
    """Add a widget to a specific tab."""
    owner_id = _get_owner_id(request)
    config = _load_config(owner_id)

    tab = next((t for t in config.tabs if t.id == tab_id), None)
    if not tab:
        raise HTTPException(status_code=404, detail=f"Tab '{tab_id}' not found.")

    payload.widget.position = len(tab.widgets)
    tab.widgets.append(payload.widget)
    _save_config(owner_id, config)

    return {"tab_id": tab_id, "widget_id": payload.widget.id, "config": config.model_dump()}


@router.delete("/tabs/{tab_id}/widgets/{widget_id}")
def remove_widget(tab_id: str, widget_id: str, request: Request) -> dict[str, Any]:
    """Remove a widget from a tab."""
    owner_id = _get_owner_id(request)
    config = _load_config(owner_id)

    tab = next((t for t in config.tabs if t.id == tab_id), None)
    if not tab:
        raise HTTPException(status_code=404, detail=f"Tab '{tab_id}' not found.")

    tab.widgets = [w for w in tab.widgets if w.id != widget_id]
    for i, w in enumerate(tab.widgets):
        w.position = i

    _save_config(owner_id, config)
    return {"removed": widget_id, "config": config.model_dump()}


@router.put("/tabs/reorder")
def reorder_tabs(payload: ReorderTabsRequest, request: Request) -> dict[str, Any]:
    """Reorder tabs by passing a list of tab IDs in desired order."""
    owner_id = _get_owner_id(request)
    config = _load_config(owner_id)

    tab_map = {t.id: t for t in config.tabs}
    reordered = []
    for i, tid in enumerate(payload.tab_ids):
        if tid in tab_map:
            tab_map[tid].position = i
            reordered.append(tab_map[tid])
    # Add any tabs not in the reorder list at the end
    remaining = [t for t in config.tabs if t.id not in set(payload.tab_ids)]
    for t in remaining:
        t.position = len(reordered)
        reordered.append(t)

    config.tabs = reordered
    _save_config(owner_id, config)
    return config.model_dump()


@router.put("/theme")
def update_theme(payload: ThemeConfig, request: Request) -> dict[str, Any]:
    """Update just the theme settings."""
    owner_id = _get_owner_id(request)
    config = _load_config(owner_id)
    config.theme = payload
    _save_config(owner_id, config)
    return config.model_dump()


@router.post("/reset")
def reset_to_defaults(request: Request) -> dict[str, Any]:
    """Reset dashboard to plan defaults."""
    owner_id = _get_owner_id(request)

    plan = "starter"
    try:
        db = _get_db()
        rows = db.fetch_all("owners", {"id": owner_id})
        if rows:
            plan = rows[0].get("plan", "starter")
    except Exception:
        pass

    config = _default_config(plan)
    _save_config(owner_id, config)
    return config.model_dump()
