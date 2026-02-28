"""Dual Layer injection method - Visual overlay using \\duallayerbox."""
import re
import logging
from typing import Dict, List, Any, Tuple, Optional
from .base_injector import BaseInjector
from ..models.perturbation import PerturbationMapping, Question
from ..latex_parser import extract_question_stem_from_latex

logger = logging.getLogger(__name__)


class DualLayerInjector(BaseInjector):
    """Applies visual overlay using dual layer box macro."""
    
    def __init__(self, config=None):
        """
        Initialize Dual Layer injector.
        
        Args:
            config: Configuration object (optional)
        """
        super().__init__()
        self.config = config
    
    MACRO_DEFINITION = r"""
% --- latex-dual-layer macros (auto-generated) ---
\newlength{\dlboxwidth}
\newlength{\dlboxheight}
\newlength{\dlboxdepth}
\newcommand{\duallayerbox}[2]{%
  \begingroup
  \settowidth{\dlboxwidth}{\strut #1}%
  \settoheight{\dlboxheight}{\strut #1}%
  \settodepth{\dlboxdepth}{\strut #1}%
  \ifdim\dlboxwidth=0pt
    \settowidth{\dlboxwidth}{#2}%
  \fi
  \raisebox{0pt}[\dlboxheight][\dlboxdepth]{%
    \makebox[\dlboxwidth][l]{\resizebox{\dlboxwidth}{!}{\strut #2}}%
  }%
  \endgroup
}
% --- end latex-dual-layer macros ---
""".strip()
    
    PACKAGE_DEPENDENCIES = ("graphicx", "calc", "xcolor")
    
    def inject(
        self,
        tex_content: str,
        perturbations: List[PerturbationMapping],
        questions: List[Question]
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Apply dual layer visual overlay to LaTeX.
        
        Args:
            tex_content: Original LaTeX content
            perturbations: List of perturbation mappings
            questions: List of question data
        
        Returns:
            Tuple of (modified_tex, metadata)
        """
        mutated_tex = tex_content
        
        # Add required packages
        mutated_tex = self._ensure_packages(mutated_tex)
        
        # Add dual layer macros
        if "\\duallayerbox" not in mutated_tex:
            mutated_tex = self._insert_in_preamble(mutated_tex, self.MACRO_DEFINITION)
        
        # Apply replacements
        replacements = []
        metadata_replacements = []
        
        for question in questions:
            question_number = question.question_number
            
            if not question_number:
                logger.warning(f"[DualLayerInjector] Skipping question with no question_number")
                continue
            
            # Use only the FIRST perturbation per question to avoid overlapping replacements
            # Multiple perturbations (k=3) would create overlapping/adjacent replacements
            # that cause malformed LaTeX. For dual-layer, we only need one replacement per question.
            question_perturbations = question.perturbations
            
            if not question_perturbations:
                logger.warning(f"[DualLayerInjector] Question {question_number}: No perturbations available")
                continue
            
            logger.debug(f"[DualLayerInjector] Question {question_number}: Processing {len(question_perturbations)} perturbations")
            
            # Check config to see if multiple perturbations are allowed
            allow_multiple = self.config.experimental.dual_layer_allow_multiple_perturbations if self.config else False
            
            if allow_multiple:
                # Process all perturbations (may cause overlaps - use with caution)
                perturbations_to_process = question_perturbations
            else:
                # Use only the first perturbation (default, safe)
                perturbations_to_process = [question_perturbations[0]]
            
            # Get latex_stem_text from first perturbation or question (shared for all perturbations)
            latex_stem_text = None
            if perturbations_to_process:
                latex_stem_text = perturbations_to_process[0].latex_stem_text or ''
            if not latex_stem_text:
                latex_stem_text = question.latex_stem_text or question.stem_text or ''
            
            # Find latex_stem_text in LaTeX (this should match exactly)
            logger.debug(f"[DualLayerInjector] Question {question_number}: Searching for stem text in LaTeX")
            stem_pos = self._find_question_stem_in_tex(mutated_tex, latex_stem_text)
            if not stem_pos:
                # Try with "True or False: " prefix
                prefixed_stem = f"True or False: {latex_stem_text}"
                stem_pos = self._find_question_stem_in_tex(mutated_tex, prefixed_stem)
                if stem_pos:
                    # Adjust to skip the prefix
                    prefix_len = len("True or False: ")
                    stem_pos = (stem_pos[0] + prefix_len, stem_pos[1])
                    logger.debug(f"[DualLayerInjector] Question {question_number}: Found stem with prefix, adjusted position")
            
            # If still not found, try extracting directly from LaTeX by question number
            # This handles cases where LLM-generated latex_stem_text is incorrect
            if not stem_pos:
                logger.debug(f"[DualLayerInjector] Question {question_number}: JSON latex_stem_text not found, extracting from LaTeX by question number")
                extracted_stem = extract_question_stem_from_latex(mutated_tex, question_number)
                if extracted_stem:
                    logger.info(f"[DualLayerInjector] Question {question_number}: Extracted stem from LaTeX: {extracted_stem[:50]}...")
                    # Try to find the extracted stem in the LaTeX
                    stem_pos = self._find_question_stem_in_tex(mutated_tex, extracted_stem)
                    if stem_pos:
                        latex_stem_text = extracted_stem  # Update to use the correct stem text
                        logger.info(f"[DualLayerInjector] Question {question_number}: Successfully matched extracted stem")
                    else:
                        # Try with "True or False: " prefix
                        prefixed_extracted = f"True or False: {extracted_stem}"
                        stem_pos = self._find_question_stem_in_tex(mutated_tex, prefixed_extracted)
                        if stem_pos:
                            prefix_len = len("True or False: ")
                            stem_pos = (stem_pos[0] + prefix_len, stem_pos[1])
                            latex_stem_text = extracted_stem
                            logger.info(f"[DualLayerInjector] Question {question_number}: Successfully matched extracted stem with prefix")
            
            if not stem_pos:
                logger.warning(f"[DualLayerInjector] Question {question_number}: Could not find stem text in LaTeX (tried JSON value and extraction): {latex_stem_text[:50] if latex_stem_text else 'None'}...")
                continue
            
            logger.debug(f"[DualLayerInjector] Question {question_number}: Found stem at position {stem_pos}")
            
            stem_start, stem_end = stem_pos
            
            # Process each perturbation (usually just one)
            for perturbation in perturbations_to_process:
                original_substring = perturbation.original_substring
                replacement_substring = perturbation.replacement_substring
                start_pos = perturbation.start_pos
                end_pos = perturbation.end_pos
                
                if not original_substring or not replacement_substring:
                    continue
                
                # Use positions from perturbation (relative to latex_stem_text)
                # Verify the positions are valid
                if start_pos >= 0 and end_pos > start_pos and end_pos <= len(latex_stem_text):
                    # Use exact positions from perturbation
                    abs_start = stem_start + start_pos
                    abs_end = stem_start + end_pos
                    
                    # Verify the substring matches
                    actual_substring = mutated_tex[abs_start:abs_end]
                    if actual_substring != original_substring:
                        # Try to find it manually if positions don't match
                        stem_in_tex = mutated_tex[stem_start:stem_end]
                        substring_index = stem_in_tex.find(original_substring)
                        if substring_index != -1:
                            abs_start = stem_start + substring_index
                            abs_end = abs_start + len(original_substring)
                        else:
                            continue
                else:
                    # Fallback: find substring manually
                    stem_in_tex = mutated_tex[stem_start:stem_end]
                    substring_index = stem_in_tex.find(original_substring)
                    if substring_index == -1:
                        # Try normalized search
                        normalized_stem = re.sub(r'\s+', ' ', stem_in_tex)
                        normalized_orig = re.sub(r'\s+', ' ', original_substring)
                        substring_index = normalized_stem.find(normalized_orig)
                        if substring_index != -1:
                            # Approximate position
                            substring_index = stem_in_tex.find(original_substring[:5]) if len(original_substring) >= 5 else -1
                    
                    # If not found in stem, try searching in options (for option-level substitutions)
                    if substring_index == -1:
                        # Find the options section (nested enumerate after the stem)
                        # Look for \begin{enumerate} after the stem
                        nested_begin = mutated_tex.find('\\begin{enumerate}', stem_end)
                        if nested_begin != -1 and nested_begin < stem_end + 200:  # Options should be close
                            # Find matching \end{enumerate} for this nested enumerate
                            # Need to track depth to find the correct closing
                            depth = 1
                            search_pos = nested_begin + len('\\begin{enumerate}')
                            nested_end = -1
                            
                            while search_pos < len(mutated_tex) and depth > 0:
                                next_begin = mutated_tex.find('\\begin{enumerate}', search_pos)
                                next_end = mutated_tex.find('\\end{enumerate}', search_pos)
                                
                                if next_end == -1:
                                    break
                                
                                if next_begin != -1 and next_begin < next_end:
                                    depth += 1
                                    search_pos = next_begin + len('\\begin{enumerate}')
                                else:
                                    depth -= 1
                                    if depth == 0:
                                        nested_end = next_end
                                        break
                                    search_pos = next_end + len('\\end{enumerate}')
                            
                            if nested_end != -1:
                                options_text = mutated_tex[nested_begin:nested_end]
                                # Search in options
                                options_index = options_text.find(original_substring)
                                if options_index != -1:
                                    abs_start = nested_begin + options_index
                                    abs_end = abs_start + len(original_substring)
                                    logger.info(f"[DualLayerInjector] Question {question_number}: Found '{original_substring}' in options section")
                                else:
                                    # Try normalized search in options
                                    normalized_options = re.sub(r'\s+', ' ', options_text)
                                    normalized_orig = re.sub(r'\s+', ' ', original_substring)
                                    normalized_index = normalized_options.find(normalized_orig)
                                    if normalized_index != -1:
                                        # Find approximate position in original text
                                        # Count characters in normalized text up to normalized_index
                                        char_count = 0
                                        orig_pos = 0
                                        for i, char in enumerate(options_text):
                                            if char.isspace():
                                                # Skip multiple spaces
                                                while orig_pos < len(options_text) and options_text[orig_pos].isspace():
                                                    orig_pos += 1
                                            else:
                                                char_count += 1
                                                if char_count > normalized_index:
                                                    break
                                                orig_pos += 1
                                        
                                        # Try to find the substring starting from approximate position
                                        search_start = max(0, orig_pos - 10)
                                        options_index = options_text.find(original_substring, search_start)
                                        if options_index != -1:
                                            abs_start = nested_begin + options_index
                                            abs_end = abs_start + len(original_substring)
                                            logger.info(f"[DualLayerInjector] Question {question_number}: Found '{original_substring}' in options (normalized)")
                                        else:
                                            continue
                                    else:
                                        continue
                            else:
                                continue
                        else:
                            continue
                    else:
                        # Found in stem
                        abs_start = stem_start + substring_index
                        abs_end = abs_start + len(original_substring)
                
                # Create dual layer replacement using \duallayerbox macro
                # Format: \duallayerbox{original}{replacement}
                # The macro displays #2 (replacement) visually
                # Then image overlays from original PDF will cover it with #1 (original)
                # Result: Visual shows original, text layer has replacement
                escaped_original = self._escape_tex(original_substring)
                escaped_replacement = self._escape_tex(replacement_substring)
                
                replacement = f"\\duallayerbox{{{escaped_original}}}{{{escaped_replacement}}}"
                
                logger.info(f"[DualLayerInjector] Question {question_number}: Replacement '{original_substring}' → '{replacement_substring}' at position ({abs_start}, {abs_end})")
                replacements.append((abs_start, abs_end, replacement))
                metadata_replacements.append({
                    "question_number": question_number,
                    "original": original_substring,
                    "replacement": replacement_substring,
                    "position": (abs_start, abs_end)
                })
        
        # Remove duplicate replacements (same position and content)
        seen_replacements = set()
        unique_replacements = []
        for start, end, replacement in replacements:
            replacement_key = (start, end, replacement)
            if replacement_key not in seen_replacements:
                seen_replacements.add(replacement_key)
                unique_replacements.append((start, end, replacement))
        
        # Sort by start position (descending) to apply in reverse order
        unique_replacements.sort(key=lambda x: x[0], reverse=True)
        
        logger.info(f"[DualLayerInjector] Total unique replacements: {len(unique_replacements)}")
        
        # Check for overlapping replacements and skip them
        final_replacements = []
        for start, end, replacement in unique_replacements:
            # Check if this replacement overlaps with any already processed one
            overlaps = False
            for prev_start, prev_end, _ in final_replacements:
                # Check if ranges overlap: (start < prev_end) and (end > prev_start)
                if start < prev_end and end > prev_start:
                    overlaps = True
                    break
            
            if not overlaps:
                final_replacements.append((start, end, replacement))
        
        logger.info(f"[DualLayerInjector] Final replacements after overlap check: {len(final_replacements)}")
        
        # Apply replacements in reverse order to preserve positions
        for start, end, replacement in final_replacements:
            mutated_tex = mutated_tex[:start] + replacement + mutated_tex[end:]
        
        logger.info(f"[DualLayerInjector] Injection complete: {len(final_replacements)} replacements applied")
        
        metadata = {
            "replacements_count": len(metadata_replacements),
            "replacements": metadata_replacements,
            "method": "dual_layer",
            "final_replacements_count": len(final_replacements)
        }
        
        return mutated_tex, metadata
    
    def _ensure_packages(self, tex: str) -> str:
        """Ensure required packages are included."""
        for package in self.PACKAGE_DEPENDENCIES:
            if f"\\usepackage{{{package}}}" not in tex:
                tex = self._insert_in_preamble(tex, f"\\usepackage{{{package}}}")
        return tex

