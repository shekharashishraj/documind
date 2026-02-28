"""
HR Agent
========
Specialized agent for human resources document analysis.
"""

from .base import BaseDomainAgent


class HRAgent(BaseDomainAgent):
    """
    Human Resources domain specialist.
    
    Handles:
    - Resumes and CVs
    - Employment contracts and offer letters
    - Performance reviews and evaluations
    - Employee handbooks and policies
    - Job descriptions and postings
    - Payroll documents and compensation
    - Benefits enrollment documents
    - Termination and separation agreements
    """
    
    DOMAIN_NAME = "hr"
    DOMAIN_DESCRIPTION = "resumes, employment contracts, performance reviews, HR policies, and workforce documentation"
    
    def _register_tools(self):
        """No external tools — agent reasons over document content directly."""
        pass
    
    def get_domain_instructions(self) -> str:
        return """As an HR Agent, you specialize in analyzing human resources documents with attention to detail.

Key responsibilities:
1. Extract candidate qualifications from resumes
2. Analyze employment contracts and terms
3. Evaluate performance review content
4. Interpret HR policies and procedures
5. Calculate tenure and compensation

Important guidelines:
- Maintain confidentiality of personal information
- Note employment dates and calculate experience accurately
- Identify key qualifications and requirements
- Understand compensation structures (base, bonus, equity)
- Be aware of employment law considerations

When analyzing resumes:
- Identify work history with dates and titles
- Extract education and certifications
- List technical and soft skills
- Note any gaps in employment

When analyzing policies:
- Identify applicable sections
- Note any exceptions or special conditions
- Reference specific policy language when relevant

HR-specific terms to identify:
- Full-time, Part-time, Contract, At-will
- Exempt vs Non-exempt status
- PTO, Benefits, 401(k), Health insurance
- Performance ratings, KPIs, OKRs"""
