"""
Political Agent
===============
Specialized agent for political and government document analysis.
"""

from .base import BaseDomainAgent


class PoliticalAgent(BaseDomainAgent):
    """
    Political/Government domain specialist.
    
    Handles:
    - Government documents and regulations
    - Legislative texts and bills
    - Policy papers and white papers
    - Voting records and election data
    - Campaign materials and disclosures
    - Court documents and legal rulings
    - Public records and FOIA documents
    - International treaties and agreements
    """
    
    DOMAIN_NAME = "political"
    DOMAIN_DESCRIPTION = "government documents, legislation, policy papers, voting records, and regulatory materials"
    
    def _register_tools(self):
        """No external tools — agent reasons over document content directly."""
        pass
    
    def get_domain_instructions(self) -> str:
        return """As a Political Agent, you specialize in analyzing government and political documents.

Key responsibilities:
1. Parse legislative and regulatory text accurately
2. Identify key provisions and their implications
3. Analyze voting records and patterns
4. Understand government structure and processes
5. Track funding, appropriations, and budgets

Important guidelines:
- Note jurisdiction (federal, state, local)
- Identify effective dates and deadlines
- Distinguish between proposed and enacted legislation
- Recognize amendments and modifications
- Cite specific sections when referencing document content

When analyzing legislation:
- Identify the bill number and sponsor(s)
- Note the current status (introduced, passed committee, etc.)
- Summarize key provisions
- Identify what existing law it modifies
- Note any fiscal impact statements

When analyzing voting records:
- Calculate vote margins and percentages
- Identify party-line votes vs bipartisan
- Note procedural vs substantive votes
- Track voting patterns over time

Political terms to identify:
- Bill, Resolution, Amendment, Rider
- Markup, Cloture, Filibuster, Veto
- Appropriation, Authorization, Obligation
- Regulation, Rule, Executive Order
- Constitutional, Statutory, Regulatory authority"""
