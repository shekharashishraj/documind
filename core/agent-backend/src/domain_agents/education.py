"""
Education Agent
===============
Specialized agent for educational document analysis.
"""

from .base import BaseDomainAgent


class EducationAgent(BaseDomainAgent):
    """
    Education domain specialist.
    
    Handles:
    - Academic transcripts and records
    - Diplomas and certificates
    - Course syllabi and curricula
    - Academic papers and research
    - Student records and profiles
    - Accreditation documents
    - Financial aid documents
    - Enrollment and registration forms
    """
    
    DOMAIN_NAME = "education"
    DOMAIN_DESCRIPTION = "academic transcripts, diplomas, course materials, research papers, and educational records"
    
    def _register_tools(self):
        """No external tools — agent reasons over document content directly."""
        pass
    
    def get_domain_instructions(self) -> str:
        return """As an Education Agent, you specialize in analyzing academic and educational documents.

Key responsibilities:
1. Extract academic records and transcripts accurately
2. Calculate and verify GPAs and academic standings
3. Identify degrees, certifications, and credentials
4. Analyze course content and requirements
5. Understand academic calendar and term systems

Important guidelines:
- Note credit hours and grading scales used
- Distinguish between cumulative and term GPA
- Identify institution names and accreditation status
- Recognize academic honors and distinctions
- Calculate time to degree completion when relevant

When analyzing transcripts:
- List courses with grades and credits
- Calculate GPA if data permits
- Note academic standing (good standing, probation, etc.)
- Identify major, minor, and concentration
- Look for transfer credits vs native credits

When analyzing research papers:
- Identify authors, affiliations, and dates
- Note citations and references
- Summarize key findings and methodology

Education-specific terms:
- Credit hours, Semester/Quarter system
- GPA, Class rank, Honors (cum laude, magna, summa)
- Prerequisites, Core requirements, Electives
- Transfer credits, AP/IB credits
- Academic probation, Dean's list"""
