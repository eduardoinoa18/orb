"""Aria's task management system.

CRUD operations for daily priorities and follow-ups.
Tasks are created via dashboard and included in briefings.
"""

from datetime import datetime
from typing import Any, Optional
import uuid

from app.database.connection import SupabaseService
from config.settings import get_settings


class AriaTaskManager:
    """Manages owner's daily tasks and priorities."""

    def __init__(self):
        self.db = SupabaseService()
        self.settings = get_settings()

    def create_task(
        self,
        title: str,
        description: Optional[str] = None,
        priority: str = "normal",
        due_at: Optional[str] = None,
        related_lead_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a new task."""
        try:
            task_id = str(uuid.uuid4())
            
            task_data = {
                "id": task_id,
                "title": title,
                "description": description,
                "priority": priority,  # high, normal, low
                "status": "pending",  # pending, in_progress, completed
                "due_at": due_at,
                "related_lead_id": related_lead_id,
                "created_at": datetime.utcnow().isoformat(),
            }
            
            result = self.db.client.table("tasks").insert(task_data).execute()
            
            self.db.log_activity(
                agent_id=None,
                owner_id=None,
                action_type="task_created",
                description=f"Task created: {title}",
                cost_cents=0,
            )
            
            return {
                "success": True,
                "task_id": task_id,
                "task": result.data[0] if result.data else task_data,
            }
        except Exception as e:
            print(f"Error creating task: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def get_tasks(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Fetch tasks with optional filters."""
        try:
            query = self.db.client.table("tasks").select("*")
            
            if status:
                query = query.eq("status", status)
            
            if priority:
                query = query.eq("priority", priority)
            
            results = query.order("due_at", desc=False).execute()
            return results.data or []
        except Exception as e:
            print(f"Error fetching tasks: {e}")
            return []

    def update_task(
        self,
        task_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        due_at: Optional[str] = None,
    ) -> dict[str, Any]:
        """Update a task's fields."""
        try:
            update_data = {}
            
            if title is not None:
                update_data["title"] = title
            if description is not None:
                update_data["description"] = description
            if status is not None:
                update_data["status"] = status
            if priority is not None:
                update_data["priority"] = priority
            if due_at is not None:
                update_data["due_at"] = due_at
            
            update_data["updated_at"] = datetime.utcnow().isoformat()
            
            result = self.db.client.table("tasks").update(update_data).eq(
                "id", task_id
            ).execute()
            
            self.db.log_activity(
                agent_id=None,
                owner_id=None,
                action_type="task_updated",
                description=f"Task updated: {task_id}",
                cost_cents=0,
            )
            
            return {
                "success": True,
                "task": result.data[0] if result.data else update_data,
            }
        except Exception as e:
            print(f"Error updating task: {e}")
            return {"success": False, "error": str(e)}

    def complete_task(self, task_id: str) -> dict[str, Any]:
        """Mark a task as completed."""
        return self.update_task(
            task_id,
            status="completed",
        )

    def delete_task(self, task_id: str) -> dict[str, Any]:
        """Delete a task."""
        try:
            result = self.db.client.table("tasks").delete().eq(
                "id", task_id
            ).execute()
            
            self.db.log_activity(
                agent_id=None,
                owner_id=None,
                action_type="task_deleted",
                description=f"Task deleted: {task_id}",
                cost_cents=0,
            )
            
            return {"success": True}
        except Exception as e:
            print(f"Error deleting task: {e}")
            return {"success": False, "error": str(e)}

    def get_tasks_by_priority(self) -> dict[str, list]:
        """Organize all tasks by priority."""
        all_tasks = self.get_tasks(status="pending")
        
        return {
            "high": [t for t in all_tasks if t.get("priority") == "high"],
            "normal": [t for t in all_tasks if t.get("priority") == "normal"],
            "low": [t for t in all_tasks if t.get("priority") == "low"],
        }
