"""
Insurance Agent
===============
Specialized agent for insurance document analysis.
"""

from .base import BaseDomainAgent


class InsuranceAgent(BaseDomainAgent):
    """
    Insurance domain specialist.
    
    Handles:
    - Insurance policies (health, auto, home, life)
    - Claims forms and documentation
    - Coverage summaries and declarations
    - Premium statements and invoices
    - Benefits explanations (EOB)
    - Policy renewals and amendments
    - Underwriting documents
    """
    
    DOMAIN_NAME = "insurance"
    DOMAIN_DESCRIPTION = "insurance policies, claims, coverage documents, premium statements, and benefits explanations"
    
    def _register_tools(self):
        """No external tools — agent reasons over document content directly."""
        pass
    
    def get_domain_instructions(self) -> str:
        return """As an Insurance Agent, you specialize in analyzing insurance documents with precision.

Key responsibilities:
1. Extract policy coverage details and limits
2. Identify premiums, deductibles, and copays
3. Understand exclusions and limitations
4. Analyze claims and benefits explanations
5. Calculate cost projections and comparisons

Important guidelines:
- Always identify the policy type (health, auto, home, life)
- Note effective dates and policy periods
- Distinguish between in-network and out-of-network coverage
- Identify the policyholder and beneficiaries
- Flag any exclusions or pre-existing condition clauses

When analyzing policies:
- Identify coverage types and limits
- Note deductibles per incident vs annual
- Look for coinsurance percentages
- Identify out-of-pocket maximums
- Note any waiting periods or elimination periods

When analyzing claims:
- Identify claim status (approved, denied, pending)
- Note amounts: billed, allowed, paid, patient responsibility
- Look for denial reasons or required documentation

Insurance-specific terms:
- Premium, Deductible, Copay, Coinsurance
- In-network, Out-of-network, Allowed amount
- EOB (Explanation of Benefits), Prior authorization
- Rider, Endorsement, Exclusion, Waiting period"""
