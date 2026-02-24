"""
Perception / Input Layer
========================
PDF Parser and Text Extraction module.

Extracts raw text, tables, and metadata from PDF documents,
converting them into machine-readable format for downstream processing.
"""

import os
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path


@dataclass
class PDFMetadata:
    """Metadata extracted from a PDF document."""
    filename: str
    page_count: int
    total_characters: int
    file_size_bytes: int = 0
    title: Optional[str] = None
    author: Optional[str] = None
    creation_date: Optional[str] = None


@dataclass
class TableData:
    """Represents a table extracted from a PDF."""
    page_number: int
    rows: List[List[str]] = field(default_factory=list)
    headers: List[str] = field(default_factory=list)


@dataclass
class PageContent:
    """Content from a single PDF page."""
    page_number: int
    text: str
    tables: List[TableData] = field(default_factory=list)
    has_images: bool = False


@dataclass
class ParsedDocument:
    """Complete parsed PDF document with all extracted data."""
    metadata: PDFMetadata
    pages: List[PageContent]
    full_text: str
    tables: List[TableData]
    
    def get_context_string(self) -> str:
        """Get formatted context string for LLM consumption."""
        context_parts = [
            f"Document: {self.metadata.filename}",
            f"Pages: {self.metadata.page_count}",
            f"Characters: {self.metadata.total_characters}",
            "",
            "=== DOCUMENT CONTENT ===",
            self.full_text
        ]
        
        if self.tables:
            context_parts.append("\n=== EXTRACTED TABLES ===")
            for i, table in enumerate(self.tables, 1):
                context_parts.append(f"\nTable {i} (Page {table.page_number}):")
                if table.headers:
                    context_parts.append(" | ".join(table.headers))
                    context_parts.append("-" * 40)
                for row in table.rows:
                    context_parts.append(" | ".join(str(cell) for cell in row))
        
        return "\n".join(context_parts)


class PDFParser:
    """
    PDF Parser that extracts text, tables, and metadata.
    
    Uses PyPDF for text extraction with fallback strategies.
    """
    
    def __init__(self):
        self._pypdf_available = self._check_pypdf()
    
    def _check_pypdf(self) -> bool:
        """Check if PyPDF is available."""
        try:
            import pypdf
            return True
        except ImportError:
            return False
    
    def parse(self, pdf_path: str) -> ParsedDocument:
        """
        Parse a PDF file and extract all content.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            ParsedDocument with all extracted content
        """
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        if not self._pypdf_available:
            raise ImportError("PyPDF is required. Install with: pip install pypdf")
        
        import pypdf
        
        pages: List[PageContent] = []
        all_tables: List[TableData] = []
        full_text_parts: List[str] = []
        
        file_size = path.stat().st_size
        
        with open(pdf_path, 'rb') as f:
            reader = pypdf.PdfReader(f)
            page_count = len(reader.pages)
            
            # Extract metadata
            meta = reader.metadata
            title = meta.title if meta else None
            author = meta.author if meta else None
            
            for i, page in enumerate(reader.pages):
                page_num = i + 1
                text = page.extract_text() or ""
                
                # Attempt basic table detection
                tables = self._detect_tables(text, page_num)
                all_tables.extend(tables)
                
                page_content = PageContent(
                    page_number=page_num,
                    text=text,
                    tables=tables,
                    has_images=bool(page.images) if hasattr(page, 'images') else False
                )
                pages.append(page_content)
                full_text_parts.append(f"--- Page {page_num} ---\n{text}")
        
        full_text = "\n\n".join(full_text_parts)
        
        metadata = PDFMetadata(
            filename=path.name,
            page_count=page_count,
            total_characters=len(full_text),
            file_size_bytes=file_size,
            title=title,
            author=author
        )
        
        return ParsedDocument(
            metadata=metadata,
            pages=pages,
            full_text=full_text,
            tables=all_tables
        )
    
    def _detect_tables(self, text: str, page_number: int) -> List[TableData]:
        """
        Simple heuristic-based table detection.
        
        Looks for patterns that suggest tabular data:
        - Lines with multiple tab/space separations
        - Repeated column-like structures
        """
        tables = []
        lines = text.split('\n')
        
        # Look for lines with consistent column separators
        potential_table_rows = []
        
        for line in lines:
            # Check if line has multiple columns (tabs or multiple spaces)
            if '\t' in line or '  ' in line:
                # Split by tabs or multiple spaces
                cells = re.split(r'\t+|\s{2,}', line.strip())
                if len(cells) >= 2:
                    potential_table_rows.append(cells)
                elif potential_table_rows:
                    # End of potential table
                    if len(potential_table_rows) >= 2:
                        table = TableData(
                            page_number=page_number,
                            headers=potential_table_rows[0] if potential_table_rows else [],
                            rows=potential_table_rows[1:] if len(potential_table_rows) > 1 else []
                        )
                        tables.append(table)
                    potential_table_rows = []
        
        # Handle remaining rows
        if len(potential_table_rows) >= 2:
            table = TableData(
                page_number=page_number,
                headers=potential_table_rows[0],
                rows=potential_table_rows[1:]
            )
            tables.append(table)
        
        return tables


class PerceptionLayer:
    """
    Main perception layer that handles all input processing.
    
    Responsibilities:
    - PDF parsing and text extraction
    - Storing parsed content in shared memory
    - Providing formatted context for downstream agents
    """
    
    def __init__(self):
        self.parser = PDFParser()
        self._document_cache: Dict[str, ParsedDocument] = {}
    
    def process_document(self, pdf_path: str, use_cache: bool = True) -> ParsedDocument:
        """
        Process a PDF document through the perception layer.
        
        Args:
            pdf_path: Path to the PDF file
            use_cache: Whether to use cached results
            
        Returns:
            ParsedDocument with all extracted content
        """
        cache_key = os.path.abspath(pdf_path)
        
        if use_cache and cache_key in self._document_cache:
            return self._document_cache[cache_key]
        
        parsed = self.parser.parse(pdf_path)
        self._document_cache[cache_key] = parsed
        
        return parsed
    
    def get_llm_context(self, pdf_path: str) -> str:
        """
        Get formatted context string suitable for LLM input.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Formatted string with document content
        """
        parsed = self.process_document(pdf_path)
        return parsed.get_context_string()
    
    def clear_cache(self):
        """Clear the document cache."""
        self._document_cache.clear()


# Convenience function for quick parsing
def parse_pdf(pdf_path: str) -> ParsedDocument:
    """
    Quick function to parse a PDF.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        ParsedDocument with extracted content
    """
    layer = PerceptionLayer()
    return layer.process_document(pdf_path)
