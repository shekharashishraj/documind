"""PDF-level dual layer using image overlays (like reference implementation)."""
import logging
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

logger = logging.getLogger(__name__)


def apply_image_overlay_dual_layer(
    original_pdf_path: Path,
    compiled_pdf_path: Path,
    output_pdf_path: Path,
    mappings: List[Dict[str, Any]],
    search_pdf_path: Optional[Path] = None
) -> bool:
    """
    Apply dual-layer effect using image overlays.
    
    Process:
    1. Compiled PDF has replacement text (from \duallayerbox macro)
    2. Extract image snapshots from original PDF at mapping positions
    3. Overlay these images on compiled PDF to show original text visually
    4. Result: Visual shows original, text layer has replacement
    
    Args:
        original_pdf_path: Original PDF (before LaTeX changes) - source for image overlays
        compiled_pdf_path: Compiled PDF (with \duallayerbox macros) - target for overlays
        output_pdf_path: Output PDF path
        mappings: List of mappings with 'original', 'replacement', and geometry info
        search_pdf_path: Fallback PDF to search for text if geometry missing
    
    Returns:
        True if successful, False otherwise
    """
    if not FITZ_AVAILABLE:
        return False
    
    if not compiled_pdf_path.exists():
        logger.error(f"[DualLayerOverlay] Compiled PDF not found: {compiled_pdf_path}")
        return False
    
    logger.info(f"[DualLayerOverlay] Starting overlay process")
    logger.info(f"[DualLayerOverlay] Compiled PDF: {compiled_pdf_path}")
    logger.info(f"[DualLayerOverlay] Original PDF: {original_pdf_path}")
    logger.info(f"[DualLayerOverlay] Search PDF: {search_pdf_path}")
    logger.info(f"[DualLayerOverlay] Output PDF: {output_pdf_path}")
    logger.info(f"[DualLayerOverlay] Mappings count: {len(mappings)}")
    
    try:
        # Open compiled PDF (target for overlays)
        compiled_doc = fitz.open(str(compiled_pdf_path))
        logger.info(f"[DualLayerOverlay] Compiled PDF opened: {len(compiled_doc)} pages")
        
        # Open original PDF (source for image overlays)
        original_doc = None
        original_source = None
        if original_pdf_path and original_pdf_path.exists():
            original_doc = fitz.open(str(original_pdf_path))
            original_source = "original_pdf_path"
            logger.info(f"[DualLayerOverlay] Original PDF opened from original_pdf_path: {len(original_doc)} pages")
        elif search_pdf_path and search_pdf_path.exists():
            original_doc = fitz.open(str(search_pdf_path))
            original_source = "search_pdf_path (fallback)"
            logger.warning(f"[DualLayerOverlay] Using search_pdf_path as fallback (this means original PDF not found)")
            logger.info(f"[DualLayerOverlay] Fallback PDF opened: {len(original_doc)} pages")
        
        if not original_doc:
            # No original PDF, just copy compiled
            logger.warning(f"[DualLayerOverlay] WARNING: No original PDF found! Overlay cannot be applied.")
            logger.warning(f"[DualLayerOverlay] Original PDF path exists: {original_pdf_path.exists() if original_pdf_path else False}")
            logger.warning(f"[DualLayerOverlay] Search PDF path exists: {search_pdf_path.exists() if search_pdf_path else False}")
            logger.warning(f"[DualLayerOverlay] Copying compiled PDF without overlay - replacement text will be visible!")
            compiled_doc.save(str(output_pdf_path))
            compiled_doc.close()
            return True
        
        # Collect overlay targets by page
        overlay_targets: Dict[int, List[Dict[str, Any]]] = {}
        for mapping in mappings:
            original = mapping.get('original', '')
            replacement = mapping.get('replacement', '')
            if not original or not replacement:
                continue
            
            # Try to get geometry from mapping
            page_index = mapping.get('page_index')
            rect = _get_rect_from_mapping(mapping, original_doc, page_index)
            
            if rect and not rect.is_empty:
                # Determine page index from rect or mapping
                if page_index is None:
                    # Try to find which page contains this rect
                    for pidx in range(len(original_doc)):
                        page_rect = original_doc[pidx].rect
                        if page_rect.contains(rect) or page_rect.intersects(rect):
                            page_index = pidx
                            break
                    if page_index is None:
                        page_index = 0  # Default to first page
                
                # Pad rect more generously for better coverage of text
                padded_rect = fitz.Rect(
                    rect.x0 - 10, rect.y0 - 5,
                    rect.x1 + 10, rect.y1 + 5
                )
                
                if page_index not in overlay_targets:
                    overlay_targets[page_index] = []
                
                overlay_targets[page_index].append({
                    'rect': padded_rect,
                    'original': original,
                    'replacement': replacement
                })
        
        # Apply full-page image overlays (safest approach)
        # For each page: take full page image from original PDF and overlay on compiled PDF
        # This ensures complete coverage without needing precise geometry
        overlays_applied = 0
        logger.info(f"[DualLayerOverlay] Applying full-page image overlays from {original_source}")
        for page_index in range(len(compiled_doc)):
            page = compiled_doc[page_index]
            original_page = original_doc[page_index] if page_index < len(original_doc) else None
            
            if not original_page:
                logger.warning(f"[DualLayerOverlay] Page {page_index + 1}: No corresponding page in original PDF")
                continue
            
            try:
                # Extract full page image from original PDF
                # This captures the entire page as an image
                logger.debug(f"[DualLayerOverlay] Page {page_index + 1}: Extracting pixmap from original PDF")
                pix = original_page.get_pixmap(
                    matrix=fitz.Matrix(2.0, 2.0),  # ~144 DPI (72 * 2.0)
                    alpha=False
                )
                
                # Overlay full page image on compiled PDF
                # This covers all text with original visual appearance
                # The text layer underneath still has the replacement text (from \duallayerbox)
                logger.debug(f"[DualLayerOverlay] Page {page_index + 1}: Overlaying image on compiled PDF")
                page.insert_image(
                    page.rect,  # Full page rectangle
                    stream=pix.tobytes("png"),
                    keep_proportion=True,
                    overlay=True  # CRITICAL: Overlay on top of text layer
                )
                overlays_applied += 1
                logger.info(f"[DualLayerOverlay] Page {page_index + 1}: Overlay applied successfully")
            
            except Exception as e:
                # Log error but continue with other pages
                logger.error(f"[DualLayerOverlay] Page {page_index + 1}: Failed to apply overlay: {e}", exc_info=True)
                continue
        
        logger.info(f"[DualLayerOverlay] Total overlays applied: {overlays_applied}/{len(compiled_doc)} pages")
        
        # Save output
        output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"[DualLayerOverlay] Saving final PDF to: {output_pdf_path}")
        compiled_doc.save(str(output_pdf_path))
        
        compiled_doc.close()
        if original_doc:
            original_doc.close()
        
        logger.info(f"[DualLayerOverlay] Overlay process completed successfully")
        return True
    
    except Exception as e:
        logger.error(f"[DualLayerOverlay] Overlay process failed: {e}", exc_info=True)
        if 'compiled_doc' in locals() and compiled_doc:
            compiled_doc.close()
        if 'original_doc' in locals() and original_doc:
            original_doc.close()
        return False


def _get_rect_from_mapping(
    mapping: Dict[str, Any],
    pdf_doc: fitz.Document,
    page_index: Optional[int]
) -> Optional[fitz.Rect]:
    """Extract rectangle from mapping, with fallback to PDF search."""
    # Try bbox first
    bbox = mapping.get('bbox') or mapping.get('selection_bbox')
    if bbox:
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            try:
                rect = fitz.Rect(bbox)
                if rect.get_area() > 0:
                    return rect
            except Exception:
                pass
    
    # Try selection_rect
    selection_rect = mapping.get('selection_rect')
    if isinstance(selection_rect, dict):
        try:
            rect = fitz.Rect(
                selection_rect.get('x0', 0),
                selection_rect.get('y0', 0),
                selection_rect.get('x1', 0),
                selection_rect.get('y1', 0)
            )
            if rect.get_area() > 0:
                return rect
        except Exception:
            pass
    
    # Fallback: search PDF for text (try all pages if page_index not specified)
    if pdf_doc:
        original_text = mapping.get('original', '').strip()
        if original_text:
            try:
                pages_to_search = [page_index] if page_index is not None else range(len(pdf_doc))
                for pidx in pages_to_search:
                    if pidx >= len(pdf_doc):
                        continue
                    page = pdf_doc[pidx]
                    
                    # Try multiple search strategies
                    search_patterns = [
                        original_text,  # Exact match
                        f"is '{original_text}'",  # With context
                        f"'{original_text}'",  # With quotes
                    ]
                    
                    # Also try without quotes/apostrophes
                    if "'" in original_text or '"' in original_text:
                        clean_text = original_text.replace("'", "").replace('"', '')
                        if clean_text:
                            search_patterns.append(clean_text)
                    
                    for pattern in search_patterns:
                        hits = page.search_for(pattern)
                        # Limit to first 5 hits
                        for hit in hits[:5]:
                            # Get text around the hit to verify
                            expanded = fitz.Rect(
                                max(0, hit.x0 - 30), max(0, hit.y0 - 3),
                                min(page.rect.x1, hit.x1 + 30), min(page.rect.y1, hit.y1 + 3)
                            )
                            context = page.get_textbox(expanded)
                            
                            # Verify this is likely our target
                            context_clean = context.lower().replace("'", "").replace('"', '').replace('\n', ' ')
                            original_clean = original_text.lower().replace("'", "").replace('"', '')
                            if original_clean in context_clean:
                                # Expand rect for better coverage
                                return fitz.Rect(
                                    hit.x0 - 8, hit.y0 - 3,
                                    hit.x1 + 8, hit.y1 + 3
                                )
                    
                    # For multi-word text, try different search strategies
                    words = original_text.split()
                    if len(words) >= 2:
                        # Strategy 1: Try last 2 words (often more unique, e.g., "link layer")
                        if len(words) >= 2:
                            last_two = ' '.join(words[-2:])
                            hits = page.search_for(last_two)
                            for hit in hits[:10]:  # Check more hits
                                # Expand significantly to include all words
                                # For "Data link layer", "link layer" is at ~520-540, "Data" is at ~492
                                expanded = fitz.Rect(
                                    hit.x0 - 100, hit.y0 - 3,  # Extend left to catch "Data"
                                    hit.x1 + 20, hit.y1 + 20   # Extend down for next line if needed
                                )
                                context = page.get_textbox(expanded)
                                context_lower = context.lower()
                                
                                # Simple check: do all words from original appear in context?
                                # Be lenient - just check if words are present
                                words_lower = [w.lower() for w in words]
                                words_in_context = [w for w in words_lower if w in context_lower]
                                
                                # If most words are found, consider it a match
                                if len(words_in_context) >= len(words) - 1:  # Allow 1 missing word
                                    return fitz.Rect(
                                        expanded.x0 - 5, expanded.y0 - 3,
                                        expanded.x1 + 5, expanded.y1 + 3
                                    )
                        
                        # Strategy 2: Try first 2 words, then expand
                        first_two = ' '.join(words[:2])
                        first_hits = page.search_for(first_two)
                        for fhit in first_hits[:5]:
                            # Expand to include remaining words
                            expanded_rect = fitz.Rect(
                                fhit.x0 - 5,
                                fhit.y0 - 2,
                                fhit.x1 + 80,  # Extend right
                                fhit.y1 + 18   # Extend down one line
                            )
                            context = page.get_textbox(expanded_rect)
                            context_clean = context.lower().replace("'", "").replace('"', '').replace('\n', ' ')
                            original_clean = original_text.lower().replace("'", "").replace('"', '')
                            if original_clean in context_clean or all(w.lower() in context_clean for w in words):
                                return fitz.Rect(
                                    expanded_rect.x0 - 5, expanded_rect.y0 - 3,
                                    expanded_rect.x1 + 5, expanded_rect.y1 + 3
                                )
                    
                    # Try word-by-word search for multi-word text
                    words = original_text.split()
                    if len(words) >= 2:
                        # Try different combinations
                        search_combinations = [
                            ' '.join(words[-2:]),  # Last 2 words
                            ' '.join(words[-3:]) if len(words) >= 3 else ' '.join(words),  # Last 3 words
                            ' '.join(words[:2]),  # First 2 words
                            words[-1],  # Last word only
                        ]
                        
                        for search_text in search_combinations:
                            hits = page.search_for(search_text)
                            for hit in hits[:10]:  # Check more hits
                                expanded = fitz.Rect(
                                    max(0, hit.x0 - 100), max(0, hit.y0 - 5),
                                    min(page.rect.x1, hit.x1 + 100), min(page.rect.y1, hit.y1 + 5)
                                )
                                context = page.get_textbox(expanded)
                                # Check if original text appears in context (case-insensitive, flexible)
                                context_lower = context.lower().replace("'", "").replace('"', '')
                                original_lower = original_text.lower().replace("'", "").replace('"', '')
                                if original_lower in context_lower:
                                    # Found it! Expand rect to cover the full text
                                    return fitz.Rect(
                                        hit.x0 - 10, hit.y0 - 4,
                                        hit.x1 + 10, hit.y1 + 4
                                    )
            except Exception:
                pass
    
    return None

