"""Tool Registry - Single source of truth for all Commander tools.

This replaces the hardcoded tools list and makes the system maintainable.
Each tool is defined once with: name, category, required permission, env vars needed, description.

This enables:
- Auto-generated /tools/available endpoint
- Auto-generated tool documentation
- Permission validation
- Admin UI to show which integrations enable which tools
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ToolMetadata:
    """Metadata for a single Commander tool."""
    tool_id: str
    name: str
    description: str
    category: str
    required_permission: str
    required_env_vars: list[str]
    admin_only: bool = False
    always_available: bool = False  # e.g., dashboard tools don't need external API


# ============================================================================
# TOOL REGISTRY - All 83+ tools defined once
# ============================================================================

TOOL_REGISTRY: dict[str, ToolMetadata] = {
    # ========== Slack (3 tools) ==========
    "slack_send": ToolMetadata(
        tool_id="slack_send",
        name="Send Slack Message",
        description="Send a message to a Slack channel",
        category="Communications",
        required_permission="SEND_SLACK",
        required_env_vars=["SLACK_BOT_TOKEN"],
    ),
    "slack_alert": ToolMetadata(
        tool_id="slack_alert",
        name="Send Slack Alert",
        description="Send a formatted alert card to Slack",
        category="Communications",
        required_permission="SEND_SLACK",
        required_env_vars=["SLACK_BOT_TOKEN"],
    ),
    "slack_list_channels": ToolMetadata(
        tool_id="slack_list_channels",
        name="List Slack Channels",
        description="List all available Slack channels",
        category="Communications",
        required_permission="SEND_SLACK",
        required_env_vars=["SLACK_BOT_TOKEN"],
    ),

    # ========== Google Calendar (4 tools) ==========
    "calendar_list": ToolMetadata(
        tool_id="calendar_list",
        name="List Calendar Events",
        description="List upcoming calendar events",
        category="Calendar & Scheduling",
        required_permission="READ_CALENDAR",
        required_env_vars=["GOOGLE_REFRESH_TOKEN"],
    ),
    "calendar_create": ToolMetadata(
        tool_id="calendar_create",
        name="Create Calendar Event",
        description="Create a new calendar event",
        category="Calendar & Scheduling",
        required_permission="CREATE_CALENDAR_EVENT",
        required_env_vars=["GOOGLE_REFRESH_TOKEN"],
    ),
    "calendar_cancel": ToolMetadata(
        tool_id="calendar_cancel",
        name="Cancel Calendar Event",
        description="Cancel an existing calendar event",
        category="Calendar & Scheduling",
        required_permission="CANCEL_CALENDAR_EVENT",
        required_env_vars=["GOOGLE_REFRESH_TOKEN"],
    ),
    "calendar_check": ToolMetadata(
        tool_id="calendar_check",
        name="Check Availability",
        description="Check availability in a time window",
        category="Calendar & Scheduling",
        required_permission="READ_CALENDAR",
        required_env_vars=["GOOGLE_REFRESH_TOKEN"],
    ),

    # ========== Email & SMS (2 tools) ==========
    "email_send": ToolMetadata(
        tool_id="email_send",
        name="Send Email",
        description="Send an email via Resend",
        category="Communications",
        required_permission="SEND_EMAIL",
        required_env_vars=["RESEND_API_KEY"],
    ),
    "sms_send": ToolMetadata(
        tool_id="sms_send",
        name="Send SMS",
        description="Send an SMS message via Twilio",
        category="Communications",
        required_permission="SEND_SMS",
        required_env_vars=["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER"],
    ),

    # ========== Notion (3 tools) ==========
    "notion_create": ToolMetadata(
        tool_id="notion_create",
        name="Create Notion Page",
        description="Create a new page in Notion",
        category="Productivity",
        required_permission="WRITE_NOTION",
        required_env_vars=["NOTION_API_KEY"],
    ),
    "notion_log": ToolMetadata(
        tool_id="notion_log",
        name="Log to Notion",
        description="Append a log entry to a Notion database",
        category="Productivity",
        required_permission="WRITE_NOTION",
        required_env_vars=["NOTION_API_KEY"],
    ),
    "notion_search": ToolMetadata(
        tool_id="notion_search",
        name="Search Notion",
        description="Search your Notion workspace",
        category="Productivity",
        required_permission="READ_NOTION",
        required_env_vars=["NOTION_API_KEY"],
    ),

    # ========== HubSpot CRM (4 tools) ==========
    "hubspot_contact": ToolMetadata(
        tool_id="hubspot_contact",
        name="Create/Find HubSpot Contact",
        description="Create or find a contact in HubSpot",
        category="CRM",
        required_permission="WRITE_HUBSPOT",
        required_env_vars=["HUBSPOT_API_KEY"],
    ),
    "hubspot_deal": ToolMetadata(
        tool_id="hubspot_deal",
        name="Create HubSpot Deal",
        description="Create a new deal in HubSpot",
        category="CRM",
        required_permission="WRITE_HUBSPOT",
        required_env_vars=["HUBSPOT_API_KEY"],
    ),
    "hubspot_note": ToolMetadata(
        tool_id="hubspot_note",
        name="Log HubSpot Note",
        description="Add a note to a HubSpot contact",
        category="CRM",
        required_permission="WRITE_HUBSPOT",
        required_env_vars=["HUBSPOT_API_KEY"],
    ),
    "hubspot_search": ToolMetadata(
        tool_id="hubspot_search",
        name="Search HubSpot Contacts",
        description="Search for contacts in HubSpot",
        category="CRM",
        required_permission="READ_HUBSPOT",
        required_env_vars=["HUBSPOT_API_KEY"],
    ),

    # ========== Follow Up Boss CRM (9 tools) ==========
    "fub_contact": ToolMetadata(
        tool_id="fub_contact",
        name="Create FUB Contact",
        description="Create a contact in Follow Up Boss",
        category="CRM",
        required_permission="WRITE_FUB",
        required_env_vars=["FOLLOWUPBOSS_API_KEY"],
    ),
    "fub_search": ToolMetadata(
        tool_id="fub_search",
        name="Search FUB Contacts",
        description="Search for contacts in Follow Up Boss",
        category="CRM",
        required_permission="READ_FUB",
        required_env_vars=["FOLLOWUPBOSS_API_KEY"],
    ),
    "fub_note": ToolMetadata(
        tool_id="fub_note",
        name="Add FUB Note",
        description="Add a note to a FUB contact",
        category="CRM",
        required_permission="WRITE_FUB",
        required_env_vars=["FOLLOWUPBOSS_API_KEY"],
    ),
    "fub_deal": ToolMetadata(
        tool_id="fub_deal",
        name="Create FUB Deal",
        description="Create a deal in Follow Up Boss",
        category="CRM",
        required_permission="WRITE_FUB",
        required_env_vars=["FOLLOWUPBOSS_API_KEY"],
    ),
    "fub_task": ToolMetadata(
        tool_id="fub_task",
        name="Create FUB Task",
        description="Create a task in Follow Up Boss",
        category="CRM",
        required_permission="WRITE_FUB",
        required_env_vars=["FOLLOWUPBOSS_API_KEY"],
    ),
    "fub_stage": ToolMetadata(
        tool_id="fub_stage",
        name="Change FUB Stage",
        description="Move a deal to a different stage in FUB",
        category="CRM",
        required_permission="WRITE_FUB",
        required_env_vars=["FOLLOWUPBOSS_API_KEY"],
    ),
    "fub_call": ToolMetadata(
        tool_id="fub_call",
        name="Log FUB Call",
        description="Log a call in Follow Up Boss",
        category="CRM",
        required_permission="WRITE_FUB",
        required_env_vars=["FOLLOWUPBOSS_API_KEY"],
    ),
    "fub_smart_lists": ToolMetadata(
        tool_id="fub_smart_lists",
        name="Get FUB Smart Lists",
        description="Retrieve FUB smart list filters",
        category="CRM",
        required_permission="READ_FUB",
        required_env_vars=["FOLLOWUPBOSS_API_KEY"],
    ),
    "fub_tasks_pending": ToolMetadata(
        tool_id="fub_tasks_pending",
        name="Get FUB Pending Tasks",
        description="Get pending tasks from Follow Up Boss",
        category="CRM",
        required_permission="READ_FUB",
        required_env_vars=["FOLLOWUPBOSS_API_KEY"],
    ),

    # ========== GitHub (3 tools) ==========
    "github_issue": ToolMetadata(
        tool_id="github_issue",
        name="Create GitHub Issue",
        description="Create a new GitHub issue",
        category="Development",
        required_permission="WRITE_GITHUB",
        required_env_vars=["GITHUB_TOKEN"],
    ),
    "github_comment": ToolMetadata(
        tool_id="github_comment",
        name="Comment on GitHub Issue",
        description="Add a comment to a GitHub issue",
        category="Development",
        required_permission="WRITE_GITHUB",
        required_env_vars=["GITHUB_TOKEN"],
    ),
    "github_commits": ToolMetadata(
        tool_id="github_commits",
        name="Get GitHub Commits",
        description="Retrieve recent commits from a repository",
        category="Development",
        required_permission="READ_GITHUB",
        required_env_vars=["GITHUB_TOKEN"],
    ),

    # ========== Voice (1 tool) ==========
    "voice_speak": ToolMetadata(
        tool_id="voice_speak",
        name="Text to Speech",
        description="Convert text to speech using ElevenLabs",
        category="AI & Voice",
        required_permission="USE_VOICE",
        required_env_vars=["ELEVENLABS_API_KEY"],
    ),

    # ========== Instagram (3 tools) ==========
    "instagram_send": ToolMetadata(
        tool_id="instagram_send",
        name="Send Instagram DM",
        description="Send a direct message on Instagram",
        category="Social Media",
        required_permission="SEND_INSTAGRAM",
        required_env_vars=["INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_BUSINESS_ID"],
    ),
    "instagram_reply": ToolMetadata(
        tool_id="instagram_reply",
        name="Reply to Instagram Comment",
        description="Reply to a comment on an Instagram post",
        category="Social Media",
        required_permission="SEND_INSTAGRAM",
        required_env_vars=["INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_BUSINESS_ID"],
    ),
    "instagram_post": ToolMetadata(
        tool_id="instagram_post",
        name="Publish Instagram Photo",
        description="Publish a photo to Instagram",
        category="Social Media",
        required_permission="SEND_INSTAGRAM",
        required_env_vars=["INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_BUSINESS_ID"],
    ),

    # ========== Facebook Messenger (2 tools) ==========
    "messenger_send": ToolMetadata(
        tool_id="messenger_send",
        name="Send Messenger Message",
        description="Send a message on Facebook Messenger",
        category="Social Media",
        required_permission="SEND_MESSENGER",
        required_env_vars=["FACEBOOK_PAGE_TOKEN", "FACEBOOK_APP_SECRET"],
    ),
    "messenger_buttons": ToolMetadata(
        tool_id="messenger_buttons",
        name="Messenger Message with Buttons",
        description="Send a Messenger message with quick-reply buttons",
        category="Social Media",
        required_permission="SEND_MESSENGER",
        required_env_vars=["FACEBOOK_PAGE_TOKEN", "FACEBOOK_APP_SECRET"],
    ),

    # ========== Microsoft Teams (2 tools) ==========
    "teams_message": ToolMetadata(
        tool_id="teams_message",
        name="Post to Teams Channel",
        description="Post a message to a Microsoft Teams channel",
        category="Communications",
        required_permission="SEND_TEAMS",
        required_env_vars=["TEAMS_WEBHOOK_URL"],
    ),
    "teams_alert": ToolMetadata(
        tool_id="teams_alert",
        name="Teams Alert Card",
        description="Send a formatted alert card to Teams",
        category="Communications",
        required_permission="SEND_TEAMS",
        required_env_vars=["TEAMS_WEBHOOK_URL"],
    ),

    # ========== Airtable (4 tools) ==========
    "airtable_read": ToolMetadata(
        tool_id="airtable_read",
        name="Read Airtable Records",
        description="Read records from an Airtable table",
        category="Database",
        required_permission="READ_AIRTABLE",
        required_env_vars=["AIRTABLE_API_KEY", "AIRTABLE_BASE_ID"],
    ),
    "airtable_create": ToolMetadata(
        tool_id="airtable_create",
        name="Create Airtable Record",
        description="Create a new record in Airtable",
        category="Database",
        required_permission="WRITE_AIRTABLE",
        required_env_vars=["AIRTABLE_API_KEY", "AIRTABLE_BASE_ID"],
    ),
    "airtable_update": ToolMetadata(
        tool_id="airtable_update",
        name="Update Airtable Record",
        description="Update an existing Airtable record",
        category="Database",
        required_permission="WRITE_AIRTABLE",
        required_env_vars=["AIRTABLE_API_KEY", "AIRTABLE_BASE_ID"],
    ),
    "airtable_search": ToolMetadata(
        tool_id="airtable_search",
        name="Search Airtable Records",
        description="Search for records in Airtable by field value",
        category="Database",
        required_permission="READ_AIRTABLE",
        required_env_vars=["AIRTABLE_API_KEY", "AIRTABLE_BASE_ID"],
    ),

    # ========== Zapier (3 tools) ==========
    "zapier_trigger": ToolMetadata(
        tool_id="zapier_trigger",
        name="Trigger Zapier Workflow",
        description="Trigger any Zapier webhook",
        category="Automation",
        required_permission="TRIGGER_ZAPIER",
        required_env_vars=["ZAPIER_WEBHOOK_URL"],
    ),
    "zapier_new_lead": ToolMetadata(
        tool_id="zapier_new_lead",
        name="Zapier: New Lead Event",
        description="Fire Zapier 'new_lead' trigger",
        category="Automation",
        required_permission="TRIGGER_ZAPIER",
        required_env_vars=["ZAPIER_WEBHOOK_URL"],
    ),
    "zapier_deal_closed": ToolMetadata(
        tool_id="zapier_deal_closed",
        name="Zapier: Deal Closed Event",
        description="Fire Zapier 'deal_closed' trigger",
        category="Automation",
        required_permission="TRIGGER_ZAPIER",
        required_env_vars=["ZAPIER_WEBHOOK_URL"],
    ),

    # ========== Calendly (3 tools) ==========
    "calendly_list": ToolMetadata(
        tool_id="calendly_list",
        name="List Calendly Meetings",
        description="List upcoming Calendly meetings",
        category="Calendar & Scheduling",
        required_permission="READ_CALENDLY",
        required_env_vars=["CALENDLY_API_KEY"],
    ),
    "calendly_link": ToolMetadata(
        tool_id="calendly_link",
        name="Create Calendly Scheduling Link",
        description="Generate a scheduling link for a lead",
        category="Calendar & Scheduling",
        required_permission="WRITE_CALENDLY",
        required_env_vars=["CALENDLY_API_KEY"],
    ),
    "calendly_cancel": ToolMetadata(
        tool_id="calendly_cancel",
        name="Cancel Calendly Event",
        description="Cancel a Calendly event",
        category="Calendar & Scheduling",
        required_permission="WRITE_CALENDLY",
        required_env_vars=["CALENDLY_API_KEY"],
    ),

    # ========== Mailchimp (3 tools) ==========
    "mailchimp_add": ToolMetadata(
        tool_id="mailchimp_add",
        name="Add Mailchimp Subscriber",
        description="Add or update a subscriber in Mailchimp",
        category="Email Marketing",
        required_permission="WRITE_MAILCHIMP",
        required_env_vars=["MAILCHIMP_API_KEY", "MAILCHIMP_SERVER"],
    ),
    "mailchimp_tag": ToolMetadata(
        tool_id="mailchimp_tag",
        name="Tag Mailchimp Subscriber",
        description="Apply tags to a Mailchimp subscriber",
        category="Email Marketing",
        required_permission="WRITE_MAILCHIMP",
        required_env_vars=["MAILCHIMP_API_KEY", "MAILCHIMP_SERVER"],
    ),
    "mailchimp_unsubscribe": ToolMetadata(
        tool_id="mailchimp_unsubscribe",
        name="Unsubscribe from Mailchimp",
        description="Unsubscribe a contact from Mailchimp",
        category="Email Marketing",
        required_permission="WRITE_MAILCHIMP",
        required_env_vars=["MAILCHIMP_API_KEY", "MAILCHIMP_SERVER"],
    ),

    # ========== Pipedrive (4 tools) ==========
    "pipedrive_contact": ToolMetadata(
        tool_id="pipedrive_contact",
        name="Pipedrive Contact",
        description="Create or find a person in Pipedrive",
        category="CRM",
        required_permission="WRITE_PIPEDRIVE",
        required_env_vars=["PIPEDRIVE_API_KEY"],
    ),
    "pipedrive_deal": ToolMetadata(
        tool_id="pipedrive_deal",
        name="Create Pipedrive Deal",
        description="Create a deal in Pipedrive",
        category="CRM",
        required_permission="WRITE_PIPEDRIVE",
        required_env_vars=["PIPEDRIVE_API_KEY"],
    ),
    "pipedrive_note": ToolMetadata(
        tool_id="pipedrive_note",
        name="Add Pipedrive Note",
        description="Add a note to a deal or person in Pipedrive",
        category="CRM",
        required_permission="WRITE_PIPEDRIVE",
        required_env_vars=["PIPEDRIVE_API_KEY"],
    ),
    "pipedrive_stage": ToolMetadata(
        tool_id="pipedrive_stage",
        name="Move Pipedrive Deal Stage",
        description="Move a deal to a different stage",
        category="CRM",
        required_permission="WRITE_PIPEDRIVE",
        required_env_vars=["PIPEDRIVE_API_KEY"],
    ),

    # ========== Monday.com (3 tools) ==========
    "monday_item": ToolMetadata(
        tool_id="monday_item",
        name="Create Monday.com Item",
        description="Create an item on a Monday.com board",
        category="Project Management",
        required_permission="WRITE_MONDAY",
        required_env_vars=["MONDAY_API_KEY"],
    ),
    "monday_update": ToolMetadata(
        tool_id="monday_update",
        name="Post Monday.com Update",
        description="Post a comment or update on a Monday item",
        category="Project Management",
        required_permission="WRITE_MONDAY",
        required_env_vars=["MONDAY_API_KEY"],
    ),
    "monday_move": ToolMetadata(
        tool_id="monday_move",
        name="Move Monday.com Item",
        description="Move an item to a different group",
        category="Project Management",
        required_permission="WRITE_MONDAY",
        required_env_vars=["MONDAY_API_KEY"],
    ),

    # ========== OpenPhone (3 tools) ==========
    "openphone_sms": ToolMetadata(
        tool_id="openphone_sms",
        name="Send OpenPhone SMS",
        description="Send an SMS from OpenPhone",
        category="Communications",
        required_permission="SEND_SMS",
        required_env_vars=["OPENPHONE_API_KEY"],
    ),
    "openphone_call": ToolMetadata(
        tool_id="openphone_call",
        name="Initiate OpenPhone Call",
        description="Initiate an outbound call",
        category="Communications",
        required_permission="SEND_SMS",
        required_env_vars=["OPENPHONE_API_KEY"],
    ),
    "openphone_history": ToolMetadata(
        tool_id="openphone_history",
        name="OpenPhone Call/Message History",
        description="Get call or message history",
        category="Communications",
        required_permission="READ_SMS",
        required_env_vars=["OPENPHONE_API_KEY"],
    ),

    # ========== DocuSign (3 tools) ==========
    "docusign_send": ToolMetadata(
        tool_id="docusign_send",
        name="Send DocuSign Envelope",
        description="Send a document for eSignature",
        category="eSignature & Legal",
        required_permission="SEND_DOCUSIGN",
        required_env_vars=["DOCUSIGN_ACCOUNT_ID", "DOCUSIGN_ACCESS_TOKEN"],
    ),
    "docusign_status": ToolMetadata(
        tool_id="docusign_status",
        name="DocuSign Envelope Status",
        description="Check the signing status of a DocuSign envelope",
        category="eSignature & Legal",
        required_permission="READ_DOCUSIGN",
        required_env_vars=["DOCUSIGN_ACCOUNT_ID", "DOCUSIGN_ACCESS_TOKEN"],
    ),
    "docusign_void": ToolMetadata(
        tool_id="docusign_void",
        name="Void DocuSign Envelope",
        description="Void or cancel a DocuSign envelope",
        category="eSignature & Legal",
        required_permission="CANCEL_DOCUSIGN",
        required_env_vars=["DOCUSIGN_ACCOUNT_ID", "DOCUSIGN_ACCESS_TOKEN"],
    ),

    # ========== LinkedIn (2 tools) ==========
    "linkedin_post": ToolMetadata(
        tool_id="linkedin_post",
        name="Post to LinkedIn",
        description="Post a text update to LinkedIn",
        category="Social Media",
        required_permission="SEND_LINKEDIN",
        required_env_vars=["LINKEDIN_ACCESS_TOKEN"],
    ),
    "linkedin_post_link": ToolMetadata(
        tool_id="linkedin_post_link",
        name="LinkedIn Post with Link Card",
        description="Post a LinkedIn update with a link card",
        category="Social Media",
        required_permission="SEND_LINKEDIN",
        required_env_vars=["LINKEDIN_ACCESS_TOKEN"],
    ),

    # ========== Twitter / X (2 tools) ==========
    "twitter_post": ToolMetadata(
        tool_id="twitter_post",
        name="Post Tweet",
        description="Post a tweet to X/Twitter",
        category="Social Media",
        required_permission="SEND_TWITTER",
        required_env_vars=["TWITTER_API_KEY", "TWITTER_API_SECRET", "TWITTER_ACCESS_TOKEN"],
    ),
    "twitter_search": ToolMetadata(
        tool_id="twitter_search",
        name="Search Tweets",
        description="Search for recent tweets",
        category="Social Media",
        required_permission="READ_TWITTER",
        required_env_vars=["TWITTER_BEARER_TOKEN"],
    ),

    # ========== Shopify (3 tools) ==========
    "shopify_orders": ToolMetadata(
        tool_id="shopify_orders",
        name="Get Shopify Orders",
        description="List Shopify orders with optional filters",
        category="E-Commerce",
        required_permission="READ_SHOPIFY",
        required_env_vars=["SHOPIFY_STORE_DOMAIN", "SHOPIFY_ACCESS_TOKEN"],
    ),
    "shopify_customer": ToolMetadata(
        tool_id="shopify_customer",
        name="Search Shopify Customers",
        description="Search for Shopify customers",
        category="E-Commerce",
        required_permission="READ_SHOPIFY",
        required_env_vars=["SHOPIFY_STORE_DOMAIN", "SHOPIFY_ACCESS_TOKEN"],
    ),
    "shopify_discount": ToolMetadata(
        tool_id="shopify_discount",
        name="Create Shopify Discount Code",
        description="Create a discount/promotion code",
        category="E-Commerce",
        required_permission="WRITE_SHOPIFY",
        required_env_vars=["SHOPIFY_STORE_DOMAIN", "SHOPIFY_ACCESS_TOKEN"],
    ),

    # ========== Typeform (2 tools) ==========
    "typeform_responses": ToolMetadata(
        tool_id="typeform_responses",
        name="Get Typeform Responses",
        description="Retrieve form responses as structured leads",
        category="Lead Capture",
        required_permission="READ_TYPEFORM",
        required_env_vars=["TYPEFORM_API_KEY"],
    ),
    "typeform_forms": ToolMetadata(
        tool_id="typeform_forms",
        name="List Typeform Forms",
        description="List available Typeform forms",
        category="Lead Capture",
        required_permission="READ_TYPEFORM",
        required_env_vars=["TYPEFORM_API_KEY"],
    ),

    # ========== Dashboard Customization (7 tools) - Always available ==========
    "dashboard_list": ToolMetadata(
        tool_id="dashboard_list",
        name="List Dashboard Tabs & Widgets",
        description="Show the owner's current dashboard configuration",
        category="Dashboard",
        required_permission="CUSTOMIZE_DASHBOARD",
        required_env_vars=[],
        always_available=True,
    ),
    "dashboard_add_tab": ToolMetadata(
        tool_id="dashboard_add_tab",
        name="Add Dashboard Tab",
        description="Add a new tab to the dashboard",
        category="Dashboard",
        required_permission="CUSTOMIZE_DASHBOARD",
        required_env_vars=[],
        always_available=True,
    ),
    "dashboard_remove_tab": ToolMetadata(
        tool_id="dashboard_remove_tab",
        name="Remove Dashboard Tab",
        description="Remove a tab from the dashboard",
        category="Dashboard",
        required_permission="CUSTOMIZE_DASHBOARD",
        required_env_vars=[],
        always_available=True,
    ),
    "dashboard_add_widget": ToolMetadata(
        tool_id="dashboard_add_widget",
        name="Add Widget to Tab",
        description="Add a widget to a dashboard tab",
        category="Dashboard",
        required_permission="CUSTOMIZE_DASHBOARD",
        required_env_vars=[],
        always_available=True,
    ),
    "dashboard_remove_widget": ToolMetadata(
        tool_id="dashboard_remove_widget",
        name="Remove Widget from Tab",
        description="Remove a widget from a tab",
        category="Dashboard",
        required_permission="CUSTOMIZE_DASHBOARD",
        required_env_vars=[],
        always_available=True,
    ),
    "dashboard_change_theme": ToolMetadata(
        tool_id="dashboard_change_theme",
        name="Change Dashboard Theme",
        description="Change dashboard accent color, card style, or density",
        category="Dashboard",
        required_permission="CUSTOMIZE_DASHBOARD",
        required_env_vars=[],
        always_available=True,
    ),
    "dashboard_reorder_tabs": ToolMetadata(
        tool_id="dashboard_reorder_tabs",
        name="Reorder Dashboard Tabs",
        description="Rearrange dashboard tabs",
        category="Dashboard",
        required_permission="CUSTOMIZE_DASHBOARD",
        required_env_vars=[],
        always_available=True,
    ),

    # ========== System / Utility (1 tool) ==========
    "rate_status": ToolMetadata(
        tool_id="rate_status",
        name="Check Rate Limits",
        description="Get current API rate limit status",
        category="System",
        required_permission="CUSTOMIZE_DASHBOARD",  # Minimal permission
        required_env_vars=[],
        always_available=True,
    ),
}


def get_all_tools() -> dict[str, ToolMetadata]:
    """Return the complete tool registry."""
    return TOOL_REGISTRY.copy()


def get_tool(tool_id: str) -> Optional[ToolMetadata]:
    """Get metadata for a specific tool."""
    return TOOL_REGISTRY.get(tool_id)


def get_tools_by_category(category: str) -> list[ToolMetadata]:
    """Get all tools in a specific category."""
    return [t for t in TOOL_REGISTRY.values() if t.category == category]


def get_required_integrations() -> dict[str, list[str]]:
    """Map integration names to required env vars.
    
    Useful for admin connections page to show "this integration enables X tools".
    """
    integration_to_tools: dict[str, set[str]] = {}
    
    for tool in TOOL_REGISTRY.values():
        if tool.always_available:
            continue
        for env_var in tool.required_env_vars:
            if env_var not in integration_to_tools:
                integration_to_tools[env_var] = set()
            integration_to_tools[env_var].add(tool.tool_id)
    
    return {k: sorted(list(v)) for k, v in integration_to_tools.items()}

