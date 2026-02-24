"""
Multi-Agent Supervisor Orchestrator
===================================
Central orchestrator implementing the Multi-Agent Supervisor architecture.

Flow:
1. Perception Layer: Parse PDF and extract content
2. Router/Supervisor: Classify intent and select domain agent
3. Domain Agent: Execute specialized analysis (single agent, dynamically spawned)
"""

import os
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Type
from enum import Enum

# Import all layers
from .perception import PerceptionLayer
from .router import SupervisorAgent, RoutingDecision, Domain
from .domain_agents.base import BaseDomainAgent, AgentResult
from .domain_agents.healthcare import HealthcareAgent
from .domain_agents.finance import FinanceAgent
from .domain_agents.hr import HRAgent
from .domain_agents.insurance import InsuranceAgent
from .domain_agents.education import EducationAgent
from .domain_agents.political import PoliticalAgent


class ExecutionStatus(Enum):
    """Status of the orchestration pipeline."""
    PENDING = "pending"
    PARSING = "parsing"
    ROUTING = "routing"
    EXECUTING = "executing"
    COMPOSING = "composing"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class ExecutionTrace:
    """Trace of the execution pipeline."""
    status: ExecutionStatus = ExecutionStatus.PENDING
    steps: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    def add_step(self, step_name: str, data: Any):
        """Add a step to the trace."""
        self.steps.append({"step": step_name, "data": data})
    
    def add_error(self, error: str):
        """Add an error to the trace."""
        self.errors.append(error)


@dataclass
class OrchestratorResult:
    """Final result from the orchestrator."""
    success: bool
    answer: str
    confidence: float
    evidence: List[str]
    trace: ExecutionTrace
    document_info: Dict[str, Any]
    routing_decision: Optional[RoutingDecision]
    agent_result: Optional[AgentResult]


class MultiAgentOrchestrator:
    """
    Central orchestrator for the Multi-Agent Supervisor architecture.
    
    This is the "brain" that:
    1. Receives user queries with PDF documents
    2. Parses PDFs through perception layer
    3. Routes to the appropriate domain agent via supervisor
    4. Returns the agent’s answer directly (no composer)
    
    Agents are spawned dynamically and released after use
    to avoid holding multiple agents in memory.
    """
    
    # Map domains to agent classes
    DOMAIN_AGENTS: Dict[Domain, Type[BaseDomainAgent]] = {
        Domain.HEALTHCARE: HealthcareAgent,
        Domain.FINANCE: FinanceAgent,
        Domain.HR: HRAgent,
        Domain.INSURANCE: InsuranceAgent,
        Domain.EDUCATION: EducationAgent,
        Domain.POLITICAL: PoliticalAgent
    }
    
    def __init__(self, api_key: Optional[str] = None, verbose: bool = True):
        """
        Initialize the orchestrator.
        
        Args:
            api_key: OpenAI API key (will try keyring if not provided)
            verbose: Print progress messages
        """
        self.api_key = api_key or self._get_api_key()
        self.verbose = verbose
        
        # Initialize layers
        self.perception = PerceptionLayer()
        self.supervisor = SupervisorAgent(api_key=self.api_key, verbose=self.verbose)
    
    def _get_api_key(self) -> str:
        """Get API key from environment or keyring."""
        key = os.environ.get("OPENAI_API_KEY")
        if key:
            return key
        try:
            import keyring
            key = keyring.get_password("openai", "api_key")
            if key:
                return key
        except ImportError:
            pass
        raise ValueError("No OpenAI API key found. Set OPENAI_API_KEY or use keyring.")
    
    def _log(self, message: str):
        """Log message if verbose mode is on."""
        if self.verbose:
            print(message)
    
    def _create_agent(self, domain: Domain) -> BaseDomainAgent:
        """Dynamically create a single agent for the given domain."""
        agent_class = self.DOMAIN_AGENTS.get(domain)
        if agent_class:
            return agent_class(api_key=self.api_key, verbose=self.verbose)
        # Fallback to finance agent for GENERAL domain
        return FinanceAgent(api_key=self.api_key, verbose=self.verbose)
    
    def process(self, pdf_path: str, query: str) -> OrchestratorResult:
        """
        Process a PDF document with a user query.
        
        Args:
            pdf_path: Path to the PDF file
            query: User's question about the document
            
        Returns:
            OrchestratorResult with complete response and trace
        """
        trace = ExecutionTrace()
        agent_result: Optional[AgentResult] = None
        routing_decision = None
        
        try:
            # ====== STEP 1: PERCEPTION LAYER ======
            trace.status = ExecutionStatus.PARSING
            self._log("\n" + "=" * 80)
            self._log("📄 STEP 1 │ PERCEPTION LAYER: Parsing PDF")
            self._log("=" * 80)
            self._log(f"   📂 File: {pdf_path}")
            
            parsed_doc = self.perception.process_document(pdf_path)
            self._log(f"   ✓ Parsed {parsed_doc.metadata.page_count} pages ({parsed_doc.metadata.total_characters:,} chars)")
            
            trace.add_step("perception", {
                "filename": parsed_doc.metadata.filename,
                "pages": parsed_doc.metadata.page_count,
                "characters": parsed_doc.metadata.total_characters
            })
            
            # ====== STEP 2: ROUTER/SUPERVISOR ======
            trace.status = ExecutionStatus.ROUTING
            self._log("\n" + "=" * 80)
            self._log("🧭 STEP 2 │ ROUTER/SUPERVISOR: Analyzing intent")
            self._log("=" * 80)
            
            # First, analyze the document
            self._log("\n   ─── Phase 2a: Document Analysis ───")
            doc_analysis = self.supervisor.analyze_document(
                parsed_doc.full_text, 
                cache_key=pdf_path
            )
            self._log(f"   📋 Document type: {doc_analysis.document_type}")
            self._log(f"   🏷️  Detected domains: {[d.value for d in doc_analysis.detected_domains]}")
            
            # Then, route the query
            self._log("\n   ─── Phase 2b: Query Routing ───")
            routing_decision = self.supervisor.route(
                query, 
                parsed_doc.full_text,
                doc_analysis
            )
            self._log(f"   🎯 Primary domain: {routing_decision.primary_domain.value}")
            self._log(f"   📊 Confidence: {routing_decision.confidence * 100:.0f}%")
            self._log(f"   💭 Reasoning: {routing_decision.reasoning}")
            
            if routing_decision.secondary_domains:
                self._log(f"   📌 Secondary domains: {[d.value for d in routing_decision.secondary_domains]}")
            
            trace.add_step("routing", {
                "primary_domain": routing_decision.primary_domain.value,
                "confidence": routing_decision.confidence,
                "requires_multi_agent": routing_decision.requires_multi_agent
            })
            
            # ====== STEP 3: DOMAIN AGENT EXECUTION ======
            trace.status = ExecutionStatus.EXECUTING
            self._log("\n" + "=" * 80)
            self._log("⚡ STEP 3 │ DOMAIN AGENT EXECUTION")
            self._log("=" * 80)
            
            # Dynamically spawn a single agent for the primary domain
            domain = routing_decision.primary_domain
            self._log(f"\n   🤖 Spawning [{domain.value.upper()}] agent...")
            
            agent = self._create_agent(domain)
            self._log(f"      Agent: {agent.__class__.__name__}")
            
            # Execute agent
            agent_result = agent.process(
                query=query,
                document_content=parsed_doc.full_text,
                context={"document_type": doc_analysis.document_type}
            )
            
            # Release agent immediately
            del agent
            
            # Display result
            status_icon = "✓" if agent_result.success else "✗"
            self._log(f"      {status_icon} Confidence: {agent_result.confidence * 100:.0f}%")
            
            if agent_result.reasoning_trace:
                self._log(f"      💭 Reasoning steps: {len(agent_result.reasoning_trace)}")
            
            trace.add_step(f"agent_{domain.value}", {
                "success": agent_result.success,
                "confidence": agent_result.confidence
            })
            
            trace.status = ExecutionStatus.COMPLETE
            
            return OrchestratorResult(
                success=agent_result.success,
                answer=agent_result.answer,
                confidence=agent_result.confidence,
                evidence=agent_result.evidence,
                trace=trace,
                document_info={
                    "filename": parsed_doc.metadata.filename,
                    "pages": parsed_doc.metadata.page_count,
                    "type": doc_analysis.document_type
                },
                routing_decision=routing_decision,
                agent_result=agent_result
            )
            
        except Exception as e:
            trace.status = ExecutionStatus.ERROR
            trace.add_error(str(e))
            self._log(f"\n❌ ERROR: {str(e)}")
            
            return OrchestratorResult(
                success=False,
                answer=f"Error processing request: {str(e)}",
                confidence=0.0,
                evidence=[],
                trace=trace,
                document_info={},
                routing_decision=routing_decision,
                agent_result=agent_result
            )
    
    def print_result(self, result: OrchestratorResult):
        """
        Print the orchestrator result in a formatted way.
        
        Args:
            result: The orchestrator result to print
        """
        print("\n" + "=" * 80)
        print("📋 FINAL RESULT")
        print("=" * 80)
        
        print(f"\n📝 Query: (see above)")
        print(f"📊 Status: {'✓ Success' if result.success else '✗ Failed'}")
        print(f"📄 Document: {result.document_info.get('filename', 'N/A')}")
        
        if result.routing_decision:
            print(f"🎯 Routed to: {result.routing_decision.primary_domain.value}")
        
        print(f"\n{'─' * 80}")
        print("ANSWER:")
        print("─" * 80)
        print(result.answer)
        print("─" * 80)
        
        print(f"\n💯 Confidence: {result.confidence * 100:.0f}%")
        
        if result.evidence:
            print("\n📌 Evidence:")
            for ev in result.evidence:
                print(f"   • {ev}")
        
        if result.agent_result:
            domain = result.agent_result.metadata.get("domain", "unknown")
            iters = result.agent_result.metadata.get("iterations", "?")
            print(f"\n🤖 Agent: {domain} ({iters} iteration(s))")
        
        print("\n" + "=" * 80)


def create_orchestrator(api_key: Optional[str] = None, verbose: bool = True) -> MultiAgentOrchestrator:
    """
    Factory function to create an orchestrator instance.
    
    Args:
        api_key: OpenAI API key (optional, will use keyring if not provided)
        verbose: Print progress messages
        
    Returns:
        Configured MultiAgentOrchestrator instance
    """
    return MultiAgentOrchestrator(api_key=api_key, verbose=verbose)
