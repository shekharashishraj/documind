"""
Healthcare Agent
================
Specialized agent for medical and healthcare document analysis.
"""

from .base import BaseDomainAgent


class HealthcareAgent(BaseDomainAgent):
    """
    Healthcare domain specialist.
    
    Handles:
    - Medical records and clinical notes
    - Prescriptions and medication lists
    - Lab results and diagnostic reports
    - Medical bills and claims
    - Health insurance documents
    - Treatment plans and discharge summaries
    """
    
    DOMAIN_NAME = "healthcare"
    DOMAIN_DESCRIPTION = "medical records, clinical documentation, prescriptions, lab results, and healthcare billing"
    
    def _register_tools(self):
        """No external tools — agent reasons over document content directly."""
        pass
    
    def get_domain_instructions(self) -> str:
        return """As a Healthcare Agent, you specialize in analyzing medical documents with precision and care.

Key responsibilities:
1. Extract and interpret medical data accurately
2. Identify diagnoses, treatments, medications, and procedures
3. Parse lab results and vital signs with proper units
4. Understand medical terminology and abbreviations
5. Handle sensitive health information appropriately

Important guidelines:
- Always note units for measurements (mg, mL, mmHg, etc.)
- Distinguish between patient-reported and clinically verified information
- Flag any critical or abnormal values
- Maintain awareness of HIPAA considerations
- Cross-reference medication names with dosages

When analyzing:
- Look for ICD codes, CPT codes, or diagnosis codes
- Identify healthcare providers and facilities mentioned
- Note dates of service, admissions, or procedures
- Extract insurance and billing information if present"""
