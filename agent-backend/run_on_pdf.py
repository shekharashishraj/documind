#!/usr/bin/env python3
"""
Multi-Agent Supervisor Architecture for PDF Analysis.

Architecture:
┌────────────────────────┐
│  Perception Layer      │ ← PDF Parse + Text Extract
├────────────────────────┤
│  Router / Supervisor   │ ← Intent Classification + Domain Routing
├────────────────────────┤
│  Domain Worker Agents  │ ← Healthcare, Finance, HR, Insurance, Education, Political
│  + Tool Execution      │ ← ReAct pattern with domain-specific tools
├────────────────────────┤
│  Composer / Synthesizer│ ← Final answer synthesis
└────────────────────────┘
"""

import sys
from pathlib import Path
from src.multi_agent_orchestrator import create_orchestrator


def run_analysis(pdf_path: str, query: str):
    """
    Process a PDF through the Multi-Agent Supervisor pipeline.
    
    Args:
        pdf_path: Path to the PDF file
        query: User's question about the document
    """
    # Validate input
    path = Path(pdf_path)
    if not path.exists():
        print(f"❌ File not found: {pdf_path}")
        sys.exit(1)
    
    if not path.suffix.lower() == '.pdf':
        print(f"⚠️  Warning: File may not be a PDF: {path.suffix}")
    
    print()
    print("╔" + "═" * 78 + "╗")
    print("║" + " MULTI-AGENT SUPERVISOR ARCHITECTURE ".center(78) + "║")
    print("║" + " PDF Document Analysis System ".center(78) + "║")
    print("╚" + "═" * 78 + "╝")
    print()
    print(f"  📄 Document: {path.name}")
    print(f"  ❓ Query:    {query}")
    
    # Create and run orchestrator
    orchestrator = create_orchestrator(verbose=True)
    result = orchestrator.process(pdf_path=str(path), query=query)
    
    # Print final result
    orchestrator.print_result(result)
    
    # Print execution trace
    print("\n📊 EXECUTION TRACE")
    print("─" * 80)
    for step in result.trace.steps:
        step_name = step["step"]
        data = step["data"]
        
        if step_name == "perception":
            print(f"  1. 📄 Parsed: {data['pages']} pages, {data['characters']:,} chars")
        elif step_name == "routing":
            print(f"  2. 🧭 Routed to: {data['primary_domain']} ({data['confidence']*100:.0f}% confidence)")
        elif step_name.startswith("agent_"):
            domain = step_name.replace("agent_", "")
            print(f"  3. 🤖 {domain.upper()}: {'✓' if data['success'] else '✗'} "
                  f"({data['confidence']*100:.0f}% confidence)")
    
    if result.trace.errors:
        print(f"\n⚠️  Errors: {result.trace.errors}")
    
    print()
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("❌ Usage: python run_on_pdf.py <pdf_path> [query]")
        print()
        print("Example:")
        print('  python run_on_pdf.py document.pdf "What is the carbon footprint?"')
        print()
        print("Supported domains: Healthcare, Finance, HR, Insurance, Education, Political")
        sys.exit(1)

    pdf_path = sys.argv[1]
    query = sys.argv[2] if len(sys.argv) > 2 else "Analyze this document and provide key insights."

    try:
        run_analysis(pdf_path, query)
        print("✅ Analysis complete!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
