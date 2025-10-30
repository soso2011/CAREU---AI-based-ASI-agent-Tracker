"""
CAREU AI - Patient Intake Agent (Cloud Deployment)
Cloud-ready version with symptom extraction and NLP pattern matching.

DEPLOYMENT: Copy this entire file to Agentverse Build tab for CAREU Patient Intake agent.
"""

from datetime import datetime
from typing import List, Dict, Optional
import re

# Import uagents framework (available in Agentverse)
from uagents import Agent, Context, Protocol, Model

# ============================================================================
# AGENT ADDRESSES - Cloud Deployment Configuration
# ============================================================================

COORDINATOR_ADDRESS = "agent1qdp74ezv3eas5q60s4650xt97ew5kmyt9de77w2ku55jxys8uq2uk0u440d"

# ============================================================================
# MESSAGE MODELS (Inline - no external imports)
# ============================================================================

class Symptom(Model):
    """Patient symptom data"""
    name: str
    raw_text: str
    severity: Optional[int] = 5
    duration: Optional[str] = None


class PatientIntakeData(Model):
    """Structured patient intake data"""
    session_id: str
    symptoms: List[Symptom]
    age: Optional[int] = None
    timestamp: datetime
    medical_history: Optional[List[str]] = None
    allergies: Optional[List[str]] = None
    current_medications: Optional[List[str]] = None


class IntakeTextMessage(Model):
    """Message from coordinator/user with symptom text"""
    text: str
    session_id: str


class AgentAcknowledgement(Model):
    """Acknowledgement message back to coordinator"""
    session_id: str
    agent_name: str
    message: str


class DiagnosticRequest(Model):
    """Request for diagnostic analysis (sent to coordinator)"""
    session_id: str
    patient_data: PatientIntakeData
    requesting_agent: str
    analysis_type: str = "symptom_analysis"


# ============================================================================
# SYMPTOM EXTRACTION KEYWORDS
# ============================================================================

# Common symptom keywords (ordered from most specific to least specific)
SYMPTOM_KEYWORDS = {
    # Fever & Temperature
    "high-fever": ["high fever", "very high temperature", "burning up with fever"],
    "fever": ["fever", "high temperature", "temp", "hot"],
    "chills": ["chills", "shivering", "shaking", "cold"],

    # Head & Neurological
    "severe-headache": ["severe headache", "terrible headache", "worst headache", "intense headache"],
    "headache": ["headache", "head pain", "head hurts", "migraine", "head ache"],
    "dizziness": ["dizzy", "lightheaded", "vertigo", "spinning"],
    "confusion": ["confused", "disoriented", "foggy", "can't think"],

    # Neck symptoms
    "neck-stiffness": ["neck is very stiff", "neck is stiff", "very stiff neck", "extremely stiff neck"],
    "stiff-neck": ["stiff neck", "neck stiff", "can't move neck", "neck hurts to move"],

    # Respiratory
    "difficulty-breathing": ["difficulty breathing", "hard to breathe", "can't breathe well"],
    "shortness-of-breath": ["short of breath", "can't breathe", "breathless", "gasping"],
    "cough": ["cough", "coughing", "hacking"],
    "sore-throat": ["sore throat", "throat pain", "hurts to swallow"],

    # Gastrointestinal
    "nausea": ["nausea", "nauseous", "queasy", "sick to stomach"],
    "vomiting": ["vomiting", "throwing up", "vomit", "puking"],
    "diarrhea": ["diarrhea", "loose stool", "runny stool"],
    "abdominal-pain": ["stomach pain", "abdominal pain", "belly pain", "stomach ache"],

    # Muscular & Pain
    "chest-pain": ["chest pain", "chest hurts", "chest pressure"],
    "muscle-pain": ["muscle pain", "body aches", "sore muscles", "aching"],
    "joint-pain": ["joint pain", "joints hurt", "stiff joints"],

    # Skin
    "rash": ["rash", "skin rash", "spots", "bumps"],

    # Energy & Consciousness
    "fatigue": ["tired", "fatigue", "exhausted", "weakness", "weak"],
    "loss-of-consciousness": ["passed out", "fainted", "blacked out", "unconscious"],
}

# Severity indicators
SEVERITY_HIGH = ["severe", "extreme", "worst", "unbearable", "terrible", "intense"]
SEVERITY_MEDIUM = ["moderate", "significant", "bad", "strong"]
SEVERITY_LOW = ["mild", "slight", "little bit", "somewhat"]


# ============================================================================
# SYMPTOM EXTRACTION ENGINE
# ============================================================================

class SymptomExtractor:
    """Extracts and normalizes symptoms from natural language text"""

    @staticmethod
    def extract_symptoms(text: str) -> List[Symptom]:
        """
        Extract symptoms from user text

        Returns list of Symptom objects with normalized names
        """
        text_lower = text.lower()
        symptoms = []

        # Find matching symptoms
        for symptom_name, keywords in SYMPTOM_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    # Estimate severity based on descriptors
                    severity = SymptomExtractor._estimate_severity(text_lower)

                    # Extract duration if present
                    duration = SymptomExtractor._extract_duration(text_lower)

                    symptom = Symptom(
                        name=symptom_name,
                        raw_text=keyword,
                        severity=severity,
                        duration=duration,
                    )
                    symptoms.append(symptom)
                    break  # Only match once per symptom type

        return symptoms

    @staticmethod
    def _estimate_severity(text: str) -> int:
        """Estimate severity 1-10 based on descriptive words"""
        if any(word in text for word in SEVERITY_HIGH):
            return 8
        elif any(word in text for word in SEVERITY_MEDIUM):
            return 5
        elif any(word in text for word in SEVERITY_LOW):
            return 3
        else:
            return 5  # Default moderate

    @staticmethod
    def _extract_duration(text: str) -> Optional[str]:
        """Extract duration information from text"""
        # Pattern: "for X days/hours/weeks"
        duration_pattern = r'for\s+(\d+)\s+(day|days|hour|hours|week|weeks)'
        match = re.search(duration_pattern, text)
        if match:
            return f"{match.group(1)} {match.group(2)}"

        # Pattern: "X days/hours ago"
        ago_pattern = r'(\d+)\s+(day|days|hour|hours|week|weeks)\s+ago'
        match = re.search(ago_pattern, text)
        if match:
            return f"{match.group(1)} {match.group(2)}"

        # Check for keywords
        if "yesterday" in text:
            return "1 day"
        if "this morning" in text or "today" in text:
            return "hours"
        if "this week" in text:
            return "days"

        return None

    @staticmethod
    def extract_age(text: str) -> Optional[int]:
        """Extract age from text"""
        # Pattern: "I am X years old" or "X year old"
        age_pattern = r'(\d+)\s*(year|years|yr|yrs)\s*old'
        match = re.search(age_pattern, text.lower())
        if match:
            return int(match.group(1))
        return None


# ============================================================================
# SESSION TRACKING
# ============================================================================

# Session tracking for follow-up questions
session_context: Dict[str, Dict] = {}


def needs_clarification(symptoms: List[Symptom], age: Optional[int], text: str) -> Optional[str]:
    """
    Determine if clarification is needed and return appropriate question
    Returns None if all necessary data is present
    """
    if not symptoms:
        return ("I didn't detect any specific symptoms. Could you describe what you're experiencing?\n\n"
                "Examples:\n"
                "• 'I have a fever and headache'\n"
                "• 'My stomach hurts and I feel nauseous'\n"
                "• 'I'm having chest pain and shortness of breath'")

    # Check for critical symptoms without duration
    critical_symptoms = ["chest-pain", "shortness-of-breath", "confusion", "loss-of-consciousness"]
    critical_without_duration = [s for s in symptoms if s.name in critical_symptoms and not s.duration]

    if critical_without_duration:
        symptom_names = ', '.join([s.name.replace('_', ' ') for s in critical_without_duration])
        return (f"You mentioned {symptom_names}. This could be important.\n\n"
                f"How long have you been experiencing this? (e.g., '2 hours', '3 days')")

    # Check if age is missing for fever cases
    has_fever = any(s.name == "fever" for s in symptoms)
    if has_fever and not age:
        return ("I see you have a fever. Your age helps with accurate assessment.\n\n"
                "How old are you?")

    return None


# ============================================================================
# AGENT INITIALIZATION
# ============================================================================

agent = Agent()

# Create inter-agent protocol
inter_agent_proto = Protocol(name="PatientIntakeProtocol")


# ============================================================================
# MESSAGE HANDLERS
# ============================================================================

@inter_agent_proto.on_message(model=IntakeTextMessage)
async def handle_intake_message(ctx: Context, sender: str, msg: IntakeTextMessage):
    """
    Process incoming patient symptom descriptions
    Extract structured data and send to coordinator
    """
    ctx.logger.info(f"Received intake message from {sender}")
    ctx.logger.info(f"Session: {msg.session_id}")
    ctx.logger.info(f"Text: {msg.text}")

    # Track session context
    if msg.session_id not in session_context:
        session_context[msg.session_id] = {
            "messages": [],
            "clarification_count": 0
        }

    session_context[msg.session_id]["messages"].append(msg.text)
    session_context[msg.session_id]["clarification_count"] += 1

    # Extract symptoms from text
    symptoms = SymptomExtractor.extract_symptoms(msg.text)

    # Extract age if mentioned
    age = SymptomExtractor.extract_age(msg.text)

    # Check if we need clarification
    clarification = needs_clarification(symptoms, age, msg.text)

    # Limit clarification attempts to 2 to avoid endless loops
    max_clarifications = 2
    if clarification and session_context[msg.session_id]["clarification_count"] <= max_clarifications:
        ctx.logger.info(f"Requesting clarification for session {msg.session_id}")
        response = AgentAcknowledgement(
            session_id=msg.session_id,
            agent_name="patient_intake",
            message=clarification
        )
        await ctx.send(sender, response)
        return

    # If no symptoms after max clarifications, provide helpful message
    if not symptoms:
        ctx.logger.warning(f"No symptoms extracted after {max_clarifications} attempts")
        response = AgentAcknowledgement(
            session_id=msg.session_id,
            agent_name="patient_intake",
            message=("I'm having trouble identifying specific symptoms from your description. "
                    "For the most accurate assessment, please consult a healthcare provider directly.\n\n"
                    "If this is an emergency, please call emergency services immediately.")
        )
        await ctx.send(sender, response)
        return

    # Structure patient data with complete information
    patient_data = PatientIntakeData(
        session_id=msg.session_id,
        symptoms=symptoms,
        age=age,
        timestamp=datetime.utcnow()
    )

    ctx.logger.info(f"✅ Complete patient data extracted:")
    ctx.logger.info(f"   Symptoms: {[s.name for s in symptoms]}")
    ctx.logger.info(f"   Age: {age}")

    # Send structured acknowledgement
    symptom_list = ', '.join([s.name.replace('_', ' ').replace('-', ' ') for s in symptoms])

    ack_message = (
        f"✅ Information received:\n\n"
        f"Symptoms: {symptom_list}\n"
        f"{'Age: ' + str(age) if age else 'Age: Not provided'}\n\n"
        f"Analyzing your symptoms..."
    )

    ack = AgentAcknowledgement(
        session_id=msg.session_id,
        agent_name="patient_intake",
        message=ack_message
    )
    await ctx.send(sender, ack)

    # Create diagnostic request for coordinator
    diagnostic_request = DiagnosticRequest(
        session_id=msg.session_id,
        patient_data=patient_data,
        requesting_agent="patient_intake",
        analysis_type="symptom_analysis"
    )

    ctx.logger.info(f"📤 Sending diagnostic request to coordinator: {COORDINATOR_ADDRESS}")
    await ctx.send(COORDINATOR_ADDRESS, diagnostic_request)


# ============================================================================
# STARTUP & INITIALIZATION
# ============================================================================

@agent.on_event("startup")
async def startup(ctx: Context):
    """Initialize patient intake agent"""
    ctx.logger.info("=" * 60)
    ctx.logger.info("CAREU AI - Patient Intake Agent (Cloud)")
    ctx.logger.info("=" * 60)
    ctx.logger.info(f"Agent address: {agent.address}")
    ctx.logger.info(f"Ready to extract patient symptoms")
    ctx.logger.info("=" * 60)


# Include the inter-agent protocol
agent.include(inter_agent_proto)
