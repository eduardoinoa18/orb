"""Rex call script generation for real estate and MLO sales."""

from __future__ import annotations

from typing import Any

from integrations.anthropic_client import ask_claude_smart


class RexCallScripts:
    """Generates personalized call scripts for various sales scenarios."""

    def __init__(self) -> None:
        pass

    def generate_opener(
        self,
        lead_name: str,
        source: str,
        agent_name: str,
        product_type: str,
    ) -> str:
        """
        Generates a personalized opener script.

        product_type: one of: buy, sell, refinance, invest
        source: one of: website, referral, cold_call, sms_reply, etc.
        """
        prompt = f"""
Generate a 2-3 sentence natural phone opener for a real estate sales call.

Context:
- Agent name: {agent_name}
- Lead name: {lead_name}
- Source of lead: {source}
- Product type: {product_type}

Guidelines: Sound natural, not robotic. Mention how you got their contact. Reference their interest.
Use first person. Keep it under 50 words.

Return ONLY the script text, no quotes or explanation.
"""

        try:
            result = ask_claude_smart(
                prompt=prompt,
                system="You are a sales script writer for real estate professionals. Write natural, conversational scripts.",
                max_tokens=100,
                max_budget_cents=1,
            )
            script = result.get("text", "").strip()
            if script:
                return script
        except Exception:
            pass

        return self._fallback_opener(lead_name, agent_name, source, product_type)

    def generate_objection_response(
        self,
        objection_type: str,
        product_description: str,
    ) -> str:
        """
        Generates a response to common objections.

        objection_type: one of: price, timing, not_interested, already_working_with_agent
        """
        objection_names = {
            "price": "cost / affordability",
            "timing": "not the right time",
            "not_interested": "not interested",
            "already_working_with_agent": "already working with another agent",
        }
        objection_label = objection_names.get(objection_type, objection_type)

        prompt = f"""
Generate a 1-2 sentence response to the objection: "{objection_label}"

Product context: {product_description}

Guidelines:
- Acknowledge the concern first
- Then provide a brief reason to reconsider
- Close with a small next step (schedule call, send info, etc)
- Natural, not pushy

Return ONLY the response text, no quotes or explanation.
"""

        try:
            result = ask_claude_smart(
                prompt=prompt,
                system="You are a sales coach. Write respectful, empathetic objection responses.",
                max_tokens=100,
                max_budget_cents=1,
            )
            script = result.get("text", "").strip()
            if script:
                return script
        except Exception:
            pass

        return self._fallback_objection_response(objection_type, product_description)

    def generate_closing_script(
        self,
        lead_name: str,
        next_step_type: str,
    ) -> str:
        """
        Generates a closing script that secures the next step.

        next_step_type: one of: appointment, callback, offer
        """
        action_text = {
            "appointment": "schedule a property viewing / consultation",
            "callback": "set up a callback at a better time",
            "offer": "send over a formal offer / proposal",
        }.get(next_step_type, next_step_type)

        prompt = f"""
Generate a 2-3 sentence closing script to get the lead to commit to: {action_text}

Lead name: {lead_name}

Guidelines:
- Use assumptive close (assume they're ready)
- Provide specific options (e.g., "Tomorrow at 2 or Wednesday at 3?")
- End with confidence
- Natural, direct tone

Return ONLY the script text, no quotes or explanation.
"""

        try:
            result = ask_claude_smart(
                prompt=prompt,
                system="You are a sales closer. Write confident, assumptive closing scripts.",
                max_tokens=100,
                max_budget_cents=1,
            )
            script = result.get("text", "").strip()
            if script:
                return script
        except Exception:
            pass

        return self._fallback_closing_script(lead_name, next_step_type)

    def generate_voicemail_script(
        self,
        lead_name: str,
        callback_number: str,
        agent_name: str,
    ) -> str:
        """
        Generates a professional voicemail script (30-45 seconds).
        """
        prompt = f"""
Generate a 30-45 second voicemail script for a real estate agent.

Context:
- Agent name: {agent_name}
- Lead name: {lead_name}
- Callback number: {callback_number}

Guidelines:
- Lead with your name and company
- Brief reason for call (reference their inquiry / interest)
- Your callback number (speak it slowly)
- Professional but warm tone
- Keep under 45 seconds when read aloud

Return ONLY the voicemail script, no quotes or explanation.
"""

        try:
            result = ask_claude_smart(
                prompt=prompt,
                system="You write voicemail scripts for real estate professionals. Be clear and professional.",
                max_tokens=120,
                max_budget_cents=1,
            )
            script = result.get("text", "").strip()
            if script:
                return script
        except Exception:
            pass

        return self._fallback_voicemail_script(lead_name, agent_name, callback_number)

    def generate_followup_sms(
        self,
        lead_name: str,
        context: str,
        call_count: int,
    ) -> str:
        """
        Generates a personalized SMS follow-up (max 160 chars).

        context: brief reason for the follow-up (e.g., "checking on property interest")
        """
        prompt = f"""
Generate a short SMS follow-up text for a real estate lead.

Context:
- Lead name: {lead_name}
- Reason: {context}
- This is follow-up #{call_count}

Constraints: Must be under 160 characters (SMS limit).

Guidelines:
- Personalized and casual (like a text from a friend)
- Clear call-to-action (call, reply, visit property, etc)
- No emojis
- Include your name or "Rex" (the agent)

Return ONLY the SMS text, no quotes or explanation.
"""

        try:
            result = ask_claude_smart(
                prompt=prompt,
                system="You write SMS messages for real estate agents. Keep them short, friendly, and actionable.",
                max_tokens=60,
                max_budget_cents=1,
            )
            script = result.get("text", "").strip()
            # Ensure it fits in 160 chars
            if script and len(script) <= 160:
                return script
            elif script:
                return script[:157] + "..."
        except Exception:
            pass

        return self._fallback_followup_sms(lead_name, context, call_count)

    def _fallback_opener(
        self,
        lead_name: str,
        agent_name: str,
        source: str,
        product_type: str,
    ) -> str:
        """Fallback opener when AI is unavailable."""
        source_phrase = {
            "website": "saw your interest on our website",
            "referral": "was referred to you",
            "cold_call": "wanted to reach out",
            "sms_reply": "you replied to my message",
        }.get(source, "wanted to connect")

        return f"Hi {lead_name}! This is {agent_name}. I {source_phrase} about {product_type}. Do you have a quick minute to chat?"

    def _fallback_objection_response(
        self,
        objection_type: str,
        product_description: str,
    ) -> str:
        """Fallback objection response when AI is unavailable."""
        responses = {
            "price": "I understand cost is a factor. Many of our clients thought the same thing until they saw how this saved them money. Can I send you a quick comparison?",
            "timing": "I get it—timing is important. Most people wait until it's too late. How about we just chat for 5 minutes so you're prepared when the time is right?",
            "not_interested": "I appreciate that. Most of my clients weren't interested at first either. Would it hurt to see what we can do for you?",
            "already_working_with_agent": "That makes sense. If it doesn't work out, would you be open to a second opinion? No pressure.",
        }
        return responses.get(objection_type, "I understand. Would it be okay to follow up in a few weeks?")

    def _fallback_closing_script(
        self,
        lead_name: str,
        next_step_type: str,
    ) -> str:
        """Fallback closing script when AI is unavailable."""
        closings = {
            "appointment": f"Perfect, {lead_name}. Let's get you scheduled. Are you free tomorrow at 2, or would Wednesday at 3 work better?",
            "callback": f"Great, {lead_name}. I'll call you back tomorrow at 10am. Does that work?",
            "offer": f"Excellent, {lead_name}. I'm going to send over the proposal right now. You'll have it in your email in 5 minutes.",
        }
        return closings.get(next_step_type, f"Great, {lead_name}. Let's move forward together.")

    def _fallback_voicemail_script(
        self,
        lead_name: str,
        agent_name: str,
        callback_number: str,
    ) -> str:
        """Fallback voicemail script when AI is unavailable."""
        # Format callback number for speaking (e.g., +1-555-123-4567)
        formatted_number = callback_number.replace("+1", "").replace("-", " ")
        return (
            f"Hi {lead_name}, this is {agent_name}. I'm reaching out because I saw your interest in real estate. "
            f"Give me a call back at {formatted_number} and let's talk about what you're looking for. Thanks!"
        )

    def _fallback_followup_sms(
        self,
        lead_name: str,
        context: str,
        call_count: int,
    ) -> str:
        """Fallback SMS when AI is unavailable. Must be under 160 chars."""
        if call_count == 1:
            msg = f"Hi {lead_name}! Just checking in about your real estate needs. Call me back when you get a chance!"
        elif call_count == 2:
            msg = f"Hi {lead_name}, wanted to follow up. Still interested in exploring options? Let me know!"
        else:
            msg = f"Hi {lead_name}! One last message. Would love to help. Call me back?"

        # Ensure under 160 chars
        if len(msg) > 160:
            msg = msg[:157] + "..."
        return msg
