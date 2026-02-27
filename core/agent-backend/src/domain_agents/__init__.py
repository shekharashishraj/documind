"""
Domain Agents Package
=====================
Specialized worker agents for different business domains.
"""

from .base import BaseDomainAgent, AgentResult, ToolCall
from .healthcare import HealthcareAgent
from .finance import FinanceAgent
from .hr import HRAgent
from .insurance import InsuranceAgent
from .education import EducationAgent
from .political import PoliticalAgent

__all__ = [
    "BaseDomainAgent",
    "AgentResult", 
    "ToolCall",
    "HealthcareAgent",
    "FinanceAgent",
    "HRAgent",
    "InsuranceAgent",
    "EducationAgent",
    "PoliticalAgent"
]
