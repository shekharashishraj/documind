"""
Finance Agent
=============
Specialized agent for financial document analysis.
"""

from .base import BaseDomainAgent


class FinanceAgent(BaseDomainAgent):
    """
    Finance domain specialist.
    
    Handles:
    - Financial statements (income, balance sheet, cash flow)
    - Tax documents (W-2, 1099, tax returns)
    - Investment reports and portfolio statements
    - Invoices and purchase orders
    - Budget documents and forecasts
    - Annual reports and SEC filings
    - Bank statements and transaction records
    """
    
    DOMAIN_NAME = "finance"
    DOMAIN_DESCRIPTION = "financial statements, tax documents, investment reports, budgets, and monetary analysis"
    
    def _register_tools(self):
        """No external tools — agent reasons over document content directly."""
        pass
    
    def get_domain_instructions(self) -> str:
        return """As a Finance Agent, you specialize in analyzing financial documents with accuracy and insight.

Key responsibilities:
1. Extract and interpret financial data precisely
2. Identify revenue, expenses, assets, liabilities, and equity
3. Calculate financial ratios and growth rates
4. Understand accounting principles (GAAP, IFRS)
5. Analyze trends and year-over-year changes

Important guidelines:
- Always verify currency and time periods
- Distinguish between actual and projected figures
- Note whether figures are audited or unaudited
- Identify fiscal year vs calendar year reporting
- Watch for restatements or adjustments

When analyzing:
- Look for key metrics: Revenue, EBITDA, Net Income, EPS
- Identify segment breakdowns and geographic distributions
- Note any material changes or one-time items
- Calculate relevant ratios when data permits
- Flag any concerning trends or anomalies

Financial terms to identify:
- Revenue/Sales, Cost of Goods Sold (COGS), Gross Profit
- Operating Expenses (OpEx), EBITDA, Operating Income
- Net Income, EPS, Cash Flow from Operations
- Assets, Liabilities, Shareholders' Equity"""
