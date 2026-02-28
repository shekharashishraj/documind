"""
Base Domain Agent
=================
Abstract base class for all domain-specific worker agents.
Implements the ReAct (Reasoning + Acting) pattern for tool calling.
"""

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from enum import Enum
from openai import OpenAI


@dataclass
class ToolCall:
    """Represents a tool invocation."""
    tool_name: str
    arguments: Dict[str, Any]
    result: Optional[Any] = None
    error: Optional[str] = None


@dataclass
class ReasoningStep:
    """A single step in the ReAct loop."""
    thought: str
    action: Optional[str] = None
    action_input: Optional[Dict[str, Any]] = None
    observation: Optional[str] = None


@dataclass
class AgentResult:
    """Result from a domain agent execution."""
    success: bool
    answer: str
    confidence: float
    evidence: List[str]
    tool_calls: List[ToolCall]
    reasoning_trace: List[ReasoningStep]
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseDomainAgent(ABC):
    """
    Abstract base class for domain-specific agents.
    
    Each domain agent:
    - Has specialized knowledge via system prompts
    - Has access to domain-specific tools
    - Uses ReAct pattern for autonomous reasoning
    - Can execute multi-step tool calling loops
    """
    
    # Override in subclasses
    DOMAIN_NAME: str = "base"
    DOMAIN_DESCRIPTION: str = "Base domain agent"
    
    # ReAct system prompt template
    REACT_SYSTEM_PROMPT = """You are a specialized {domain_name} agent with expertise in {domain_description}.

Your task is to analyze documents and answer questions using the ReAct (Reasoning + Acting) pattern.

{domain_specific_instructions}

Available Tools:
{tools_description}

For each question, follow this process:
1. THINK: Analyze what information you need
2. ACT: Call a tool if needed to gather information
3. OBSERVE: Review the tool's output
4. Repeat until you have enough information
5. ANSWER: Provide your final response

Respond in JSON format:
{{
    "thought": "Your reasoning about what to do next",
    "action": "tool_name" or null if ready to answer,
    "action_input": {{"arg1": "value1"}} or null,
    "final_answer": null or {{"answer": "...", "confidence": 0.9, "evidence": ["..."]}}
}}

Rules:
- Always think before acting
- Use tools when you need specific information
- Provide evidence for your answers
- Express confidence as a decimal (0.0 to 1.0)
- If you cannot find information, say so clearly"""

    def __init__(self, api_key: Optional[str] = None, max_iterations: int = 5, verbose: bool = False):
        """
        Initialize the domain agent.
        
        Args:
            api_key: OpenAI API key
            max_iterations: Maximum ReAct loop iterations
            verbose: Print detailed logging of ReAct loop
        """
        self.api_key = api_key or self._get_api_key()
        self.client = OpenAI(api_key=self.api_key)
        self.model = "gpt-4o"
        self.max_iterations = max_iterations
        self.verbose = verbose
        self.tools: Dict[str, Callable] = {}
        self._register_tools()
    
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
        raise ValueError("No OpenAI API key found")
    
    @abstractmethod
    def _register_tools(self):
        """Register domain-specific tools. Override in subclasses."""
        pass
    
    @abstractmethod
    def get_domain_instructions(self) -> str:
        """Get domain-specific instructions for the agent. Override in subclasses."""
        pass
    
    def register_tool(self, name: str, func: Callable, description: str, parameters: Dict[str, Any]):
        """
        Register a tool for this agent.
        
        Args:
            name: Tool name
            func: The callable function
            description: Tool description
            parameters: Parameter schema
        """
        self.tools[name] = {
            "function": func,
            "description": description,
            "parameters": parameters
        }
    
    def get_tools_description(self) -> str:
        """Get formatted description of available tools."""
        if not self.tools:
            return "No tools available. Analyze based on document content only."
        
        descriptions = []
        for name, tool in self.tools.items():
            params = tool["parameters"]
            param_str = ", ".join([f"{k}: {v.get('type', 'any')}" for k, v in params.items()])
            descriptions.append(f"- {name}({param_str}): {tool['description']}")
        
        return "\n".join(descriptions)
    
    def _log(self, message: str, indent: int = 6):
        """Log message if verbose mode is on."""
        if self.verbose:
            prefix = " " * indent
            print(f"{prefix}{message}")

    @staticmethod
    def _as_text(value: Any) -> str:
        """Safely coerce model outputs to displayable text."""
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)

    @staticmethod
    def _as_mapping(value: Any) -> Dict[str, Any]:
        """Safely coerce model outputs to a mapping for tool args."""
        if isinstance(value, dict):
            return value
        if value is None:
            return {}
        return {"value": value}

    @staticmethod
    def _as_evidence_list(value: Any) -> List[str]:
        """Normalize evidence field to a list of strings."""
        if isinstance(value, list):
            return [BaseDomainAgent._as_text(item) for item in value]
        if value is None:
            return []
        return [BaseDomainAgent._as_text(value)]

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> ToolCall:
        """
        Execute a registered tool.
        
        Args:
            tool_name: Name of the tool to execute
            arguments: Arguments to pass to the tool
            
        Returns:
            ToolCall with result or error
        """
        tool_call = ToolCall(tool_name=tool_name, arguments=arguments)
        
        if tool_name not in self.tools:
            tool_call.error = f"Unknown tool: {tool_name}"
            self._log(f"❌ Unknown tool: {tool_name}", indent=10)
            return tool_call
        
        try:
            self._log(f"🔧 Executing: {tool_name}({arguments})", indent=10)
            func = self.tools[tool_name]["function"]
            result = func(**arguments)
            tool_call.result = result
            result_preview = str(result)[:200]
            self._log(f"📤 Result: {result_preview}", indent=10)
        except Exception as e:
            tool_call.error = str(e)
            self._log(f"❌ Tool error: {str(e)}", indent=10)
        
        return tool_call
    
    def _build_system_prompt(self) -> str:
        """Build the complete system prompt for this agent."""
        return self.REACT_SYSTEM_PROMPT.format(
            domain_name=self.DOMAIN_NAME,
            domain_description=self.DOMAIN_DESCRIPTION,
            domain_specific_instructions=self.get_domain_instructions(),
            tools_description=self.get_tools_description()
        )
    
    def _call_llm(self, messages: List[Dict[str, str]]) -> str:
        """Make an LLM call."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        return response.choices[0].message.content
    
    def process(self, query: str, document_content: str, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        """
        Process a query using the ReAct pattern.
        
        Args:
            query: The user's question
            document_content: The document text to analyze
            context: Optional additional context
            
        Returns:
            AgentResult with answer and reasoning trace
        """
        system_prompt = self._build_system_prompt()
        
        # Build initial user message
        user_message = f"""Document Content:
{document_content[:6000]}

Query: {query}"""
        
        if context:
            user_message += f"\n\nAdditional Context: {json.dumps(context)}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        tool_calls: List[ToolCall] = []
        reasoning_trace: List[ReasoningStep] = []
        
        self._log(f"")
        self._log(f"┌─ ReAct Loop Started (max {self.max_iterations} iterations)")
        self._log(f"│  Domain: {self.DOMAIN_NAME} | Model: {self.model}")
        self._log(f"│  Tools available: {list(self.tools.keys())}")
        self._log(f"│  Query: {query[:100]}{'...' if len(query) > 100 else ''}")
        
        # ReAct loop
        for iteration in range(self.max_iterations):
            self._log(f"│")
            self._log(f"├─── Iteration {iteration + 1}/{self.max_iterations}")
            self._log(f"│    📡 Calling LLM...")
            response = self._call_llm(messages)
            
            try:
                data = json.loads(response)
            except json.JSONDecodeError:
                self._log(f"│    ⚠️  LLM returned non-JSON, wrapping as final answer")
                data = {"thought": response, "action": None, "final_answer": {"answer": response, "confidence": 0.5, "evidence": []}}
            
            thought = self._as_text(data.get("thought", ""))
            action_raw = data.get("action")
            action = self._as_text(action_raw).strip() if action_raw is not None else None
            if action == "":
                action = None
            action_input = self._as_mapping(data.get("action_input", {}))
            final_answer_raw = data.get("final_answer")
            final_answer = final_answer_raw if isinstance(final_answer_raw, dict) else None
            
            self._log(f"│    💭 THINK: {thought[:200]}{'...' if len(thought) > 200 else ''}")
            
            step = ReasoningStep(
                thought=thought,
                action=action,
                action_input=action_input
            )
            
            # Check if agent wants to give final answer
            if final_answer and not action:
                step.observation = "Final answer provided"
                reasoning_trace.append(step)
                
                answer_text = self._as_text(final_answer.get("answer", ""))
                try:
                    confidence = float(final_answer.get("confidence", 0.5))
                except (TypeError, ValueError):
                    confidence = 0.5
                confidence = max(0.0, min(1.0, confidence))
                evidence = self._as_evidence_list(final_answer.get("evidence", []))
                
                self._log(f"│    ✅ FINAL ANSWER (after {iteration + 1} iteration(s))")
                self._log(f"│    📊 Confidence: {confidence * 100:.0f}%")
                self._log(f"│    📝 Answer preview: {answer_text[:150]}{'...' if len(answer_text) > 150 else ''}")
                if evidence:
                    self._log(f"│    📎 Evidence ({len(evidence)} items):")
                    for ev in evidence[:3]:
                        self._log(f"│       • {str(ev)[:120]}")
                self._log(f"└─ ReAct Loop Complete")
                
                return AgentResult(
                    success=True,
                    answer=answer_text,
                    confidence=confidence,
                    evidence=evidence,
                    tool_calls=tool_calls,
                    reasoning_trace=reasoning_trace,
                    metadata={"domain": self.DOMAIN_NAME, "iterations": iteration + 1}
                )
            
            # Execute tool if requested
            if action:
                self._log(f"│    🎬 ACT: {action}")
                self._log(f"│    📥 Input: {json.dumps(action_input)[:200]}")
                
                tool_call = self.execute_tool(action, action_input or {})
                tool_calls.append(tool_call)
                
                if tool_call.error:
                    observation = f"Error: {tool_call.error}"
                    self._log(f"│    👁️  OBSERVE: ❌ {observation[:200]}")
                else:
                    observation = f"Result: {json.dumps(tool_call.result) if isinstance(tool_call.result, (dict, list)) else str(tool_call.result)}"
                    self._log(f"│    👁️  OBSERVE: {observation[:200]}{'...' if len(observation) > 200 else ''}")
                
                step.observation = observation
                reasoning_trace.append(step)
                
                # Add observation to conversation
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": f"Observation: {observation}\n\nContinue your analysis."})
            else:
                # No action and no final answer - unexpected
                self._log(f"│    ⚠️  No action and no final answer — breaking loop")
                reasoning_trace.append(step)
                break
        
        # Max iterations reached without final answer
        self._log(f"│")
        self._log(f"└─ ⚠️  ReAct Loop: Max iterations ({self.max_iterations}) reached without final answer")
        return AgentResult(
            success=False,
            answer="Unable to complete analysis within iteration limit",
            confidence=0.0,
            evidence=[],
            tool_calls=tool_calls,
            reasoning_trace=reasoning_trace,
            metadata={"domain": self.DOMAIN_NAME, "iterations": self.max_iterations, "reason": "max_iterations"}
        )
    
    def __repr__(self):
        return f"{self.__class__.__name__}(domain={self.DOMAIN_NAME}, tools={list(self.tools.keys())})"
