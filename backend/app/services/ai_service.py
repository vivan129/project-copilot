"""
AI service — Anthropic Claude claude-opus-4-8 with adaptive thinking + RAG-augmented prompting.
Generates complete, accurate, hallucination-resistant project blueprints.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, AsyncIterator

import anthropic

from app.config import settings
from app.services.rag_service import rag_service

logger = logging.getLogger(__name__)


# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are Project Copilot — the world's smartest robotics and electronics project assistant for students aged 10–18.

Your mission: transform a parts list + goal into a COMPLETE, REAL, WORKING project blueprint that a student can actually build.

## ABSOLUTE RULES — violating any of these is a failure
1. **Parts**: ONLY use components the student listed. NEVER invent, suggest, or imply additional parts. If they listed 3 parts, design a project around those 3 parts.
2. **Code**: ALL code must be 100% real, syntactically correct, and copy-paste ready. Test the logic mentally before writing. No pseudocode, no placeholders like `// your code here`.
3. **Pin consistency**: Every pin number must be IDENTICAL across the code, wiring table, and build steps. If pin 9 is TRIG in code, it must say pin 9 in wiring too.
4. **Prices**: Use realistic local prices. INR: Arduino Uno ≈ ₹500, HC-SR04 ≈ ₹80, servo ≈ ₹120. USD: divide INR by 85.
5. **Safety**: Never suggest mains voltage (120V/230V) connections for beginners. Add safety warnings for any step involving heat, high current, or sharp tools.
6. **Difficulty honesty**: 1 = complete beginner (first project ever), 5 = built 3-4 projects, 10 = advanced maker who can design PCBs. Be accurate.
7. **Encouragement**: Use emoji in titles and phase names. Make it exciting but technically accurate. Kids learn better when they're excited.
8. **JSON only**: Your ENTIRE response must be valid JSON with no text before or after. No markdown fences. No explanations outside the JSON.

## SKILL LEVEL CALIBRATION
- **beginner**: Short, simple code (under 80 lines). Explain every step. Avoid soldering. Use breadboards. No libraries beyond built-ins.
- **intermediate**: Can use popular libraries (Servo.h, Wire.h, LiquidCrystal). Moderate code length (80–200 lines). Can solder.
- **advanced**: Complex projects. Multiple libraries OK. State machines, interrupts, I2C/SPI protocols. Long code is fine.

## CODE QUALITY STANDARDS
- Include all necessary `#include` statements
- Define all pin constants at the top with `#define` or `const int`
- Add `Serial.begin(9600)` in setup() for debugging
- Add meaningful `Serial.println()` messages so students can debug
- Handle edge cases (sensor out-of-range, motor stall, etc.)
- For Python/MicroPython: include proper imports and main loop
- NEVER use `analogWrite()` on pins that don't support PWM (only 3,5,6,9,10,11 on Arduino Uno)
- NEVER exceed 5V/40mA per Arduino pin — always mention if an external power source is needed

## WIRING STANDARDS
- Use real, color-coded wires (red=VCC/power, black=GND, yellow/green/blue=signal)
- Always list BOTH ends of every connection with exact pin names
- Include pull-up/pull-down resistors when required (buttons, I2C sensors)
- Explicitly state if a component needs 3.3V vs 5V

## BLUEPRINT JSON SCHEMA — return EXACTLY this structure:
{
  "title": "🤖 Descriptive project name with emoji",
  "emoji": "🤖",
  "tagline": "One punchy sentence about what the project does and why it's cool",
  "difficulty": 4,
  "estimated_hours": 8,
  "wow_factor": "3-4 sentences: what impressive things this project can do, why judges/friends will love it, real-world applications",
  "parts": [
    {
      "name": "Exact component name",
      "quantity": 1,
      "purpose": "Specific role of this component in this project",
      "price_estimate": "₹500 / $6",
      "where_to_buy": "Amazon / Robocraze / local electronics shop"
    }
  ],
  "wiring": {
    "description": "2-3 sentence overview of the wiring approach — what connects to what and why",
    "connections": [
      {"from": "Arduino Pin 9", "to": "HC-SR04 TRIG", "wire_color": "yellow"},
      {"from": "Arduino Pin 10", "to": "HC-SR04 ECHO", "wire_color": "green"},
      {"from": "Arduino 5V", "to": "HC-SR04 VCC", "wire_color": "red"},
      {"from": "Arduino GND", "to": "HC-SR04 GND", "wire_color": "black"}
    ],
    "safety_notes": "Always disconnect power before changing wiring. Check polarities before powering on."
  },
  "code": {
    "language": "Arduino C++",
    "filename": "project_name.ino",
    "full_code": "// COMPLETE working code here — no placeholders\\n#include <...>\\n\\n#define TRIG_PIN 9\\n...",
    "explanation": "Section-by-section explanation: what each part of the code does in plain English"
  },
  "build_phases": [
    {
      "phase_number": 1,
      "phase_name": "Assemble the circuit",
      "emoji": "🔌",
      "duration_minutes": 30,
      "steps": [
        "Place the Arduino Uno on your breadboard",
        "Connect the red wire from Arduino 5V to the breadboard's positive rail",
        "Connect the black wire from Arduino GND to the breadboard's negative rail"
      ]
    }
  ],
  "testing": {
    "how_to_test": "Step-by-step test procedure starting from the most basic check",
    "expected_output": "Exactly what the student should see, hear, or measure when it works",
    "troubleshooting": [
      {"problem": "Motor not spinning", "solution": "Check L298N power connections — it needs a separate 9V supply, not just the Arduino 5V"},
      {"problem": "Sensor reading always 0", "solution": "Verify TRIG and ECHO are not swapped. Test with Serial Monitor to see raw values"}
    ]
  },
  "science_fair_tips": "Concrete tips on presenting at a science fair: what to put on the poster, what demo to prepare, what questions judges ask, how to explain the science behind it",
  "next_level_upgrades": [
    "Add Bluetooth module (HC-05) for smartphone control",
    "Add OLED display to show real-time sensor readings",
    "Add data logging to SD card for graphs"
  ],
  "common_mistakes": [
    "Connecting sensor backwards (VCC↔GND swapped) — will burn the component",
    "Using analogWrite() on a non-PWM pin — only pins 3,5,6,9,10,11 support PWM on Arduino Uno"
  ],
  "presentation_script": "A complete 2-minute script the student reads aloud: intro, how it works, demo instructions, what they learned, future plans"
}"""

# ── Few-shot example to anchor Claude's format ────────────────────────────────
FEW_SHOT_EXAMPLE = """
EXAMPLE INPUT:
Category: robotics
Parts: Arduino Uno, HC-SR04, buzzer
Budget: INR 800, Skill: beginner, Goal: obstacle detector that beeps when something is close

EXAMPLE OUTPUT (abbreviated — real output has full code):
{
  "title": "🔊 Ultrasonic Obstacle Alarm",
  "emoji": "🔊",
  "tagline": "Beeps faster and louder the closer an obstacle gets — like a car parking sensor!",
  "difficulty": 3,
  "estimated_hours": 4,
  ...
}
"""


class AIService:
    def __init__(self):
        self._client: anthropic.AsyncAnthropic | None = None

    def _get_client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            if not settings.ANTHROPIC_API_KEY:
                raise ValueError(
                    "ANTHROPIC_API_KEY is not configured. "
                    "Add it to your .env file: ANTHROPIC_API_KEY=sk-ant-..."
                )
            self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        return self._client

    def _build_user_prompt(self, input_data: dict, rag_context: str) -> str:
        category     = input_data.get("category", "electronics")
        components   = input_data.get("components", [])
        budget       = input_data.get("budget", 500)
        currency     = input_data.get("currency", "INR")
        skill_level  = input_data.get("skill_level", "beginner")
        time_available = input_data.get("time_available", "weekend")
        goal         = input_data.get("goal", "Build something cool")
        has_3d       = input_data.get("has_3d_printer", False)
        can_solder   = input_data.get("can_solder", False)

        components_str = "\n".join(f"  - {c}" for c in components) if components else "  - Basic electronics kit"

        # Skill calibration hint
        skill_hints = {
            "beginner": "Very detailed explanations. Simple code under 80 lines. No soldering required.",
            "intermediate": "Moderate detail. Can use popular libraries. Soldering OK.",
            "advanced": "Concise steps. Complex code OK. Advanced protocols (I2C, SPI, interrupts) welcome.",
        }
        skill_hint = skill_hints.get(skill_level, skill_hints["beginner"])

        # Budget calibration
        budget_note = ""
        if currency == "INR":
            if budget < 500:
                budget_note = "VERY tight budget — minimize parts, use only what's listed, no extra components."
            elif budget < 1500:
                budget_note = "Medium budget — can suggest 1-2 cheap additions (<₹100 each) if truly necessary."
            else:
                budget_note = "Comfortable budget — full-featured project OK."
        else:
            if budget < 10:
                budget_note = "VERY tight budget — use only listed parts."
            elif budget < 30:
                budget_note = "Medium budget."
            else:
                budget_note = "Comfortable budget."

        return f"""Generate a complete project blueprint for this student:

## Student Profile
- **Category**: {category}
- **Skill level**: {skill_level} ({skill_hint})
- **Time available**: {time_available}
- **Has 3D printer**: {has_3d}
- **Can solder**: {can_solder}

## Parts They Own (ONLY use these — no additions)
{components_str}

## Budget
- Amount: {currency} {budget}
- Note: {budget_note}

## Their Goal
{goal}

## Relevant Component Reference (from knowledge base)
{rag_context}

---

IMPORTANT REMINDERS:
1. Only use the parts listed above — do NOT add components they didn't mention
2. Make ALL code complete and working — no placeholders
3. Pin numbers must match exactly across code, wiring, and build steps
4. Calibrate difficulty and explanation depth for a {skill_level} student

Generate the complete blueprint JSON now:"""

    async def generate_blueprint_stream(
        self, input_data: dict
    ) -> AsyncIterator[tuple[str, Any]]:
        """
        Stream blueprint generation with live progress updates.
        Yields ("progress", dict) and ("blueprint", dict) tuples.
        """
        client = self._get_client()

        # Step 1: RAG retrieval
        yield ("progress", {"step": "🔍 Searching component knowledge base...", "pct": 10})
        try:
            rag_context = rag_service.get_context_for_project(input_data)
        except Exception as e:
            logger.warning("RAG retrieval failed (non-fatal): %s", e)
            rag_context = "No additional context available."

        yield ("progress", {"step": "🧠 Claude is thinking about your project...", "pct": 25})
        user_prompt = self._build_user_prompt(input_data, rag_context)

        yield ("progress", {"step": "✨ Generating your complete blueprint...", "pct": 40})

        collected_text = ""
        last_pct = 40

        try:
            async with client.messages.stream(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": FEW_SHOT_EXAMPLE},
                    {"role": "assistant", "content": "Understood. I will generate the exact JSON schema you showed, with complete working code and no placeholders."},
                    {"role": "user", "content": user_prompt},
                ],
            ) as stream:
                async for text in stream.text_stream:
                    collected_text += text
                    # Simulate progress based on token count
                    approx_pct = min(40 + int(len(collected_text) / 100), 80)
                    if approx_pct > last_pct + 5:
                        last_pct = approx_pct
                        step_msg = (
                            "💻 Writing your code..." if approx_pct < 55
                            else "🔌 Planning wiring connections..." if approx_pct < 68
                            else "📋 Building step-by-step guide..."
                        )
                        yield ("progress", {"step": step_msg, "pct": approx_pct})

        except anthropic.AuthenticationError:
            logger.error("Anthropic API key is invalid or missing")
            yield ("error", "Invalid API key. Please check your ANTHROPIC_API_KEY in .env")
            return
        except anthropic.RateLimitError:
            logger.warning("Rate limited — retrying in a moment")
            yield ("progress", {"step": "⏳ Rate limited — retrying...", "pct": last_pct})
            # Brief wait then retry
            import asyncio
            await asyncio.sleep(10)
            try:
                async with client.messages.stream(
                    model=settings.ANTHROPIC_MODEL,
                    max_tokens=16000,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}],
                ) as stream2:
                    async for text in stream2.text_stream:
                        collected_text += text
            except Exception as e2:
                logger.error("Retry failed: %s", e2)
                yield ("error", f"Rate limited. Please try again in a minute.")
                return
        except anthropic.APIError as e:
            logger.error("Anthropic API error: %s", e)
            yield ("error", f"AI service error: {str(e)}")
            return

        yield ("progress", {"step": "🔧 Validating blueprint...", "pct": 85})

        # Parse JSON
        try:
            blueprint = self._parse_blueprint_json(collected_text)
        except Exception as e:
            logger.error("Blueprint parse failed: %s\nFirst 500 chars: %.500s", e, collected_text)
            # Try a recovery extraction
            try:
                blueprint = self._aggressive_json_extract(collected_text)
            except Exception:
                yield ("error", "Failed to parse blueprint. Please try again.")
                return

        # Post-process: ensure required fields
        blueprint = self._enrich_blueprint(blueprint, input_data)

        yield ("progress", {"step": "🎉 Your blueprint is ready!", "pct": 100})
        yield ("blueprint", blueprint)

    async def generate_blueprint(self, input_data: dict) -> dict:
        """Non-streaming generation — returns the complete blueprint dict."""
        client = self._get_client()
        try:
            rag_context = rag_service.get_context_for_project(input_data)
        except Exception:
            rag_context = ""
        user_prompt = self._build_user_prompt(input_data, rag_context)

        try:
            message = await client.messages.create(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=16000,
                # No thinking — we need ALL tokens for the JSON output, not internal reasoning
                system=SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": FEW_SHOT_EXAMPLE},
                    {"role": "assistant", "content": "Understood. I will generate the exact JSON schema you showed, with complete working code and no placeholders."},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except anthropic.AuthenticationError:
            raise ValueError("Invalid ANTHROPIC_API_KEY. Check your .env file.")
        except anthropic.RateLimitError:
            # One retry after a short wait
            import asyncio
            await asyncio.sleep(15)
            message = await client.messages.create(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )

        raw = "".join(block.text for block in message.content if block.type == "text")
        blueprint = self._parse_blueprint_json(raw)
        return self._enrich_blueprint(blueprint, input_data)

    def _parse_blueprint_json(self, raw: str) -> dict:
        """Robustly extract and parse the JSON blueprint from Claude's response."""
        text = raw.strip()

        # Strip markdown fences
        if "```" in text:
            text = re.sub(r"```(?:json)?\s*", "", text)
            text = text.strip()

        # Find first { and matching }
        start = text.find("{")
        if start == -1:
            raise ValueError(f"No JSON object found. Response starts with: {text[:200]!r}")

        depth = 0
        end = start
        for i, ch in enumerate(text[start:], start=start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        else:
            # JSON was truncated — try to close it by appending closing braces
            logger.warning("JSON truncated — attempting auto-close repair (depth=%d)", depth)
            truncated = text[start:]
            repaired = truncated + "}" * depth
            try:
                blueprint = json.loads(repaired)
                return self._enrich_blueprint(blueprint, {}) if not blueprint.get("title") else blueprint
            except Exception:
                raise ValueError("JSON object is not closed and could not be repaired")

        blueprint = json.loads(text[start:end])

        # Validate minimum required fields
        required = ["title", "parts", "wiring", "code", "build_phases"]
        missing = [f for f in required if f not in blueprint]
        if missing:
            raise ValueError(f"Blueprint missing required fields: {missing}")

        return blueprint

    def _aggressive_json_extract(self, raw: str) -> dict:
        """
        Last-resort extraction — tries to find any valid JSON object
        in the response, even if the response is partially malformed.
        """
        # Try jsonl repair pattern: find all {...} blocks and pick the largest
        candidates = []
        i = 0
        while i < len(raw):
            if raw[i] == "{":
                depth, end = 1, i + 1
                while end < len(raw) and depth > 0:
                    if raw[end] == "{":
                        depth += 1
                    elif raw[end] == "}":
                        depth -= 1
                    end += 1
                if depth == 0:
                    try:
                        obj = json.loads(raw[i:end])
                        candidates.append((len(raw[i:end]), obj))
                    except Exception:
                        pass
            i += 1

        if not candidates:
            raise ValueError("No valid JSON found")

        # Return the largest valid JSON object found
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    def _enrich_blueprint(self, bp: dict, input_data: dict) -> dict:
        """
        Post-process the blueprint: fill in missing fields with sensible defaults
        and apply safety checks.
        """
        # Ensure emoji
        if "emoji" not in bp or not bp["emoji"]:
            bp["emoji"] = "🤖"

        # Ensure tagline
        if "tagline" not in bp or not bp["tagline"]:
            bp["tagline"] = bp.get("title", "A cool electronics project")[:80]

        # Clamp difficulty
        bp["difficulty"] = max(1, min(10, int(bp.get("difficulty", 5))))

        # Ensure estimated_hours is a number
        try:
            bp["estimated_hours"] = float(bp.get("estimated_hours", 8))
        except (TypeError, ValueError):
            bp["estimated_hours"] = 8.0

        # Ensure lists are lists
        for list_field in ["parts", "build_phases", "next_level_upgrades", "common_mistakes"]:
            if not isinstance(bp.get(list_field), list):
                bp[list_field] = []

        # Ensure wiring.connections is a list
        if isinstance(bp.get("wiring"), dict):
            if not isinstance(bp["wiring"].get("connections"), list):
                bp["wiring"]["connections"] = []

        # Ensure testing.troubleshooting is a list
        if isinstance(bp.get("testing"), dict):
            if not isinstance(bp["testing"].get("troubleshooting"), list):
                bp["testing"]["troubleshooting"] = []

        # Add skill level to wow_factor context if missing
        if not bp.get("wow_factor"):
            bp["wow_factor"] = "This project demonstrates core electronics principles in a fun, hands-on way!"

        # Add science fair tips if missing
        if not bp.get("science_fair_tips"):
            bp["science_fair_tips"] = "Prepare a poster with circuit diagram.\nRecord a video demo.\nExplain what problem your project solves."

        # Add presentation script if missing
        if not bp.get("presentation_script"):
            name = bp.get("title", "my project")
            goal = input_data.get("goal", "explore electronics")
            parts = input_data.get("components", [])
            bp["presentation_script"] = (
                f'Hi! My project is "{name}". '
                f"I built it to {goal[:100]}. "
                f"It uses {', '.join(parts[:3]) if parts else 'Arduino and sensors'}. "
                "Any questions?"
            )

        return bp


ai_service = AIService()
