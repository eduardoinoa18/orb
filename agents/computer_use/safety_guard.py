"""Safety guardrails for all computer-use actions."""

from __future__ import annotations

from dataclasses import dataclass


ALLOWED_ACTIONS = [
    "read_screen",
    "click_button",
    "fill_form_field",
    "navigate_url",
    "copy_text",
    "scroll_page",
    "select_dropdown",
    "upload_file",
    "download_file",
    "take_screenshot",
]

NEVER_ALLOWED = [
    "delete_files",
    "format_drive",
    "access_banking_directly",
    "change_passwords",
    "install_software_without_approval",
    "send_email_without_approval",
    "make_purchases_without_approval",
    "access_private_documents",
    "record_audio_or_video",
]


@dataclass
class SafetyDecision:
    allowed: bool
    requires_approval: bool
    reason: str


class SafetyGuard:
    """Central policy engine for validating any requested computer action."""

    @staticmethod
    def evaluate(action: str, description: str = "") -> SafetyDecision:
        action_norm = action.strip().lower()
        if action_norm in NEVER_ALLOWED:
            return SafetyDecision(allowed=False, requires_approval=False, reason="Action is explicitly blocked by policy.")
        if action_norm not in ALLOWED_ACTIONS:
            return SafetyDecision(allowed=False, requires_approval=False, reason="Action is not in the allowed action list.")

        requires_approval = SafetyGuard._description_requires_approval(description)
        reason = "Allowed action." if not requires_approval else "Allowed, but owner approval is required for sensitive action."
        return SafetyDecision(allowed=True, requires_approval=requires_approval, reason=reason)

    @staticmethod
    def _description_requires_approval(description: str) -> bool:
        sensitive_terms = ["purchase", "pay", "submit", "send", "money", "billing", "wire"]
        text = description.lower()
        return any(term in text for term in sensitive_terms)
