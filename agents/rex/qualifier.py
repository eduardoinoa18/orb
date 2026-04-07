"""Rex lead qualification and scoring logic."""

from __future__ import annotations

import json
import re
from typing import Any

from integrations.anthropic_client import ask_claude_smart


class QualificationResult:
    """Structured qualification result with BANT scoring."""

    def __init__(
        self,
        score: int,
        bant_scores: dict[str, int],
        recommendation: str,
        objections: list[str],
        next_action: str,
    ) -> None:
        self.score = score
        self.bant_scores = bant_scores
        self.recommendation = recommendation
        self.objections = objections
        self.next_action = next_action

    def to_dict(self) -> dict[str, Any]:
        """Returns dict representation."""
        return {
            "score": self.score,
            "bant_scores": self.bant_scores,
            "recommendation": self.recommendation,
            "objections": self.objections,
            "next_action": self.next_action,
        }


class RexQualifier:
    """Qualifies leads using BANT framework and motivation scoring."""

    def __init__(self) -> None:
        pass

    def qualify_lead(
        self,
        lead_id: str,
        owner_id: str,
        conversation_transcript: str,
        property_details: dict[str, Any],
    ) -> QualificationResult:
        """
        Qualifies a lead using BANT (Budget, Authority, Need, Timeline).

        Returns a QualificationResult with scores 0-10 for each BANT criterion.
        Falls back to keyword-based scoring if Claude fails.
        """
        prompt = f"""
Analyze this real estate / MLO conversation for BANT qualification:

CONVERSATION:
{conversation_transcript}

PROPERTY DETAILS:
{json.dumps(property_details, indent=2)}

Score each BANT dimension on 0-10:
- Budget: Does the lead mention or show ability to pay?
- Authority: Is this person a decision-maker?
- Need: How urgent is their need to buy/sell/refinance?
- Timeline: When do they need to act?

Also identify any objections mentioned (price, timing, not interested, already with agent, etc).

Respond ONLY with valid JSON, no markdown or extra text:
{{
  "budget_score": <0-10>,
  "authority_score": <0-10>,
  "need_score": <0-10>,
  "timeline_score": <0-10>,
  "overall_score": <0-10>,
  "recommendation": "Strong prospect" or "Follow up" or "Not qualified",
  "objections": ["objection1", "objection2"],
  "next_action": "Book appointment" or "Send details" or "Follow up in X days"
}}
"""

        try:
            result = ask_claude_smart(
                prompt=prompt,
                system="You are a sales qualification expert. Respond only in valid JSON.",
                max_tokens=512,
                max_budget_cents=3,
            )
            parsed = json.loads(result["text"])
        except Exception:
            # Fallback to keyword-based scoring
            return self._fallback_qualification(conversation_transcript, property_details)

        bant_scores = {
            "budget": int(parsed.get("budget_score", 5)),
            "authority": int(parsed.get("authority_score", 5)),
            "need": int(parsed.get("need_score", 5)),
            "timeline": int(parsed.get("timeline_score", 5)),
        }
        overall_score = int(parsed.get("overall_score", 5))
        recommendation = str(parsed.get("recommendation", "Follow up"))
        objections = parsed.get("objections", [])
        next_action = str(parsed.get("next_action", "Follow up"))

        return QualificationResult(
            score=overall_score,
            bant_scores=bant_scores,
            recommendation=recommendation,
            objections=objections,
            next_action=next_action,
        )

    def score_motivation(self, transcript: str) -> int:
        """
        Scores lead motivation from 0-10 based on conversation transcript.

        Higher = more motivated to act soon.
        """
        score = 5  # Default neutral

        # Keywords indicating high motivation
        high_motivation_keywords = [
            r"\bvery\b.*\b(interested|motivated|urgent)",
            r"\bneed.*\b(asap|now|today|this week)",
            r"\blooking.*\b(immediately|quickly)",
            r"\bready.*\b(to|buy|sell)",
            r"\bcan't\b.*\b(wait|hold off)",
            r"\btime.*\b(sensitive|critical|urgent)",
        ]

        # Keywords indicating low motivation
        low_motivation_keywords = [
            r"\bjust\b.*\b(browsing|looking around)",
            r"\bmaybe\b",
            r"\bnot\b.*\b(sure|ready|convinced)",
            r"\bwill\b.*\b(think about|consider later)",
            r"\bno\b.*\b(rush|hurry)",
        ]

        transcript_lower = transcript.lower()

        for pattern in high_motivation_keywords:
            if re.search(pattern, transcript_lower):
                score = min(10, score + 2)

        for pattern in low_motivation_keywords:
            if re.search(pattern, transcript_lower):
                score = max(0, score - 2)

        return score

    def extract_contact_info(self, text: str) -> dict[str, str]:
        """
        Extracts name, phone, email from unstructured text.

        Returns dict with keys: name, phone, email (empty strings if not found).
        """
        result = {"name": "", "phone": "", "email": ""}

        # Email extraction
        email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        email_match = re.search(email_pattern, text)
        if email_match:
            result["email"] = email_match.group(0)

        # Phone extraction (various formats)
        phone_pattern = r"(?:\+1|1)?[-.\s]?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})"
        phone_match = re.search(phone_pattern, text)
        if phone_match:
            # Format as E.164
            result["phone"] = f"+1{phone_match.group(1)}{phone_match.group(2)}{phone_match.group(3)}"

        # Name extraction (simple heuristic: capitalized words at start or after greeting)
        name_pattern = r"(?:i'm|i am|my name is|this is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)"
        name_match = re.search(name_pattern, text)
        if name_match:
            result["name"] = name_match.group(1)

        return result

    def classify_lead_type(self, transcript: str) -> str:
        """
        Classifies lead as: buyer, seller, investor, or unknown.

        Returns the classification string.
        """
        transcript_lower = transcript.lower()

        buyer_keywords = ["buy", "purchase", "looking for", "interested in home", "mortgage"]
        seller_keywords = ["sell", "list", "selling my", "market my home", "sale"]
        investor_keywords = ["invest", "flip", "rental", "roi", "property investment"]

        buyer_score = sum(1 for kw in buyer_keywords if kw in transcript_lower)
        seller_score = sum(1 for kw in seller_keywords if kw in transcript_lower)
        investor_score = sum(1 for kw in investor_keywords if kw in transcript_lower)

        if buyer_score > seller_score and buyer_score > investor_score:
            return "buyer"
        elif seller_score > buyer_score and seller_score > investor_score:
            return "seller"
        elif investor_score > 0:
            return "investor"
        return "unknown"

    def generate_qualification_summary(
        self,
        lead_id: str,
        owner_id: str,
    ) -> str:
        """
        Generates a human-readable SMS-friendly qualification summary.

        Example: "Lead #123 qualified: 7/10 (need=9, timeline=8). Strong buyer. Book call."
        """
        # This is a simplified template; in production you'd fetch actual lead data
        return f"Lead {lead_id}: Qualified. Ready to proceed. Review in dashboard."

    def _fallback_qualification(
        self,
        transcript: str,
        property_details: dict[str, Any],
    ) -> QualificationResult:
        """
        Fallback keyword-based BANT scoring when Claude is unavailable.
        """
        transcript_lower = transcript.lower()

        # Budget: look for price mentions, affordability language
        budget_score = 5
        if any(kw in transcript_lower for kw in ["budget", "afford", "price range", "how much"]):
            budget_score = 7
        if any(kw in transcript_lower for kw in ["too expensive", "can't afford", "out of budget"]):
            budget_score = 3

        # Authority: look for decision-maker language
        authority_score = 5
        if any(kw in transcript_lower for kw in ["i decide", "my spouse and i", "with my family"]):
            authority_score = 8
        if any(kw in transcript_lower for kw in ["have to ask", "need to talk to", "my partner"]):
            authority_score = 4

        # Need: look for pain points and urgency
        need_score = 5
        if any(kw in transcript_lower for kw in ["need", "must", "require", "problem", "issue"]):
            need_score = 7
        if any(kw in transcript_lower for kw in ["just browsing", "no rush", "thinking about it"]):
            need_score = 3

        # Timeline: look for time-sensitive language
        timeline_score = 5
        if any(kw in transcript_lower for kw in ["asap", "this week", "urgent", "immediately", "soon"]):
            timeline_score = 8
        if any(kw in transcript_lower for kw in ["eventually", "maybe later", "not sure yet"]):
            timeline_score = 3

        overall_score = (budget_score + authority_score + need_score + timeline_score) // 4

        objections = []
        if "price" in transcript_lower or "expensive" in transcript_lower:
            objections.append("price")
        if "timing" in transcript_lower or "later" in transcript_lower:
            objections.append("timing")
        if "not interested" in transcript_lower:
            objections.append("not_interested")
        if "already with" in transcript_lower or "another agent" in transcript_lower:
            objections.append("already_working_with_agent")

        recommendation = "Strong prospect" if overall_score >= 7 else "Follow up" if overall_score >= 4 else "Not qualified"
        next_action = "Book appointment" if overall_score >= 7 else "Send details" if overall_score >= 4 else "Follow up in 1 week"

        return QualificationResult(
            score=overall_score,
            bant_scores={
                "budget": budget_score,
                "authority": authority_score,
                "need": need_score,
                "timeline": timeline_score,
            },
            recommendation=recommendation,
            objections=objections,
            next_action=next_action,
        )
