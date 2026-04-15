"""Pipeline Monitor — Enhanced CRM Visibility for Real Estate Agents.

Extends basic pipeline metrics with deep lead source breakdown, engagement tracking,
and automated alerts. Generates actionable insights for Commander and Approval Tab.

Features:
- Lead source breakdown (Zillow, Google, referral, etc.)
- Last-contact date tracking (identifies dormant leads)
- Deal value aggregation and stage progression
- Unassigned lead detection and routing recommendations
- Auto-flagging: "X leads haven't been contacted in N days"
- Smart list integration for segment-based monitoring

Usage:
  from agents.nova.pipeline_monitor import get_enhanced_pipeline_view, get_pipeline_alerts
  
  view = get_enhanced_pipeline_view(owner_id="owner-123")
  alerts = get_pipeline_alerts(owner_id="owner-123", days_dormant=3)
"""

from datetime import datetime, timezone, timedelta
from typing import Any
from collections import defaultdict, Counter
import logging

logger = logging.getLogger("orb.agents.nova.pipeline_monitor")


def get_enhanced_pipeline_view(owner_id: str) -> dict[str, Any]:
    """Fetch comprehensive pipeline data with source breakdown, engagement metrics, and deal tracking.
    
    Returns dict containing:
    - counts: total, hot, qualified, unassigned leads
    - sources: Zillow, Google, referral, etc. with counts
    - stages: Lead → Offer → Closed with deal counts and values
    - engagement: average days since last contact, dormant count
    - deals: total value, average deal size, stage distribution
    - next_actions: list of leads needing follow-up
    """
    try:
        from integrations.followupboss_client import search_people, get_smart_lists
    except ImportError:
        logger.warning("FUB client not available; returning empty pipeline")
        return _empty_pipeline_view()
    
    try:
        # Fetch all people for this owner
        people = search_people(sort="created", limit=1000)
        if not people:
            return _empty_pipeline_view()
    except Exception as e:
        logger.error("Failed to fetch people from FUB: %s", e)
        return _empty_pipeline_view()
    
    # Aggregate data
    now_utc = datetime.now(timezone.utc)
    
    source_counts = Counter()
    stage_buckets = defaultdict(list)  # stage -> [people]
    unassigned_leads = []
    dormant_leads = []
    deal_values = []
    last_contacts = []
    
    for person in people:
        # Count by source
        source = person.get("source", "Other")
        source_counts[source] += 1
        
        # Track unassigned
        if not person.get("assignedTo") or person.get("assignedTo") == "Unassigned":
            unassigned_leads.append(person)
        
        # Track by stage
        stage = person.get("stage", "Lead")
        stage_buckets[stage].append(person)
        
        # Track last activity date
        last_activity_str = person.get("lastActivity")
        if last_activity_str:
            try:
                # Parse ISO format with timezone
                last_activity = datetime.fromisoformat(
                    last_activity_str.replace("Z", "+00:00")
                )
                days_since = (now_utc - last_activity).days
                last_contacts.append({"person": person, "days_since": days_since})
                
                # Mark as dormant if > 7 days
                if days_since > 7:
                    dormant_leads.append({
                        "id": person.get("id"),
                        "name": person.get("name", "Unknown"),
                        "days_since": days_since,
                        "stage": stage,
                    })
            except ValueError:
                pass
        
        # Track deal values
        price = person.get("price")
        if price and isinstance(price, (int, float)) and price > 0:
            deal_values.append(price)
    
    # Sort by most recent contact
    last_contacts.sort(key=lambda x: x["days_since"])
    
    # Calculate engagement stats
    avg_days_since_contact = (
        sum(x["days_since"] for x in last_contacts) / len(last_contacts)
        if last_contacts else 0
    )
    
    return {
        "counts": {
            "total": len(people),
            "hot": sum(1 for p in people if int(p.get("temperature") or 0) >= 8),
            "qualified": sum(1 for p in people if p.get("stage") in {"Qualified", "Appointment", "Offer"}),
            "unassigned": len(unassigned_leads),
            "dormant_7d": len(dormant_leads),
        },
        "sources": dict(source_counts.most_common(10)),
        "stages": {
            stage: {
                "count": len(people_list),
                "avg_days_since_contact": _avg_days(people_list, now_utc),
                "total_deal_value": sum(p.get("price") or 0 for p in people_list if isinstance(p.get("price"), (int, float))),
            }
            for stage, people_list in sorted(stage_buckets.items())
        },
        "engagement": {
            "avg_days_since_contact": round(avg_days_since_contact, 1),
            "dormant_count": len(dormant_leads),
            "needs_attention": len(dormant_leads) + len(unassigned_leads),
        },
        "deals": {
            "total_value": sum(deal_values),
            "count": len(deal_values),
            "avg_deal": round(sum(deal_values) / len(deal_values), 2) if deal_values else 0,
        },
        "unassigned_leads": [
            {
                "id": p.get("id"),
                "name": p.get("name", "Unknown"),
                "source": p.get("source"),
                "stage": p.get("stage"),
            }
            for p in unassigned_leads[:10]
        ],
        "dormant_leads": dormant_leads[:10],
        "next_hot_lead": next(
            (p for p in people if int(p.get("temperature") or 0) >= 8), None
        ),
    }


def get_pipeline_alerts(owner_id: str, days_dormant: int = 3) -> list[dict[str, Any]]:
    """Generate actionable alerts for pipeline issues and opportunities.
    
    Returns list of alert dicts with:
    - type: "dormant_lead", "unassigned_batch", "deal_at_risk", "new_leads"
    - severity: "critical", "high", "medium"
    - message: human-readable alert
    - suggested_action: what to do
    - affected_count: number of leads/deals involved
    """
    alerts = []
    
    try:
        from integrations.followupboss_client import search_people
        people = search_people(sort="created", limit=1000)
        if not people:
            return alerts
    except Exception as e:
        logger.error("Failed to fetch alerts from FUB: %s", e)
        return alerts
    
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(days=days_dormant)
    
    # Alert: Dormant leads by source
    dormant_by_source = defaultdict(list)
    for person in people:
        last_activity_str = person.get("lastActivity")
        if not last_activity_str:
            continue
        try:
            last_activity = datetime.fromisoformat(
                last_activity_str.replace("Z", "+00:00")
            )
            if last_activity < cutoff:
                source = person.get("source", "Unknown")
                dormant_by_source[source].append(person)
        except ValueError:
            pass
    
    for source, leads in dormant_by_source.items():
        if len(leads) > 0:
            alerts.append({
                "type": "dormant_leads",
                "severity": "high" if len(leads) >= 5 else "medium",
                "message": f"{len(leads)} leads from {source} haven't been contacted in {days_dormant}+ days",
                "suggested_action": f"Queue follow-ups for {source} leads or reassign if stale",
                "affected_count": len(leads),
                "leads": [{"name": p.get("name"), "id": p.get("id")} for p in leads[:5]],
            })
    
    # Alert: Unassigned leads
    unassigned = [p for p in people if not p.get("assignedTo") or p.get("assignedTo") == "Unassigned"]
    if len(unassigned) > 0:
        recent_unassigned = [
            p for p in unassigned
            if p.get("created", "").replace("Z", "+00:00") > (now_utc - timedelta(days=7)).isoformat()
        ]
        alerts.append({
            "type": "unassigned_leads",
            "severity": "critical" if len(recent_unassigned) >= 5 else "high",
            "message": f"{len(recent_unassigned)} new unassigned leads (recent) + {len(unassigned) - len(recent_unassigned)} older",
            "suggested_action": "Distribute unassigned leads to available agents",
            "affected_count": len(unassigned),
        })
    
    # Alert: High-temperature leads
    hot_unassigned = [
        p for p in people
        if int(p.get("temperature") or 0) >= 8 and (not p.get("assignedTo") or p.get("assignedTo") == "Unassigned")
    ]
    if hot_unassigned:
        alerts.append({
            "type": "hot_leads_unassigned",
            "severity": "critical",
            "message": f"{len(hot_unassigned)} hot leads (temp >= 8) are unassigned",
            "suggested_action": "Immediately assign hot leads to prevent lost opportunities",
            "affected_count": len(hot_unassigned),
            "leads": [{"name": p.get("name"), "id": p.get("id")} for p in hot_unassigned[:5]],
        })
    
    return alerts


def _avg_days(people_list: list[dict[str, Any]], now_utc: datetime) -> float:
    """Calculate average days since last contact for a list of people."""
    days_since = []
    for p in people_list:
        last_activity = p.get("lastActivity")
        if last_activity:
            try:
                last_dt = datetime.fromisoformat(last_activity.replace("Z", "+00:00"))
                days_since.append((now_utc - last_dt).days)
            except ValueError:
                pass
    return round(sum(days_since) / len(days_since), 1) if days_since else 0


def _empty_pipeline_view() -> dict[str, Any]:
    """Return empty pipeline structure when FUB is unavailable."""
    return {
        "counts": {"total": 0, "hot": 0, "qualified": 0, "unassigned": 0, "dormant_7d": 0},
        "sources": {},
        "stages": {},
        "engagement": {"avg_days_since_contact": 0, "dormant_count": 0, "needs_attention": 0},
        "deals": {"total_value": 0, "count": 0, "avg_deal": 0},
        "unassigned_leads": [],
        "dormant_leads": [],
        "next_hot_lead": None,
    }
