"""
Router / Supervisor Agent
=========================
Intelligent dispatcher that analyzes user prompts and PDF content
to classify intent and route to the appropriate domain specialist.
"""

import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple
from openai import OpenAI


class Domain(Enum):
    """Supported domain categories for routing."""
    HEALTHCARE = "healthcare"
    FINANCE = "finance"
    HR = "hr"
    INSURANCE = "insurance"
    EDUCATION = "education"
    POLITICAL = "political"
    GENERAL = "general"  # Fallback for uncategorized queries


@dataclass
class RoutingDecision:
    """Result of the routing decision."""
    primary_domain: Domain
    secondary_domains: List[Domain]
    confidence: float
    reasoning: str
    requires_multi_agent: bool
    sub_tasks: List[Dict[str, Any]]


@dataclass
class DocumentAnalysis:
    """Analysis of document type and content."""
    document_type: str
    detected_domains: List[Domain]
    key_entities: List[str]
    summary: str


class RouterAgent:
    """
    Supervisor/Router Agent that acts as the intelligent dispatcher.
    
    Responsibilities:
    - Analyze user prompt and PDF content
    - Classify intent and detect domain
    - Route to appropriate domain specialist(s)
    - Handle multi-domain queries by orchestrating multiple agents
    """
    
    ROUTING_SYSTEM_PROMPT = """You are an intelligent router agent responsible for analyzing user queries about PDF documents and routing them to the appropriate domain specialist.

Your job is to:
1. Analyze the user's question and the document content
2. Classify which domain(s) the query belongs to
3. Determine if multiple specialists are needed
4. Break down complex queries into sub-tasks if necessary

Available domains and their specializations:
- HEALTHCARE: Medical records, prescriptions, clinical notes, health insurance claims, lab results, medical bills
- FINANCE: Financial statements, tax documents, invoices, budgets, investment reports, annual reports, balance sheets
- HR: Resumes, employment contracts, performance reviews, employee handbooks, job descriptions, payroll documents
- INSURANCE: Insurance policies, claims forms, coverage documents, premium statements, benefits summaries
- EDUCATION: Transcripts, diplomas, course syllabi, academic papers, student records, certifications
- POLITICAL: Government documents, legislative texts, policy papers, voting records, campaign materials, regulations

You must respond with a JSON object in this exact format:
{
    "primary_domain": "DOMAIN_NAME",
    "secondary_domains": ["DOMAIN2", "DOMAIN3"],
    "confidence": 0.95,
    "reasoning": "Brief explanation of routing decision",
    "requires_multi_agent": false,
    "sub_tasks": [
        {"domain": "DOMAIN", "task": "Specific sub-task description"}
    ]
}

Rules:
- Choose GENERAL only if no specific domain applies
- Set requires_multi_agent to true if the query spans multiple domains
- Break complex queries into sub_tasks when needed
- Confidence should reflect how certain you are about the routing"""

    DOCUMENT_ANALYSIS_PROMPT = """Analyze this document content and identify:
1. What type of document this is
2. Which domain(s) it belongs to
3. Key entities mentioned (people, organizations, amounts, dates)
4. A brief summary

Document content:
{document_content}

Respond with JSON:
{{
    "document_type": "Type of document",
    "detected_domains": ["DOMAIN1", "DOMAIN2"],
    "key_entities": ["entity1", "entity2"],
    "summary": "Brief summary of the document"
}}"""

    def __init__(self, api_key: Optional[str] = None, verbose: bool = False):
        """
        Initialize the router agent.
        
        Args:
            api_key: OpenAI API key. If not provided, attempts to get from keyring.
            verbose: Print detailed logging of routing decisions.
        """
        self.api_key = api_key or self._get_api_key()
        self.client = OpenAI(api_key=self.api_key)
        self.model = "gpt-4o"
        self.verbose = verbose
        self._document_analysis_cache: Dict[str, DocumentAnalysis] = {}
    
    def _log(self, message: str, indent: int = 3):
        """Log message if verbose mode is on."""
        if self.verbose:
            prefix = " " * indent
            print(f"{prefix}{message}")
    
    def _get_api_key(self) -> str:
        """Get API key from environment or keyring."""
        # Try environment first
        key = os.environ.get("OPENAI_API_KEY")
        if key:
            return key
        
        # Try keyring
        try:
            import keyring
            key = keyring.get_password("openai", "api_key")
            if key:
                return key
        except ImportError:
            pass
        
        raise ValueError("No OpenAI API key found. Set OPENAI_API_KEY or use keyring.")
    
    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Make an LLM call and return the response."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        return response.choices[0].message.content

    @staticmethod
    def _parse_domain(value: str) -> Domain:
        """Parse a domain string safely, defaulting to GENERAL."""
        normalized = (value or "").strip().lower()
        for domain in Domain:
            if domain.value == normalized:
                return domain
        return Domain.GENERAL
    
    def analyze_document(self, document_content: str, cache_key: Optional[str] = None) -> DocumentAnalysis:
        """
        Analyze a document to understand its type and domains.
        
        Args:
            document_content: The text content of the document
            cache_key: Optional key for caching (e.g., file path)
            
        Returns:
            DocumentAnalysis with detected information
        """
        if cache_key and cache_key in self._document_analysis_cache:
            self._log("↩️  Using cached document analysis")
            return self._document_analysis_cache[cache_key]
        
        # Truncate content if too long
        max_chars = 8000
        truncated = document_content[:max_chars] if len(document_content) > max_chars else document_content
        
        self._log(f"📡 Calling LLM for document analysis ({len(truncated):,} chars sent)...")
        prompt = self.DOCUMENT_ANALYSIS_PROMPT.format(document_content=truncated)
        
        response = self._call_llm(
            "You are a document analysis expert. Analyze documents and return structured JSON.",
            prompt
        )
        
        try:
            data = json.loads(response)
            detected_domains = []
            for raw_domain in data.get("detected_domains", []):
                parsed_domain = self._parse_domain(str(raw_domain))
                if parsed_domain != Domain.GENERAL or str(raw_domain).strip().lower() == Domain.GENERAL.value:
                    detected_domains.append(parsed_domain)

            analysis = DocumentAnalysis(
                document_type=data.get("document_type", "Unknown"),
                detected_domains=detected_domains,
                key_entities=data.get("key_entities", []),
                summary=data.get("summary", "")
            )
            self._log(f"📄 Document type: {analysis.document_type}")
            self._log(f"🎯 Detected domains: {[d.value for d in analysis.detected_domains]}")
            self._log(f"🔑 Key entities: {analysis.key_entities[:8]}")
            self._log(f"📝 Summary: {analysis.summary[:200]}")
        except (json.JSONDecodeError, ValueError):
            analysis = DocumentAnalysis(
                document_type="Unknown",
                detected_domains=[Domain.GENERAL],
                key_entities=[],
                summary="Unable to analyze document"
            )
        
        if cache_key:
            self._document_analysis_cache[cache_key] = analysis
        
        return analysis
    
    def route(self, user_query: str, document_content: str, document_analysis: Optional[DocumentAnalysis] = None) -> RoutingDecision:
        """
        Route a user query to the appropriate domain agent(s).
        
        Args:
            user_query: The user's question
            document_content: The parsed document text
            document_analysis: Pre-computed document analysis (optional)
            
        Returns:
            RoutingDecision with routing information
        """
        # Get document analysis if not provided
        if document_analysis is None:
            document_analysis = self.analyze_document(document_content)
        
        # Build context for routing decision
        routing_context = f"""User Query: {user_query}

Document Type: {document_analysis.document_type}
Detected Domains: {[d.value for d in document_analysis.detected_domains]}
Key Entities: {document_analysis.key_entities}
Document Summary: {document_analysis.summary}

Document Content (first 4000 chars):
{document_content[:4000]}"""
        
        self._log(f"📡 Calling LLM for routing decision...")
        self._log(f"   Query: {user_query[:120]}")
        self._log(f"   Doc type: {document_analysis.document_type}")
        response = self._call_llm(self.ROUTING_SYSTEM_PROMPT, routing_context)
        
        try:
            data = json.loads(response)
            
            # Parse primary domain
            primary = self._parse_domain(str(data.get("primary_domain", Domain.GENERAL.value)))
            
            # Parse secondary domains
            secondary = []
            for d_str in data.get("secondary_domains", []):
                parsed = self._parse_domain(str(d_str))
                if parsed != Domain.GENERAL or str(d_str).strip().lower() == Domain.GENERAL.value:
                    secondary.append(parsed)
            
            return RoutingDecision(
                primary_domain=primary,
                secondary_domains=secondary,
                confidence=float(data.get("confidence", 0.5)),
                reasoning=data.get("reasoning", ""),
                requires_multi_agent=data.get("requires_multi_agent", False),
                sub_tasks=data.get("sub_tasks", [])
            )
            
        except (json.JSONDecodeError, ValueError) as e:
            self._log(f"⚠️  Routing parse failed: {str(e)}, falling back to GENERAL")
            # Fallback to general domain
            return RoutingDecision(
                primary_domain=Domain.GENERAL,
                secondary_domains=[],
                confidence=0.3,
                reasoning=f"Routing failed: {str(e)}",
                requires_multi_agent=False,
                sub_tasks=[]
            )
    
    def should_involve_multiple_agents(self, routing: RoutingDecision) -> bool:
        """
        Determine if the query requires multiple domain agents.
        
        Args:
            routing: The routing decision
            
        Returns:
            True if multiple agents should collaborate
        """
        return routing.requires_multi_agent or len(routing.secondary_domains) > 0
    
    def get_execution_plan(self, routing: RoutingDecision) -> List[Tuple[Domain, str]]:
        """
        Get ordered list of (domain, task) pairs for execution.
        
        Args:
            routing: The routing decision
            
        Returns:
            List of (Domain, task_description) tuples
        """
        if routing.sub_tasks:
            plan = []
            for task in routing.sub_tasks:
                domain = self._parse_domain(str(task.get("domain", Domain.GENERAL.value)))
                plan.append((domain, task.get("task", "")))
            return plan
        
        # Single domain, single task
        return [(routing.primary_domain, "Process the user query")]


class SupervisorAgent(RouterAgent):
    """
    Extended Router that also supervises agent execution and handles failures.
    
    Adds:
    - Monitoring of agent execution
    - Retry logic for failed agents
    - Result aggregation hints
    """
    
    def __init__(self, api_key: Optional[str] = None, verbose: bool = False):
        super().__init__(api_key, verbose=verbose)
        self.execution_history: List[Dict[str, Any]] = []
    
    def record_execution(self, domain: Domain, task: str, success: bool, result: Any):
        """Record an agent execution for monitoring."""
        self.execution_history.append({
            "domain": domain.value,
            "task": task,
            "success": success,
            "result_preview": str(result)[:200] if result else None
        })
    
    def suggest_retry_strategy(self, domain: Domain, error: str) -> Dict[str, Any]:
        """
        Suggest a retry strategy for a failed agent.
        
        Args:
            domain: The domain that failed
            error: The error message
            
        Returns:
            Strategy dict with retry information
        """
        # Could be extended with LLM-based analysis
        return {
            "should_retry": True,
            "alternative_domain": Domain.GENERAL if domain != Domain.GENERAL else None,
            "simplified_task": True,
            "reason": f"Agent {domain.value} failed: {error}"
        }
    
    def get_aggregation_hints(self, domains_involved: List[Domain]) -> str:
        """
        Get hints for the composer on how to aggregate results.
        
        Args:
            domains_involved: List of domains that contributed results
            
        Returns:
            Hints string for result aggregation
        """
        if len(domains_involved) == 1:
            return f"Single domain response from {domains_involved[0].value}. Present directly."
        
        domain_names = [d.value for d in domains_involved]
        return f"Multi-domain response from {', '.join(domain_names)}. Synthesize coherently, noting cross-domain insights."
