"""Safety-first browser controller skeleton using Playwright when available."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agents.computer_use.safety_guard import SafetyDecision, SafetyGuard
from app.database.connection import SupabaseService


class BrowserController:
    """Starter browser controller with strict guardrails and audit logging."""

    def __init__(self, screenshot_dir: str = "artifacts/screenshots") -> None:
        self.db = SupabaseService()
        self.playwright = None
        self.browser = None
        self.page = None
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    def launch(self, headless: bool = False, agent_id: str | None = None) -> dict[str, Any]:
        """Launches browser if Playwright is installed; otherwise returns clear guidance."""
        try:
            from playwright.sync_api import sync_playwright
        except Exception as error:
            return {
                "status": "blocked",
                "detail": "Playwright is not installed or browser binaries are missing.",
                "error": str(error),
            }

        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=headless)
        self.page = self.browser.new_page()
        self._log(agent_id, "computer_use", "Browser session launched.", "success")
        return {"status": "launched", "headless": headless}

    def navigate(self, url: str, agent_id: str | None = None) -> dict[str, Any]:
        decision = SafetyGuard.evaluate("navigate_url", f"navigate {url}")
        if not decision.allowed:
            return self._blocked(decision)
        if self.page is None:
            return {"status": "blocked", "detail": "Browser not launched."}

        self._log(agent_id, "computer_use", f"Navigate to {url}", "pending")
        self.page.goto(url)
        screenshot = self._screenshot("navigate")
        self._log(agent_id, "computer_use", f"Navigation complete: {url}", "success", metadata={"screenshot": str(screenshot)})
        return {"status": "ok", "url": url, "screenshot": str(screenshot)}

    def click(self, selector_or_description: str, agent_id: str | None = None, require_approval: bool = False) -> dict[str, Any]:
        desc = f"click {selector_or_description}"
        decision = SafetyGuard.evaluate("click_button", desc)
        if not decision.allowed:
            return self._blocked(decision)
        if require_approval or decision.requires_approval:
            return {"status": "approval_required", "detail": "Owner approval required before click."}
        if self.page is None:
            return {"status": "blocked", "detail": "Browser not launched."}

        self.page.click(selector_or_description)
        screenshot = self._screenshot("click")
        self._log(agent_id, "computer_use", f"Clicked {selector_or_description}", "success", metadata={"screenshot": str(screenshot)})
        return {"status": "ok", "screenshot": str(screenshot)}

    def fill_field(self, field_description: str, value: str, agent_id: str | None = None) -> dict[str, Any]:
        decision = SafetyGuard.evaluate("fill_form_field", f"fill {field_description}")
        if not decision.allowed:
            return self._blocked(decision)
        if self.page is None:
            return {"status": "blocked", "detail": "Browser not launched."}

        self.page.fill(field_description, value)
        screenshot = self._screenshot("fill")
        self._log(agent_id, "computer_use", f"Filled field {field_description}", "success", metadata={"screenshot": str(screenshot)})
        return {"status": "ok", "screenshot": str(screenshot)}

    def read_page_content(self, agent_id: str | None = None) -> dict[str, Any]:
        decision = SafetyGuard.evaluate("read_screen", "read screen content")
        if not decision.allowed:
            return self._blocked(decision)
        if self.page is None:
            return {"status": "blocked", "detail": "Browser not launched."}

        text = self.page.inner_text("body")
        self._log(agent_id, "computer_use", "Read page content.", "success")
        return {"status": "ok", "content": text[:4000]}

    def complete_task(self, task_description: str, url: str, agent_id: str | None = None, require_approval: bool = True) -> dict[str, Any]:
        if require_approval:
            return {"status": "approval_required", "detail": "Task requires owner approval before execution."}

        nav = self.navigate(url=url, agent_id=agent_id)
        if nav.get("status") != "ok":
            return nav

        return {
            "status": "completed",
            "task": task_description,
            "url": url,
            "detail": "Task starter completed (navigation + audit).",
        }

    def _screenshot(self, prefix: str) -> Path:
        if self.page is None:
            return self.screenshot_dir / "missing-page.png"
        filename = self.screenshot_dir / f"{prefix}-{len(list(self.screenshot_dir.glob(prefix + '*')))+1}.png"
        self.page.screenshot(path=str(filename), full_page=True)
        return filename

    def _log(
        self,
        agent_id: str | None,
        action_type: str,
        description: str,
        outcome: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.db.log_activity(
            agent_id=agent_id,
            owner_id=None,
            action_type=action_type,
            description=description,
            cost_cents=0,
            outcome=outcome,
            metadata=metadata,
            needs_approval=outcome == "approval_required",
        )

    def _blocked(self, decision: SafetyDecision) -> dict[str, Any]:
        return {"status": "blocked", "detail": decision.reason, "requires_approval": decision.requires_approval}
