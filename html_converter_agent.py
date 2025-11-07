"""
HTML Converter Agent

Converts markdown intelligence reports to professional, self-contained HTML
following Bloomberg/FT journalism best practices with clean typography,
inline data cards, sidebar insights, and minimal STI branding.
"""

import html
import json
import os
import re
import logging
import traceback
from datetime import datetime
from typing import Dict, List, Any
from pathlib import Path

# Import STIConfig at module level for image generation
try:
    from config import STIConfig
except ImportError:
    # Logger not yet initialized, use basic print or defer warning
    STIConfig = None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HTMLConverterAgent:
    """
    Converts markdown intelligence reports to professional HTML format
    following journalism best practices for readability and presentation.
    """
    
    def __init__(self, template_path: str = "templates/report_template.html"):
        self.template_path = template_path
        self.ensure_template_exists()
    
    def ensure_template_exists(self):
        """Ensure the template directory and file exist"""
        template_dir = Path(self.template_path).parent
        template_dir.mkdir(exist_ok=True)
        
        if not os.path.exists(self.template_path):
            logger.warning(f"Template not found at {self.template_path}, will create basic template")
            self._create_basic_template()

    def _load_json_artifact(self, report_dir: str, filename: str) -> Dict[str, Any]:
        if not report_dir:
            return {}
        path = Path(report_dir) / filename
        if not path.exists():
            return {}
        try:
            with path.open('r', encoding='utf-8') as handle:
                return json.load(handle)
        except Exception as exc:
            logger.warning(f"Failed to load artifact {filename}: {exc}")
            return {}

    def _load_evidence_ledger(self, report_dir: str) -> Dict[str, Any]:
        ledger = self._load_json_artifact(report_dir, "evidence_ledger.json")
        if ledger:
            logger.info("Loaded evidence ledger with %d claims", len(ledger.get('claims', [])))
        return ledger
    
    def convert(self, markdown_report: str, json_ld: Dict[str, Any],
                metadata: Dict[str, Any], report_dir: str = None) -> str:
        """
        Convert markdown report to HTML
        
        Args:
            markdown_report: The markdown intelligence report
            json_ld: JSON-LD structured data
            metadata: Report metadata
            
        Returns:
            Self-contained HTML string
        """
        try:
            metadata = dict(metadata or {})
            # Detect intent (thesis vs market)
            agent_stats = metadata.get('agent_stats', {})
            intent = agent_stats.get('intent') or metadata.get('intent')
            is_thesis = (intent == 'theory')

            ledger = self._load_evidence_ledger(report_dir)
            adversarial = self._load_json_artifact(report_dir, "adversarial.json")
            playbooks = self._load_json_artifact(report_dir, "playbooks.json")
            quant_patch = self._load_json_artifact(report_dir, "vignette_quant_patch.json")

            if ledger:
                metadata['evidence_ledger'] = ledger
            if adversarial:
                metadata['adversarial_findings'] = adversarial
            if playbooks:
                metadata['decision_playbooks'] = playbooks
            if quant_patch:
                metadata['quant_patch'] = quant_patch

            # If thesis, switch to thesis template
            if is_thesis:
                self.template_path = "templates/report_thesis.html"
                self.ensure_thesis_template()

            # Parse markdown sections (pass intent for thesis handling)
            parsed_sections = self._parse_markdown_sections(markdown_report, json_ld, metadata, is_thesis=is_thesis)
            
            # Extract additional data from JSON-LD
            json_data = self._extract_json_ld_data(json_ld, len(parsed_sections.get('sources', [])))
            
            # Combine parsed and JSON data
            template_data = {**parsed_sections, **json_data, **metadata}
            # Surface horizon and hybrid flags from agent_stats for UI injection
            try:
                _as = metadata.get('agent_stats', {})
                template_data['horizon'] = _as.get('horizon', 'Near-term')
                template_data['hybrid_thesis_anchored'] = _as.get('hybrid_thesis_anchored', False)
                # Use validated_sources_count from agent_stats if available (matches manifest)
                validated_count = _as.get('validated_sources_count')
                if validated_count is not None:
                    template_data['sources_count'] = validated_count
                else:
                    # Fallback to parsed sources count
                    template_data['sources_count'] = len(parsed_sections.get('sources', []))
            except Exception:
                template_data['horizon'] = template_data.get('horizon', 'Near-term')
                template_data['hybrid_thesis_anchored'] = template_data.get('hybrid_thesis_anchored', False)
                template_data['sources_count'] = len(parsed_sections.get('sources', []))

            template_data['evidence_ledger'] = ledger
            template_data['adversarial_findings'] = adversarial
            template_data['decision_playbooks'] = playbooks
            template_data['quant_patch'] = quant_patch
            template_data['confidence_breakdown'] = agent_stats.get('confidence_breakdown') or metadata.get('confidence_breakdown')
            template_data['run_manifest'] = agent_stats.get('run_manifest') or metadata.get('run_manifest')
            template_data['provenance_banner'] = self._render_provenance_banner(template_data)
            template_data['confidence_dials'] = self._render_confidence_dials(template_data)
            template_data['evidence_ledger_html'] = self._render_evidence_ledger(ledger)
            template_data['adversarial_html'] = self._render_adversarial_section(adversarial)
            template_data['playbooks_html'] = self._render_playbooks(playbooks)
            template_data['quant_patch_html'] = self._render_quant_patch(quant_patch)
            
            # Extract thesis critique scores if available
            if is_thesis:
                thesis_io = metadata.get('agent_stats', {}).get('thesis_io', {})
                critique = thesis_io.get('critique_out', {})
                
                # Extract badge scores from critique (ensure they're properly extracted)
                alignment_score = critique.get('alignment')
                theory_depth_score = critique.get('theory_depth')
                clarity_score = critique.get('clarity')
                
                # Convert badges from 0-1 scale to 0-10 scale and ensure never "N/A"
                # Compute fallback values if None
                if alignment_score is None or not isinstance(alignment_score, (int, float)):
                    alignment_score = 6.0  # Default to 6/10 = 0.6
                else:
                    alignment_score = max(0.0, min(10.0, alignment_score * 10.0))  # Convert 0-1 to 0-10
                
                if theory_depth_score is None or not isinstance(theory_depth_score, (int, float)):
                    theory_depth_score = 6.0  # Default to 6/10 = 0.6
                else:
                    theory_depth_score = max(0.0, min(10.0, theory_depth_score * 10.0))  # Convert 0-1 to 0-10
                
                if clarity_score is None or not isinstance(clarity_score, (int, float)):
                    clarity_score = 7.0  # Default to 7/10 = 0.7
                else:
                    clarity_score = max(0.0, min(10.0, clarity_score * 10.0))  # Convert 0-1 to 0-10
                
                # Format as strings with 1 decimal place (0-10 scale)
                template_data['thesis_alignment'] = f"{alignment_score:.1f}"
                template_data['thesis_theory_depth'] = f"{theory_depth_score:.1f}"
                template_data['thesis_clarity'] = f"{clarity_score:.1f}"
                
                # Extract full publication rubric if available
                publication_rubric = thesis_io.get('publication_rubric', {})
                if publication_rubric:
                    template_data['publication_rubric'] = publication_rubric
                    template_data['rubric_total_score'] = publication_rubric.get('total_score', 0.0)
                else:
                    template_data['publication_rubric'] = {}
                    template_data['rubric_total_score'] = 0.0
                
                # Extract diversity score
                template_data['diversity_score'] = thesis_io.get('diversity_score', 1.0)
                
                # Derive anchor_status from ledger coverage (not domain heuristics)
                anchor_status = None
                if ledger and ledger.get('anchor_coverage') is not None:
                    # Use ledger's anchor_coverage metric
                    anchor_coverage = float(ledger.get('anchor_coverage', 0.0))
                    anchor_coverage_min = getattr(STIConfig, 'ANCHOR_COVERAGE_MIN', 0.70)
                    if anchor_coverage >= anchor_coverage_min:
                        anchor_status = "Anchored"
                    elif anchor_coverage >= 0.30:  # Partial coverage
                        anchor_status = "Anchor-Sparse"
                    else:
                        anchor_status = "Anchor-Absent"
                else:
                    # Fallback: try metadata or domain-based computation
                    anchor_status = thesis_io.get('anchor_status')
                    if not anchor_status:
                        # Last resort: compute from sources (domain heuristics)
                        sources = parsed_sections.get('sources', [])
                        if sources:
                            anchor_domains = (
                                getattr(STIConfig, 'THESIS_ANCHOR_DOMAINS', [])
                                if STIConfig else []
                            )
                            anchor_count = sum(
                                1 for s in sources
                                if any(domain in s.get('url', '').lower()
                                       for domain in anchor_domains)
                            )
                            if anchor_count >= 2:
                                anchor_status = "Anchored"
                            elif anchor_count == 1:
                                anchor_status = "Anchor-Sparse"
                            else:
                                anchor_status = "Anchor-Absent"
                        else:
                            anchor_status = "Anchor-Absent"
                template_data['anchor_status'] = anchor_status
                
                # Extract confidence (use playbook formula if available, otherwise fallback)
                thesis_confidence = thesis_io.get('confidence')
                if thesis_confidence is None or not isinstance(thesis_confidence, (int, float)):
                    # Fallback: use existing confidence if available
                    thesis_confidence = template_data.get('confidence', 0.5)
                template_data['thesis_confidence'] = thesis_confidence
                
                # Pre-compute display values (remove Jinja2 conditionals from template)
                thesis_confidence_display = thesis_confidence if thesis_confidence is not None else template_data.get('confidence', 0.5)
                template_data['thesis_confidence_display'] = f"{thesis_confidence_display:.3f}"
                
                rubric_display = f"| Rubric Score: {template_data['rubric_total_score']}/100" if template_data['rubric_total_score'] > 0 else ""
                template_data['rubric_display'] = rubric_display
                
                disclosure_anchor_text = ""
                if anchor_status in ["Anchor-Sparse", "Anchor-Absent"]:
                    disclosure_anchor_text = "Where anchors are scarce, this brief is labeled **Anchor-Absent** and any analogical inferences are explicitly bounded."
                template_data['disclosure_anchor_text'] = disclosure_anchor_text
            else:
                # Default values for market reports (not used, but prevent template errors)
                template_data['thesis_alignment'] = ""
                template_data['thesis_theory_depth'] = ""
                template_data['thesis_clarity'] = ""
                template_data['publication_rubric'] = {}
                template_data['rubric_total_score'] = 0.0
                template_data['diversity_score'] = 1.0
                template_data['anchor_status'] = ""
                template_data['thesis_confidence'] = None
                template_data['thesis_confidence_display'] = "0.500"
                template_data['rubric_display'] = ""
                template_data['disclosure_anchor_text'] = ""
            
            # Load and render template
            html_content = self._render_template(template_data)
            
            # Inject additional metadata
            html_content = self._inject_metadata(html_content, metadata)
            
            # Inject report-type UI (market vs thesis) per journalistic framing
            cfg = self._report_type_config(is_thesis)
            anchor_status = ""
            if is_thesis:
                anchor_status = template_data.get('anchor_status', "")
            html_content = self._inject_report_type_ui(html_content, cfg, is_thesis, anchor_status)
            
            # Generate and inject hero image if enabled and report_dir provided
            logger.debug(f"🔍 Image generation check:")
            logger.debug(f"   - report_dir provided: {report_dir is not None}")
            logger.debug(f"   - STIConfig available: {STIConfig is not None}")
            if report_dir:
                logger.debug(f"   - report_dir value: '{report_dir}'")
            if STIConfig:
                enable_gen = getattr(STIConfig, 'ENABLE_IMAGE_GENERATION', None)
                logger.debug(f"   - ENABLE_IMAGE_GENERATION: {enable_gen}")
            
            asset_gating = agent_stats.get('asset_gating', {}) if isinstance(agent_stats, dict) else {}
            images_enabled = asset_gating.get('images_enabled', True)
            social_enabled = asset_gating.get('social_enabled', True)
            
            # Note: Image generation now works for all reports regardless of anchor status
            # Removed anchor requirement gating to ensure images are generated for every report

            if not images_enabled:
                logger.info("🛑 Image generation skipped by asset gate.")
            elif report_dir and STIConfig and getattr(STIConfig, 'ENABLE_IMAGE_GENERATION', False):
                query = metadata.get('query') or template_data.get('title', 'Technology Intelligence')
                intent = "theory" if is_thesis else "market"
                exec_summary = template_data.get('exec_summary', '')  # Extract exec summary for tailored prompts
                logger.info(f"🎯 Image generation conditions met - proceeding with generation")
                logger.debug(f"   - query: '{query}'")
                logger.debug(f"   - intent: '{intent}'")
                logger.debug(f"   - exec_summary available: {len(exec_summary) > 0} ({len(exec_summary)} chars)")
                html_content = self._generate_and_inject_images(html_content, query, report_dir, intent, exec_summary=exec_summary)
            else:
                reason = []
                if not report_dir:
                    reason.append("report_dir not provided")
                if not STIConfig:
                    reason.append("STIConfig not available")
                elif not getattr(STIConfig, 'ENABLE_IMAGE_GENERATION', False):
                    reason.append("ENABLE_IMAGE_GENERATION is False")
                logger.debug(f"ℹ️ Image generation skipped: {', '.join(reason) if reason else 'unknown reason'}")
            
            return html_content
            
        except Exception as e:
            logger.error(f"Error converting to HTML: {str(e)}")
            logger.debug(f"Full traceback:\n{traceback.format_exc()}")
            return self._create_fallback_html(markdown_report, metadata, report_dir=report_dir)
    
    def _parse_markdown_sections(self, markdown: str, json_ld: Dict[str, Any], 
                                 metadata: Dict[str, Any] = None, is_thesis: bool = False) -> Dict[str, Any]:
        """Parse markdown into structured sections
        
        Args:
            markdown: The markdown report
            json_ld: JSON-LD structured data
            metadata: Report metadata (optional)
            is_thesis: Whether this is a thesis-style report
        """
        sections = {}
        metadata = metadata or {}
        
        # Detect thesis-style markdown format (single # or ## headings like "Abstract", "Executive Summary", "Introduction")
        # Look for common thesis markers: Abstract, Executive Summary, or other academic section patterns
        thesis_format_detected = (
            re.search(r'^(?:#{1,2})\s+Abstract', markdown, re.MULTILINE) is not None or
            re.search(r'^(?:#{1,2})\s+Executive Summary', markdown, re.MULTILINE) is not None or
            re.search(r'^(?:#{1,2})\s+(?:Theory-First|Conceptual Framework|Foundations|Mechanisms|Case Studies|Applications|Limits)', markdown, re.MULTILINE) is not None
        )
        
        # If thesis intent is set, trust it and use thesis parsing (format detection is secondary)
        # This ensures thesis-path reports are parsed correctly even if format detection misses
        if is_thesis:
            return self._parse_thesis_markdown(markdown, json_ld, metadata)
        
        # If not thesis intent but format looks like thesis, still use thesis parsing (fallback)
        if thesis_format_detected:
            logger.warning("Thesis format detected but intent is not 'theory'. Using thesis parsing anyway.")
            return self._parse_thesis_markdown(markdown, json_ld, metadata)
        
        # Otherwise, handle market-style parsing (existing logic)
        # Extract title and apply house style
        title_match = re.search(r'^# (.+)$', markdown, re.MULTILINE)
        raw_title = title_match.group(1) if title_match else "Intelligence Report"
        
        # For thesis reports, prefer query from metadata over first heading
        if is_thesis and metadata.get('query'):
            raw_title = metadata['query']
        elif is_thesis and raw_title == "Abstract":
            # If title is "Abstract", try to get query from metadata
            raw_title = metadata.get('query', raw_title)
        
        sections['title'] = self._apply_house_style_title(raw_title)
        
        # Extract metadata line (clean format) - only the date range part
        metadata_match = re.search(r'^Date range: ([^|]+)', markdown, re.MULTILINE)
        sections['date_range'] = metadata_match.group(1).strip() if metadata_match else ""
        
        
        # Extract executive summary
        exec_summary_match = re.search(r'## Executive Summary\n(.*?)(?=\n## |$)', markdown, re.DOTALL)
        sections['exec_summary'] = exec_summary_match.group(1).strip() if exec_summary_match else ""
        
        # Extract topline
        topline_match = re.search(r'## Topline\n(.*?)(?=\n## |$)', markdown, re.DOTALL)
        sections['topline'] = topline_match.group(1).strip() if topline_match else ""
        
        # Extract signals
        signals_match = re.search(r'## Signals.*?\n(.*?)(?=\n## |$)', markdown, re.DOTALL)
        if signals_match:
            signals_text = signals_match.group(1)
            sections['signals'] = self._parse_signals(signals_text, sections['date_range'])
            sections['signals_html'] = self._render_signal_cards(sections['signals'])
        else:
            sections['signals'] = []
            sections['signals_html'] = ""
        
        # Extract analysis sections with paragraph segmentation
        sections['market_analysis'] = self._segment_into_paragraphs(self._extract_section(markdown, "Market Analysis"))
        sections['tech_deepdive'] = self._segment_into_paragraphs(self._extract_section(markdown, "Technology Deep-Dive"))
        sections['competitive'] = self._segment_into_paragraphs(self._extract_section(markdown, "Competitive Landscape"))

        # Thesis-style mapping: if thesis sections exist, map them into the standard placeholders
        foundations = self._extract_section(markdown, "Foundational Theory") or self._extract_section(markdown, "Foundations")
        formalization = self._extract_section(markdown, "Formalization")
        mechanisms = self._extract_section(markdown, "Mechanisms")
        applications = self._extract_section(markdown, "Applications")
        limits = self._extract_section(markdown, "Limits and Open Questions") or self._extract_section(markdown, "Open Questions and Future Directions")
        synthesis = self._extract_section(markdown, "Synthesis and Current Developments")

        if foundations or mechanisms or applications or limits or synthesis:
            # Build market_analysis from foundational + formalization (or synthesis)
            thesis_market = "\n\n".join(filter(None, [foundations, formalization or synthesis]))
            thesis_tech = "\n\n".join(filter(None, [mechanisms, applications]))
            thesis_comp = limits or ""
            if thesis_market:
                sections['market_analysis'] = self._segment_into_paragraphs(thesis_market)
            if thesis_tech:
                sections['tech_deepdive'] = self._segment_into_paragraphs(thesis_tech)
            if thesis_comp:
                sections['competitive'] = self._segment_into_paragraphs(thesis_comp)

            # Also expose thesis-native fields for a thesis template
            sections['foundations'] = self._segment_into_paragraphs(foundations)
            sections['formalization'] = self._segment_into_paragraphs(formalization)
            sections['mechanisms'] = self._segment_into_paragraphs(mechanisms)
            sections['applications'] = self._segment_into_paragraphs(applications)
            sections['limits'] = self._segment_into_paragraphs(limits)
            sections['synthesis'] = self._segment_into_paragraphs(synthesis)
        
        # Extract lenses with paragraph formatting
        sections['operator_lens'] = self._format_lens_content(self._extract_section(markdown, "Operator Lens"))
        sections['investor_lens'] = self._format_lens_content(self._extract_section(markdown, "Investor Lens"))
        sections['bd_lens'] = self._format_lens_content(self._extract_section(markdown, "BD Lens"))
        
        # Extract sources
        sources_match = re.search(r'## Sources\n(.*?)$', markdown, re.DOTALL)
        if sources_match:
            sources_text = sources_match.group(1)
            
            # Extract raw markdown sections for citation filtering (more reliable than processed HTML)
            # This ensures we catch all [^id] format citations before they're converted to HTML
            raw_market_analysis = self._extract_section(markdown, "Market Analysis")
            raw_tech_deepdive = self._extract_section(markdown, "Technology Deep-Dive")
            raw_competitive = self._extract_section(markdown, "Competitive Landscape")
            raw_operator_lens = self._extract_section(markdown, "Operator Lens")
            raw_investor_lens = self._extract_section(markdown, "Investor Lens")
            raw_bd_lens = self._extract_section(markdown, "BD Lens")
            raw_exec_summary = self._extract_section(markdown, "Executive Summary")
            raw_topline = self._extract_section(markdown, "Topline")
            
            # Combine all raw markdown sections for citation search
            all_raw_sections = '\n'.join(filter(None, [
                raw_market_analysis,
                raw_tech_deepdive,
                raw_competitive,
                raw_operator_lens,
                raw_investor_lens,
                raw_bd_lens,
                raw_exec_summary,
                raw_topline
            ]))
            
            # Pass raw markdown and signals HTML for citation filtering
            sections['sources'] = self._parse_sources(
                sources_text, 
                signals_html=sections.get('signals_html', ''),
                raw_markdown=all_raw_sections,
                ledger=metadata.get('evidence_ledger')
            )
            sections['sources_html'] = self._render_source_citations(sections['sources'])
        else:
            sections['sources'] = []
            sections['sources_html'] = ""
        
        return sections
    
    def _parse_thesis_markdown(self, markdown: str, json_ld: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Parse thesis-style markdown with # or ## headings into structured sections"""
        sections = {}
        
        # Extract title from metadata query (preferred) or first heading
        raw_title = metadata.get('query', '')
        if not raw_title:
            # Try ## Title section first (full title), then single # heading
            title_match_2 = re.search(r'^## Title\s*\n+(.+?)(?=\n## |$)', markdown, re.MULTILINE | re.DOTALL)
            if title_match_2:
                raw_title = title_match_2.group(1).strip()
                # Extract just the first line if multiline
                raw_title = raw_title.split('\n')[0].strip()
            else:
                title_match = re.search(r'^# (.+)$', markdown, re.MULTILINE)
                if title_match:
                    raw_title = title_match.group(1).strip()
            
            if not raw_title:
                raw_title = "Intelligence Report"
            
            # If title is "Abstract", try to get query from metadata
            if raw_title == "Abstract":
                raw_title = metadata.get('query', raw_title)
        
        sections['title'] = self._apply_house_style_title(raw_title)
        
        # Extract date range from markdown or metadata
        metadata_match = re.search(r'^Date range: ([^|]+)', markdown, re.MULTILINE)
        if metadata_match:
            sections['date_range'] = metadata_match.group(1).strip()
        else:
            # Generate date range from metadata if available
            if 'days_back' in metadata:
                from datetime import datetime, timedelta
                days_back = metadata['days_back']
                end_date = datetime.now()
                start_date = end_date - timedelta(days=days_back)
                sections['date_range'] = f"{start_date.strftime('%b %d')}–{end_date.strftime('%b %d, %Y')}"
            else:
                sections['date_range'] = ""
        
        # Extract ALL sections with # or ## headings dynamically
        # Need to capture content until next heading at same or higher level
        # For # headings: stop at next # heading (not ##)
        # For ## headings: stop at next # or ## heading
        all_sections = {}
        
        lines = markdown.split('\n')
        i = 0
        current_section = None
        current_content = []
        
        while i < len(lines):
            line = lines[i]
            line_stripped = line.strip()
            
            # Check if this line is a heading
            if line_stripped.startswith('#'):
                # Count heading level
                heading_level = 0
                j = 0
                while j < len(line_stripped) and line_stripped[j] == '#':
                    heading_level += 1
                    j += 1
                
                # Extract section name (rest of line after #s and spaces)
                section_name = line_stripped[j:].strip()
                
                # Skip title-related headings
                # BUT: Never skip "Executive Summary" even if it somehow matches title - it's always a real section
                if section_name == "Title":
                    i += 1
                    continue
                # Skip first heading if it matches the document title (document title, not a section)
                # Important: Only skip if this is the FIRST heading AND it matches title
                # Never skip "Executive Summary" or other known section headings
                if (heading_level == 1 and 
                    section_name == raw_title and 
                    section_name not in ["Executive Summary", "Abstract", "Introduction", "Theory-First Framework"] and
                    current_section is None):  # Only skip if we haven't started any section yet
                    i += 1
                    continue
                if section_name == "References":
                    # Save previous section if exists
                    if current_section:
                        all_sections[current_section['name']] = '\n'.join(current_content).strip()
                    current_section = None
                    current_content = []
                    i += 1
                    continue
                
                # If we have a previous section, check if this is a heading at same/higher level
                should_save_previous = False
                if current_section:
                    current_level = current_section['level']
                    # Save previous section if:
                    # - Current is # and new is # (same level - new top-level section)
                    # - Current is # and new is ## (new subsection - BUT in this markdown format,
                    #   ## headings at the end may be standalone sections, not subsections)
                    # - Current is ## and new is # or ## (same/higher level)
                    
                    # Heuristic: If previous line is empty or we're near end of document,
                    # treat ## as standalone section, not subsection
                    # For now, we'll treat ## headings as subsections only if they appear
                    # immediately after content in a # section. If there's spacing, treat as new section.
                    
                    # Check for spacing before this heading (empty lines indicate new section)
                    has_spacing = False
                    if i > 0:
                        # Check previous line
                        if not lines[i-1].strip():
                            has_spacing = True
                        # Check if there are multiple empty lines
                        empty_count = 0
                        for j in range(max(0, i-3), i):
                            if not lines[j].strip():
                                empty_count += 1
                        if empty_count >= 2:
                            has_spacing = True
                    
                    if current_level == 1:
                        # # heading: save if next is # (same level)
                        if heading_level == 1:
                            should_save_previous = True
                        elif heading_level == 2 and has_spacing:
                            # ## heading with spacing - treat as new standalone section
                            should_save_previous = True
                        # Otherwise, ## is a subsection - include it in current section content
                        # Don't save yet, just add the ## heading line to current section content
                        if heading_level == 2 and not has_spacing:
                            # This is a subsection - add it to current section's content
                            current_content.append(line)
                            i += 1
                            continue  # Don't start a new section, stay in current section
                    elif current_level == 2:
                        # ## heading: save if next is # or ## (same/higher level)
                        if heading_level <= 2:
                            should_save_previous = True
                    
                    if should_save_previous:
                        all_sections[current_section['name']] = '\n'.join(current_content).strip()
                
                # Start new section (only if we're not in a subsection case above)
                current_section = {'name': section_name, 'level': heading_level}
                current_content = []
            elif current_section:
                # Add line to current section content
                current_content.append(line)
            
            i += 1
        
        # Save last section if exists
        if current_section:
            all_sections[current_section['name']] = '\n'.join(current_content).strip()
        
        # Debug logging: show extracted sections
        logger.info(f"Thesis parsing: Extracted {len(all_sections)} sections: {list(all_sections.keys())}")
        for name, content in all_sections.items():
            logger.debug(f"Thesis section '{name}': {len(content)} chars, preview: {content[:100]}...")
        
        # Extract Executive Summary using regex (similar to market path approach)
        # Handle both # Executive Summary and ## Executive Summary
        # Stop at horizontal rule (---) or next heading
        # First, try to get from all_sections if it exists (preserves full content)
        exec_summary_text = ""
        if 'Executive Summary' in all_sections:
            # Use the full section content, but extract just the text before horizontal rule
            exec_section_content = all_sections['Executive Summary']
            # Split by horizontal rule if present
            parts = re.split(r'\n---\s*\n', exec_section_content, maxsplit=1)
            exec_summary_text = parts[0].strip()
            logger.debug(f"Thesis: Extracted Executive Summary from all_sections ({len(exec_summary_text)} chars)")
        else:
            # Fallback: try regex extraction
            exec_summary_match = re.search(r'^#+\s+Executive Summary\s*\n(.*?)(?=\n(?:---|#\s+)|$)', markdown, re.MULTILINE | re.DOTALL)
            if exec_summary_match:
                exec_summary_text = exec_summary_match.group(1).strip()
                # Remove horizontal rule if it appears at the end
                exec_summary_text = re.sub(r'\n---\s*$', '', exec_summary_text, flags=re.MULTILINE)
                logger.debug(f"Thesis: Extracted Executive Summary via regex ({len(exec_summary_text)} chars)")
            else:
                # Fallback: try to extract from Abstract section (for backwards compatibility)
                abstract_text = ""
                if 'Title and Abstract' in all_sections:
                    title_abstract_content = all_sections['Title and Abstract']
                    # Look for "Abstract:" at start of line
                    abstract_match = re.search(r'^Abstract\s*:\s*\n+(.+?)(?=\n(?:##|Title\s*:)|\Z)', title_abstract_content, re.MULTILINE | re.DOTALL | re.IGNORECASE)
                    if abstract_match:
                        abstract_text = abstract_match.group(1).strip()
                elif 'Abstract' in all_sections:
                    abstract_text = all_sections['Abstract'].strip()
                
                if abstract_text:
                    exec_summary_text = abstract_text
                    logger.debug(f"Thesis: Extracted Executive Summary from Abstract section ({len(abstract_text)} chars)")
                else:
                    # Final fallback: use first paragraph of first section
                    first_section_name = list(all_sections.keys())[0] if all_sections else None
                    if first_section_name:
                        first_content = all_sections[first_section_name]
                        first_para = first_content.split('\n\n')[0] if '\n\n' in first_content else first_content.split('\n')[0]
                        exec_summary_text = first_para.strip()
                        logger.debug(f"Thesis: Extracted Executive Summary from first section ({len(exec_summary_text)} chars)")
                    else:
                        exec_summary_text = ""
                        logger.warning("Thesis: No Executive Summary found via any method")
        
        # Clean Executive Summary content before conversion
        if exec_summary_text:
            exec_summary_text = self._clean_exec_summary_content(exec_summary_text)
            sections['exec_summary'] = self._convert_thesis_markdown_to_html(exec_summary_text)
            # Topline from first paragraph
            first_para = exec_summary_text.split('\n\n')[0] if '\n\n' in exec_summary_text else exec_summary_text.split('\n')[0]
            sections['topline'] = self._process_markdown_inline(first_para.strip()) if first_para.strip() else ""
            logger.debug(f"Thesis exec_summary: {len(sections['exec_summary'])} chars, topline: {len(sections['topline'])} chars")
        else:
            sections['exec_summary'] = ""
            sections['topline'] = ""
            logger.warning("Thesis report has no Executive Summary or Abstract found")
        
        # Helper function to sanitize section name for ID
        def sanitize_section_id(name: str) -> str:
            """Convert section name to URL-safe ID"""
            # Convert to lowercase, replace spaces and special chars with hyphens
            id_text = re.sub(r'[^\w\s-]', '', name.lower())
            id_text = re.sub(r'[-\s]+', '-', id_text)
            return id_text.strip('-')
        
        # Build all sections HTML dynamically (preserve order, skip "Title and Abstract" and "References")
        section_list = []  # List of dicts: [{'name': str, 'id': str, 'content_html': str}]
        section_ids = set()  # Track IDs to avoid duplicates
        
        for section_name, section_content in all_sections.items():
            # Skip these sections (they're handled separately)
            # Executive Summary is already in the template, so skip from dynamic sections (case-insensitive)
            section_name_lower = section_name.lower().strip()
            if section_name_lower in ['title and abstract', 'references', 'executive summary']:
                continue
            
            # Skip empty sections
            if not section_content or not section_content.strip():
                logger.debug(f"Skipping empty section: {section_name}")
                continue
            
            # Generate sanitized ID
            section_id = sanitize_section_id(section_name)
            # Handle duplicate IDs
            original_id = section_id
            counter = 1
            while section_id in section_ids:
                section_id = f"{original_id}-{counter}"
                counter += 1
            section_ids.add(section_id)
            
            # Convert content to HTML
            content_html = self._convert_thesis_markdown_to_html(section_content)
            
            section_list.append({
                'name': section_name,
                'id': section_id,
                'content_html': content_html
            })
        
        # Build all_sections_html and toc_html
        all_sections_html_parts = []
        toc_html_parts = ['<strong>Outline</strong>', '<ul>']
        
        if not section_list:
            logger.warning(f"Thesis: No sections found in section_list! all_sections had {len(all_sections)} sections: {list(all_sections.keys())}")
            # Log details about each section
            for name, content in all_sections.items():
                content_len = len(content) if content else 0
                content_preview = content[:100] if content else "(empty)"
                logger.warning(f"  Section '{name}': {content_len} chars, preview: {content_preview}...")
                # If section has content but was filtered out, try to include it anyway (except Executive Summary which is handled separately)
                if content_len > 0 and name.lower() not in ['executive summary', 'title and abstract', 'references']:
                    logger.warning(f"  Attempting to include filtered section '{name}' with {content_len} chars")
                    section_id = sanitize_section_id(name)
                    content_html = self._convert_thesis_markdown_to_html(content)
                    if content_html.strip():  # Only add if HTML conversion produced content
                        section_list.append({
                            'name': name,
                            'id': section_id,
                            'content_html': content_html
                        })
        
        for section in section_list:
            # Add to TOC
            toc_html_parts.append(f'<li><a href="#{section["id"]}">{section["name"]}</a></li>')
            
            # Add section HTML
            all_sections_html_parts.append(
                f'<section id="{section["id"]}">\n'
                f'    <h2>{section["name"]}</h2>\n'
                f'    {section["content_html"]}\n'
                f'</section>'
            )
        
        # Add Sources to TOC before closing ul
        toc_html_parts.append('<li><a href="#sources">Sources</a></li>')
        toc_html_parts.append('</ul>')
        
        sections['toc_html'] = '\n'.join(toc_html_parts)
        sections['all_sections_html'] = '\n\n'.join(all_sections_html_parts)
        
        logger.info(f"Thesis sections rendered: {len(section_list)} sections, {len(sections['all_sections_html'])} chars HTML")
        if len(section_list) > 0:
            logger.info(f"Thesis section names: {[s['name'] for s in section_list]}")
        
        # Extract sources from JSON-LD/agent_stats for thesis reports
        sources_list = []
        
        # Try to get sources from agent_stats first
        agent_stats = metadata.get('agent_stats', {})
        sources_data = agent_stats.get('sources_data', [])
        
        if sources_data:
            # Extract citations from markdown content - handle both [^id] and [^id:type] formats
            # Also handle numeric [id] format after conversion
            citations = re.findall(r'\[\^(\d+)(?::[^\]]+)?\]|\[(\d+)\]', markdown)
            cited_ids = {int(c[0] if c[0] else c[1]) for c in citations if c[0] or c[1]}
            
            # Filter sources to only those cited in markdown
            for source_data in sources_data:
                source_id = source_data.get('id')
                if source_id in cited_ids:
                    # Format source for rendering
                    publisher = source_data.get('publisher', '')
                    date = source_data.get('date', '')
                    credibility = source_data.get('credibility', 0.5)
                    url = source_data.get('url', '')
                    title = source_data.get('title', '')
                    
                    publisher_date = f"{publisher}, {date}" if publisher and date else (publisher or date or "")
                    if publisher_date:
                        publisher_date += f". (cred: {credibility:.2f})"
                    
                    sources_list.append({
                        'id': source_id,
                        'title': title,
                        'publisher_date': publisher_date,
                        'credibility': credibility,
                        'url': url
                    })
        else:
            # Fallback to JSON-LD hasPart
            has_part = json_ld.get('hasPart', [])
            for i, part in enumerate(has_part, 1):
                # Extract citations from markdown - handle both [^id] and [^id:type] formats, and numeric [id]
                citations = re.findall(r'\[\^(\d+)(?::[^\]]+)?\]|\[(\d+)\]', markdown)
                cited_ids = {int(c[0] if c[0] else c[1]) for c in citations if c[0] or c[1]}
                
                if i in cited_ids:
                    headline = part.get('headline', '')
                    confidence = part.get('confidence', 0.5)
                    citations_list = part.get('citation', [])
                    url = citations_list[0] if citations_list else ""
                    
                    sources_list.append({
                        'id': i,
                        'title': headline,
                        'publisher_date': f"(cred: {confidence:.2f})",
                        'credibility': confidence,
                        'url': url
                    })
        
        sections['sources'] = sources_list
        sections['sources_html'] = self._render_source_citations(sources_list) if sources_list else ""
        
        # Set empty defaults for market-style sections (not used in thesis template)
        sections['signals'] = []
        sections['signals_html'] = ""
        sections['market_analysis'] = ""
        sections['tech_deepdive'] = ""
        sections['competitive'] = ""
        sections['operator_lens'] = ""
        sections['investor_lens'] = ""
        sections['bd_lens'] = ""
        
        return sections
    
    def _extract_section(self, markdown: str, section_name: str) -> str:
        """Extract a specific section from markdown"""
        pattern = f'## {section_name}\n(.*?)(?=\n## |$)'
        match = re.search(pattern, markdown, re.DOTALL)
        return match.group(1).strip() if match else ""
    
    def _segment_into_paragraphs(self, text: str, max_words: int = 150) -> str:
        """Break long text into readable paragraphs with editorial enhancements"""
        if not text:
            return ""
        
        # Apply editorial fixes to the text
        text = self._soften_dyna_claims(text)
        text = self._inject_vendor_disclosure(text)
        
        # If text is short enough, just wrap it
        if len(text.split()) <= max_words:
            return f"<p>{text}</p>"
        
        # Split text into sentences first
        sentences = self._split_at_sentences(text)
        
        # Group sentences into paragraphs
        paragraphs = []
        current_para = []
        current_word_count = 0
        
        for sentence in sentences:
            sentence_words = len(sentence.split())
            
            # Check if adding this sentence would exceed max_words
            if current_word_count + sentence_words > max_words and current_para:
                # Start new paragraph
                paragraphs.append(' '.join(current_para))
                current_para = [sentence]
                current_word_count = sentence_words
            else:
                current_para.append(sentence)
                current_word_count += sentence_words
        
        # Add remaining sentences
        if current_para:
            paragraphs.append(' '.join(current_para))
        
        # Convert to HTML paragraphs
        html_parts = []
        for para in paragraphs:
            html_parts.append(f'<p>{para}</p>')
        
        return '\n'.join(html_parts)
    
    def _detect_subsections(self, text: str) -> List[str]:
        """Detect subsection patterns in text"""
        subsection_patterns = [
            r'^([A-Z][^.]*?):\s*$',  # "Pricing power dynamics:"
            r'^([A-Z][^.]*?)\s*—\s*',  # "Pricing power —"
            r'^([A-Z][^.]*?)\s*\(',  # "Model architectures ("
            r'^([A-Z][^.]*?)\s*and\s+[A-Z]',  # "Model architectures and chip"
        ]
        
        subsections = []
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            for pattern in subsection_patterns:
                match = re.match(pattern, line)
                if match:
                    subsection = match.group(1).strip()
                    if len(subsection) > 10 and len(subsection) < 80:
                        subsections.append(subsection)
                    break
        
        return subsections
    
    def _is_subsection_heading(self, text: str) -> bool:
        """Check if text is a subsection heading - improved for thesis sections"""
        line = text.strip()
        
        # Exclude empty lines and list items
        if not line or line.startswith('- '):
            return False
        
        # Exclude long lines (likely paragraph text)
        if len(line) > 60:
            return False
        
        # Exclude lines ending with punctuation (likely sentences)
        if line.endswith('.') or line.endswith(','):
            return False
        
        # Check for common subsection patterns
        patterns = [
            r'^[A-Z][^.]*:\s*$',  # Ends with colon
            r'^[A-Z][^.]*\s*—\s*',  # Contains em-dash
            r'^[A-Z][^.]*\s*and\s+[A-Z]',  # Contains "and" between caps
        ]
        
        for pattern in patterns:
            if re.match(pattern, line):
                return True
        
        # Additional check: short, capitalized lines (potential headings)
        words = line.split()
        if not words:
            return False
        
        # Consider it a heading if it's short and starts with capital
        if len(words) <= 5 and words[0][0].isupper():
            # But not if it contains common sentence words
            if any(word.lower() in ['the', 'a', 'an', 'is', 'are', 'was', 'were', 'will', 'to', 'for'] for word in words):
                return False
            return True
        
        return False
    
    def _process_markdown_inline(self, text: str) -> str:
        """Process inline markdown formatting (citations, emphasis, code)"""
        # Convert citations [^id:type] or [^id] to numeric [id] format for consistency
        # First convert [^id:type] to [id], then convert all [^id] to [id]
        text = re.sub(r'\[\^(\d+):[^\]]+\]', r'[\1]', text)  # [^2:A] -> [2]
        text = re.sub(r'\[\^(\d+)\]', r'[\1]', text)  # [^2] -> [2]
        
        # Convert numeric citations [id] to HTML links
        text = re.sub(r'\[(\d+)\]', r'<sup><a href="#source-\1" class="citation-link">[\1]</a></sup>', text)
        
        # Convert bold **text** to <strong>
        text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
        
        # Convert italic *text* to <em> (but not if already bold)
        text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', text)
        
        # Convert code `code` to <code>
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
        
        return text
    
    def _clean_exec_summary_content(self, text: str) -> str:
        """Clean Executive Summary content: remove confidence formula, duplicate paragraphs, blockquote artifacts"""
        if not text:
            return text
        
        lines = text.split('\n')
        cleaned_lines = []
        seen_paragraphs = set()
        confidence_pattern = re.compile(r'^\s*>?\s*\*\*Confidence:\*\*', re.IGNORECASE)
        confidence_value_pattern = re.compile(r'Confidence:\s*0\.\d+', re.IGNORECASE)
        
        # Group lines into paragraphs for better duplicate detection
        current_paragraph = []
        paragraphs = []
        
        for line in lines:
            stripped = line.strip()
            
            # Skip confidence formula lines (already in header) - catch both formats
            if confidence_pattern.search(stripped) or confidence_value_pattern.search(stripped):
                continue
            
            # Skip lines that start with stray ">" followed by space (blockquote artifacts in wrong context)
            if stripped.startswith('> ') and not stripped.startswith('> **'):
                # Remove the stray ">" marker
                cleaned_line = stripped[2:] if len(stripped) > 2 else ""
                if cleaned_line:
                    current_paragraph.append(cleaned_line)
                continue
            
            # Empty line marks paragraph boundary
            if not stripped:
                if current_paragraph:
                    paragraphs.append('\n'.join(current_paragraph))
                    current_paragraph = []
                continue
            
            current_paragraph.append(line)
        
        # Add final paragraph
        if current_paragraph:
            paragraphs.append('\n'.join(current_paragraph))
        
        # Remove duplicate paragraphs (compare normalized content)
        for para in paragraphs:
            # Normalize: remove blockquote markers, extra whitespace
            normalized = re.sub(r'^\s*>?\s*', '', para.strip(), flags=re.MULTILINE)
            normalized = ' '.join(normalized.split())  # Collapse whitespace
            
            if normalized and len(normalized) > 50:  # Only check substantial paragraphs
                para_key = normalized.lower().strip()
                if para_key not in seen_paragraphs:
                    seen_paragraphs.add(para_key)
                    cleaned_lines.append(para)
            elif normalized:  # Keep short non-empty paragraphs
                cleaned_lines.append(para)
        
        return '\n\n'.join(cleaned_lines)
    
    def _convert_markdown_table_to_html(self, table_text: str) -> str:
        """Convert markdown table to HTML table with proper styling"""
        if not table_text or not table_text.strip():
            return ""
        
        lines = [line.strip() for line in table_text.strip().split('\n') if line.strip()]
        if not lines:
            return ""
        
        # Check if this looks like a markdown table (pipe-delimited)
        if '|' not in lines[0]:
            return ""  # Not a table
        
        html_parts = ['<table>']
        
        for i, line in enumerate(lines):
            # Skip separator rows (|---|---|---|)
            if re.match(r'^[\|\s\-:]+$', line):
                continue
            
            # Handle escaped pipes: replace \| with placeholder before splitting
            escaped_placeholder = "___ESCAPED_PIPE___"
            line_with_placeholder = line.replace('\\|', escaped_placeholder)
            cells_raw = line_with_placeholder.split('|')
            cells = [cell.strip().replace(escaped_placeholder, '|') for cell in cells_raw]
            # Remove empty cells at start/end (from leading/trailing |)
            if cells and not cells[0]:
                cells = cells[1:]
            if cells and not cells[-1]:
                cells = cells[:-1]
            
            if not cells:
                continue
            
            # First non-separator row is header (check if previous line was separator)
            is_header = False
            if i == 0:
                # First line is always header if next line is separator
                if len(lines) > 1 and re.match(r'^[\|\s\-:]+$', lines[1]):
                    is_header = True
            else:
                # Check if previous non-separator line was a separator
                prev_line_idx = i - 1
                while prev_line_idx >= 0 and re.match(r'^[\|\s\-:]+$', lines[prev_line_idx]):
                    prev_line_idx -= 1
                if prev_line_idx < 0:
                    is_header = True  # First non-separator line is header
            
            if is_header:
                if i == 0:
                    html_parts.append('<thead><tr>')
                else:
                    html_parts.append('</thead><tbody>')
                    html_parts.append('<tr>')
                for cell in cells:
                    cell_html = self._process_markdown_inline(cell)
                    html_parts.append(f'<th>{cell_html}</th>')
                html_parts.append('</tr>')
                if i == 0:
                    html_parts.append('</thead><tbody>')
            else:
                html_parts.append('<tr>')
                for cell in cells:
                    cell_html = self._process_markdown_inline(cell)
                    html_parts.append(f'<td>{cell_html}</td>')
                html_parts.append('</tr>')
        
        html_parts.append('</tbody></table>')
        return '\n'.join(html_parts)
    
    def _convert_thesis_markdown_to_html(self, markdown_text: str) -> str:
        """Convert markdown text to HTML with proper formatting for thesis sections, including tables"""
        if not markdown_text or not markdown_text.strip():
            return ""
        
        # First, detect and convert tables
        # Split text into blocks, separating table blocks from other content
        text_blocks = []
        lines = markdown_text.split('\n')
        current_block = []
        current_block_type = 'text'  # 'text' or 'table'
        
        i = 0
        while i < len(lines):
            line = lines[i]
            line_stripped = line.strip()
            
            # Check if this line looks like the start of a table (has | and at least 2 cells)
            # Need to handle both cases: table with separator and table without explicit separator
            if '|' in line_stripped and len([c for c in line_stripped.split('|') if c.strip()]) >= 2:
                # Check if next line is a separator (|---|---|) - this confirms it's a table
                is_table_start = False
                if i + 1 < len(lines):
                    next_line_stripped = lines[i + 1].strip()
                    if re.match(r'^[\|\s\-:]+$', next_line_stripped):
                        is_table_start = True
                else:
                    # If this is the last line and it looks like a table row, might be table
                    # But without separator we can't be sure, so only if we're already in a table
                    pass
                
                if is_table_start:
                    # This is a table - close current text block if needed
                    if current_block and current_block_type == 'text':
                        text_blocks.append(('text', '\n'.join(current_block)))
                        current_block = []
                    current_block_type = 'table'
            
            # Check if we're ending a table block
            if current_block_type == 'table':
                # End table if:
                # 1. Line is empty (markdown tables don't have empty lines between rows)
                # 2. Line doesn't contain | and is not a separator pattern
                if not line_stripped:
                    # Empty line - end the table (markdown tables are contiguous)
                    table_text = '\n'.join(current_block)
                    if table_text.strip():
                        table_html = self._convert_markdown_table_to_html(table_text)
                        if table_html:
                            text_blocks.append(('table', table_html))
                    current_block = []
                    current_block_type = 'text'
                    # Skip the empty line (don't add it to text block)
                    i += 1
                    continue
                elif '|' not in line_stripped:
                    # Line without | that's not empty - end the table
                    # But check if it's a separator pattern first (shouldn't happen here since we already detected it)
                    if not re.match(r'^[\|\s\-:]+$', line_stripped):
                        table_text = '\n'.join(current_block)
                        if table_text.strip():
                            table_html = self._convert_markdown_table_to_html(table_text)
                            if table_html:
                                text_blocks.append(('table', table_html))
                        current_block = []
                        current_block_type = 'text'
                        # Process this line as text - add it to text block
                        # Don't continue, let it fall through
            
            current_block.append(line)
            i += 1
        
        # Process remaining block
        if current_block:
            if current_block_type == 'table':
                table_text = '\n'.join(current_block)
                table_html = self._convert_markdown_table_to_html(table_text)
                if table_html:
                    text_blocks.append(('table', table_html))
            else:
                text_blocks.append(('text', '\n'.join(current_block)))
        
        # Now convert each text block to HTML and combine
        html_parts = []
        for block_type, block_content in text_blocks:
            if block_type == 'table':
                html_parts.append(block_content)
            else:
                # Convert text block (paragraphs, lists, headings)
                block_html = self._convert_thesis_text_to_html(block_content)
                if block_html:
                    html_parts.append(block_html)
        
        result = '\n'.join(html_parts)
        if not result.strip():
            return ""
        
        return result
    
    def _report_type_config(self, is_thesis: bool):
        """Return small style/content config for report-type banners and accents."""
        if is_thesis:
            return {
                'type_key': 'thesis',
                'banner_class': 'thesis-path',
                'label': 'Thesis Brief — Theory-First Research',
                'timestamp_label': 'Edition',
                'timestamp_suffix': ' | Peer-review pending (Theory-First)',
                'palette_main': '#c05621',
                'palette_bg': '#fdf8f3',
                'text_color': '#7b341e',
                'font_stack': 'Georgia, "Times New Roman", serif',
                'exec_heading': 'Abstract & Theory-First Framing.',
                'footer_line': 'Prepared under the STI Research Program — theoretical framework subject to revision as data accumulate.'
            }
        else:
            return {
                'type_key': 'market',
                'banner_class': 'market-path',
                'label': 'Market Brief — Rapid Intelligence',
                'timestamp_label': 'Updated',
                'timestamp_suffix': ' | Rapid-cycle analysis',
                'palette_main': '#0056b3',
                'palette_bg': '#f0f7ff',
                'text_color': '#0056b3',
                'font_stack': '-apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif',
                'exec_heading': 'Market Takeaway',
                'footer_line': 'Prepared by the STI Market Intelligence Desk — all views as of publication time.'
            }
    
    def _inject_report_type_ui(self, html: str, cfg: Dict[str, Any], is_thesis: bool, anchor_status: str = '') -> str:
        """Inject minimal banner + timestamp + subtle style cues into HTML."""
        # 1) Add CSS accents and font override
        css = f"""
        <style>
          .report-type.{cfg['banner_class']} {{
            background: {cfg['palette_bg']};
            color: {cfg['text_color']};
            border-left: 5px solid {cfg['palette_main']};
            font-family: {cfg['font_stack']};
            text-transform: uppercase;
            letter-spacing: {('0.04em' if is_thesis else '0.05em')};
            padding: 0.6rem 1rem;
            margin-bottom: 1.5rem;
            font-weight: 600;
          }}
          .update-timestamp {{
            color: #666;
            font-size: 0.9em;
            margin: -0.75rem 0 1.25rem 0.3rem;
            font-family: {cfg['font_stack']};
          }}
          .sti-footer-note {{
            border-top: 2px solid {cfg['palette_main']};
            margin-top: 2rem;
            padding-top: 0.75rem;
            color: #666;
            font-size: 0.9em;
          }}
          /* Global font override to match path tone */
          body, h1, h2, h3, h4, h5 {{
            font-family: {cfg['font_stack']};
          }}
          /* Hero image styling */
          .hero-image-container {{
            margin: 1.5rem 0 2rem 0;
            text-align: center;
          }}
          .hero-image-container img {{
            max-width: 100%;
            height: auto;
            border-radius: 4px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
          }}
          .hero-image-attribution {{
            font-size: 0.75em;
            color: #666;
            margin-top: 0.5rem;
          }}
          /* Section image styling */
          .section-image-container {{
            margin: 1.5rem 0 2rem 0;
            text-align: center;
          }}
          .section-image-container img {{
            max-width: 90%;
            height: auto;
            border-radius: 4px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.1);
          }}
          .section-image-attribution {{
            font-size: 0.7em;
            color: #666;
            margin-top: 0.5rem;
            font-style: italic;
          }}
        </style>
        """
        html = html.replace("</head>", css + "</head>", 1)
        
        # 2) Banner + timestamp at top
        from datetime import datetime as _dt
        dt_display = _dt.now().strftime('%Y-%m-%d')
        timestamp = f"{cfg['timestamp_label']}: {dt_display}{cfg['timestamp_suffix']}"
        banner = f"""
        <div class="report-type {cfg['banner_class']}">
          <span>{cfg['label']}</span>
        </div>
        <div class="update-timestamp">{timestamp}</div>
        """
        # Add market subtitle to set expectations
        subtitle = '' if is_thesis else '<div class="update-timestamp">Timely market brief on infrastructure, operators, and capital flows.</div>'
        if "<header>" in html:
            html = html.replace("<header>", banner + subtitle + "<header>", 1)
        else:
            html = html.replace("<body>", "<body>\n" + banner + subtitle, 1)
        
        # 3) Rename Executive Summary heading
        html = html.replace(">Executive Summary<", f">{cfg['exec_heading']}<", 1)
        
        # 4) Metadata tell in header line
        type_line = "Report Type: Theoretical Research" if is_thesis else "Report Type: Market Intelligence"
        # Note: Anchor Status is already in template, don't duplicate here
        # Include horizon in metadata line if available
        if "| Confidence:" in html:
            html = html.replace("| Confidence:", f"| {type_line} | Horizon: {{horizon}} | Confidence:", 1)
            # Fill placeholder if present in the document title line
            html = html.replace("{horizon}", "Near-term")
        
        # 5) Footer note
        footer_note = f"<div class=\"sti-footer-note\">{cfg['footer_line']}</div>"
        if "</footer>" in html:
            html = html.replace("</footer>", footer_note + "\n</footer>", 1)
        else:
            html = html.replace("</body>", footer_note + "\n</body>", 1)
        
        return html
    
    def _generate_and_inject_images(self, html: str, query: str, report_dir: str, intent: str, exec_summary: str = None) -> str:
        """Generate hero image and section images using OpenAI API and inject into HTML"""
        logger.info(f"🖼️ _generate_and_inject_images called:")
        logger.debug(f"   - query: '{query}'")
        logger.debug(f"   - report_dir: '{report_dir}'")
        logger.debug(f"   - intent: '{intent}'")
        logger.debug(f"   - exec_summary: {len(exec_summary) if exec_summary else 0} chars")
        logger.debug(f"   - HTML length: {len(html)}")
        
        try:
            from image_generator import ImageGenerator
            import os
            
            # Check API key
            openai_key = os.getenv("OPENAI_API_KEY")
            logger.debug(f"🔑 OPENAI_API_KEY check: {'found' if openai_key else 'not found'}")
            if openai_key:
                logger.debug(f"   API key length: {len(openai_key)}, starts with: {openai_key[:7]}...")
            
            if not openai_key:
                logger.warning("⚠️ OPENAI_API_KEY not found - skipping image generation")
                return html
            
            # Check config
            try:
                enable_gen = getattr(STIConfig, 'ENABLE_IMAGE_GENERATION', False)
                logger.debug(f"⚙️ ENABLE_IMAGE_GENERATION: {enable_gen}")
                if not enable_gen:
                    logger.info("ℹ️ Image generation disabled in config")
                    return html
            except Exception as e:
                logger.warning(f"⚠️ Could not check STIConfig: {e}")
            
            # Validate report_dir
            report_path = Path(report_dir)
            if not report_path.exists():
                logger.error(f"❌ Report directory does not exist: {report_dir}")
                return html
            logger.debug(f"✅ Report directory exists: {report_dir}")
            
            logger.info(f"🔧 Initializing ImageGenerator...")
            generator = ImageGenerator(openai_key)
            
            # Generate hero image first (pass exec_summary for tailored prompts)
            html = self._generate_and_inject_hero_image(html, query, report_dir, intent, generator, exec_summary=exec_summary)
            
            # Generate section images if enabled
            enable_section_images = getattr(STIConfig, 'ENABLE_SECTION_IMAGES', True)
            if enable_section_images:
                logger.info("🎨 Generating section images...")
                html = self._generate_and_inject_section_images(html, query, report_dir, intent, generator)
            else:
                logger.debug("ℹ️ Section images disabled in config")
            
            return html
            
        except Exception as e:
            import traceback
            logger.error(f"❌ Image generation/injection failed: {type(e).__name__}: {e}")
            logger.error(f"❌ Full traceback:\n{traceback.format_exc()}")
            return html  # Continue without image
    
    def _generate_and_inject_hero_image(self, html: str, query: str, report_dir: str, 
                                        intent: str, generator, exec_summary: str = None) -> str:
        """Generate hero image and inject at top of article"""
        logger.info(f"🎨 Generating hero image...")
        logger.info(f"⏱️  Hero image generation may take 30-60 seconds - please wait...")
        try:
            result = generator.generate_hero_image(query, report_dir, intent, exec_summary=exec_summary)
        except Exception as img_error:
            error_str = str(img_error)
            if "timeout" in error_str.lower():
                logger.warning(f"⚠️ Hero image generation timed out - continuing without hero image")
            else:
                logger.warning(f"⚠️ Hero image generation failed: {error_str}")
                logger.warning(f"   Continuing without hero image...")
            return html
        
        if result is None:
            logger.warning("⚠️ Hero image generation returned None - no image generated")
            return html
        
        img_path, attribution = result
        logger.info(f"✅ Hero image generated: {img_path}")
        
        # Verify image file exists
        full_path = Path(report_dir) / img_path
        if not full_path.exists():
            logger.error(f"❌ Generated hero image file does not exist: {full_path}")
            return html
        
        # Build hero image HTML
        alt_text = html.escape(f"Conceptual illustration for {query}")
        hero_html = f'''
            <div class="hero-image-container">
                <img src="{img_path}" alt="{alt_text}" loading="lazy">
                <p class="hero-image-attribution">{attribution}</p>
            </div>
            '''
        
        # Insert hero image
        if "<article>" in html:
            html = html.replace("<article>", hero_html + "<article>", 1)
            logger.debug("✅ Inserted hero image before <article> tag")
        elif "<section" in html:
            import re
            html = re.sub(r'(<section[^>]*>)', hero_html + r'\1', html, count=1)
            logger.debug("✅ Inserted hero image before first <section> tag")
        else:
            html = html.replace("</header>", f"</header>{hero_html}", 1)
            logger.debug("✅ Inserted hero image after </header> tag")
        
        logger.info(f"✅ Injected hero image: {img_path}")
        return html
    
    def _detect_eligible_sections(self, html: str, intent: str) -> list:
        """Detect sections eligible for images based on intent and content length"""
        import re
        
        # Define target sections based on intent
        if intent == "theory" or intent == "thesis":
            target_sections = [
                "Foundational Theory", "Foundations",
                "Mechanisms", "Formalization",
                "Applications", "Synthesis"
            ]
        else:
            target_sections = [
                "Market Analysis",
                "Technology Deep-Dive", "Technology Deep Dive", "Tech Deep-Dive",
                "Competitive Landscape"
            ]
        
        eligible_sections = []
        min_length = getattr(STIConfig, 'MIN_SECTION_LENGTH_FOR_IMAGE', 400)
        max_images = getattr(STIConfig, 'MAX_SECTION_IMAGES', 4)
        
        # Find all h2 tags and their content
        h2_pattern = r'<h2[^>]*>(.*?)</h2>'
        sections = re.finditer(h2_pattern, html, re.IGNORECASE | re.DOTALL)
        
        for match in sections:
            section_title = re.sub(r'<[^>]+>', '', match.group(1)).strip()
            
            # Check if this section matches our target sections
            is_target = False
            normalized_title = section_title.lower()
            for target in target_sections:
                if target.lower() in normalized_title:
                    is_target = True
                    break
            
            if not is_target:
                continue
            
            # Find content between this h2 and next h2 (or end of section/article)
            start_pos = match.end()
            
            # Find next h2 or section/article boundary
            next_match = re.search(r'<h2[^>]*>', html[start_pos:], re.IGNORECASE)
            if next_match:
                end_pos = start_pos + next_match.start()
            else:
                # Find end of section or article
                section_end = re.search(r'</section>|</article>', html[start_pos:], re.IGNORECASE)
                if section_end:
                    end_pos = start_pos + section_end.start()
                else:
                    end_pos = len(html)
            
            # Extract content and count words (strip HTML tags)
            content = html[start_pos:end_pos]
            text_content = re.sub(r'<[^>]+>', ' ', content)
            word_count = len(text_content.split())
            
            logger.debug(f"📊 Section '{section_title}': {word_count} words")
            
            if word_count >= min_length:
                eligible_sections.append({
                    'title': section_title,
                    'content': text_content[:1500],  # First 1500 chars for LLM prompt context
                    'position': match.start(),
                    'content_html': content[:2000]  # First 2000 chars for HTML context
                })
                logger.info(f"✅ Section '{section_title}' eligible for image ({word_count} words)")
                
                # Respect max images limit
                if len(eligible_sections) >= max_images:
                    logger.info(f"ℹ️ Reached maximum section images limit ({max_images})")
                    break
        
        logger.info(f"📋 Found {len(eligible_sections)} eligible sections for images")
        return eligible_sections
    
    def _generate_and_inject_section_images(self, html: str, query: str, report_dir: str, 
                                           intent: str, generator) -> str:
        """Generate and inject images for eligible sections"""
        logger.info(f"🖼️ _generate_and_inject_section_images called")
        
        # Detect eligible sections
        eligible_sections = self._detect_eligible_sections(html, intent)
        
        if not eligible_sections:
            logger.info("ℹ️ No eligible sections found for images")
            return html
        
        # Generate images for each section (in reverse order to maintain positions)
        # We process in reverse so insertions don't shift positions
        injected_count = 0
        
        for section in reversed(eligible_sections):
            section_title = section['title']
            section_content = section['content']
            
            logger.info(f"🎨 Generating image for section: '{section_title}'")
            logger.info(f"⏱️  Section image generation may take 30-60 seconds - please wait...")
            
            try:
                result = generator.generate_section_image(
                    section_title, section_content, query, intent, report_dir
                )
            except Exception as img_error:
                error_str = str(img_error)
                if "timeout" in error_str.lower():
                    logger.warning(f"⚠️ Section image generation timed out for '{section_title}' - skipping")
                else:
                    logger.warning(f"⚠️ Section image generation failed for '{section_title}': {error_str}")
                continue
            
            if result is None:
                logger.warning(f"⚠️ Section image generation returned None for '{section_title}'")
                continue
            
            img_path, attribution = result
            logger.info(f"✅ Section image generated: {img_path}")
            
            # Verify image file exists
            full_path = Path(report_dir) / img_path
            if not full_path.exists():
                logger.error(f"❌ Generated section image file does not exist: {full_path}")
                continue
            
            # Build section image HTML
            safe_section = html.escape(section_title or "Section illustration")
            section_html = f'''
            <div class="section-image-container">
                <img src="{img_path}" alt="{safe_section}" loading="lazy">
                <p class="section-image-attribution">{attribution}</p>
            </div>
            '''
            
            # Inject after section header
            # Find the h2 tag for this section
            import re
            h2_pattern = re.compile(
                f'<h2[^>]*>{re.escape(section_title)}</h2>',
                re.IGNORECASE
            )
            
            match = h2_pattern.search(html)
            if match:
                # Insert after the h2 tag
                insert_pos = match.end()
                html = html[:insert_pos] + section_html + html[insert_pos:]
                injected_count += 1
                logger.info(f"✅ Injected section image for '{section_title}'")
            else:
                logger.warning(f"⚠️ Could not find h2 tag for section '{section_title}' in HTML")
        
        logger.info(f"🎉 Successfully injected {injected_count} section images")
        return html
    
    def _convert_thesis_text_to_html(self, text: str) -> str:
        """Convert non-table markdown text to HTML (paragraphs, lists, headings)"""
        if not text or not text.strip():
            return ""
        
        lines = text.split('\n')
        html_parts = []
        in_list = False
        in_ordered_list = False
        in_blockquote = False
        current_paragraph = []
        current_blockquote = []
        
        for line in lines:
            stripped_line = line.strip()
            
            # Blockquote detection (lines starting with > )
            if stripped_line.startswith('> '):
                # Close any open structures
                if current_paragraph:
                    para_text = ' '.join(current_paragraph)
                    if para_text:
                        html_parts.append(f"<p>{para_text}</p>")
                    current_paragraph = []
                if in_list:
                    html_parts.append("</ul>")
                    in_list = False
                if in_ordered_list:
                    html_parts.append("</ol>")
                    in_ordered_list = False
                
                # Start blockquote if not already in one
                if not in_blockquote:
                    html_parts.append("<blockquote>")
                    in_blockquote = True
                
                # Process blockquote content (remove > marker, keep space)
                blockquote_content = stripped_line[2:]  # Remove '> '
                processed_content = self._process_markdown_inline(blockquote_content.strip())
                current_blockquote.append(processed_content)
                continue
            
            # If we were in a blockquote and this line doesn't start with >, close it
            if in_blockquote:
                if current_blockquote:
                    blockquote_text = ' '.join(current_blockquote)
                    html_parts.append(f"<p>{blockquote_text}</p>")
                    current_blockquote = []
                html_parts.append("</blockquote>")
                in_blockquote = False
            
            # Horizontal rule (--- or *** or ___)
            if re.match(r'^[-*_]{3,}\s*$', stripped_line):
                # Close any open structures
                if current_paragraph:
                    para_text = ' '.join(current_paragraph)
                    if para_text:
                        html_parts.append(f"<p>{para_text}</p>")
                    current_paragraph = []
                if in_list:
                    html_parts.append("</ul>")
                    in_list = False
                if in_ordered_list:
                    html_parts.append("</ol>")
                    in_ordered_list = False
                if in_blockquote:
                    if current_blockquote:
                        blockquote_text = ' '.join(current_blockquote)
                        html_parts.append(f"<p>{blockquote_text}</p>")
                        current_blockquote = []
                    html_parts.append("</blockquote>")
                    in_blockquote = False
                
                html_parts.append("<hr/>")
                continue
            
            # Empty line = paragraph break
            if not stripped_line:
                # Close blockquote if open (empty line ends blockquote)
                if in_blockquote:
                    if current_blockquote:
                        blockquote_text = ' '.join(current_blockquote)
                        html_parts.append(f"<p>{blockquote_text}</p>")
                        current_blockquote = []
                    html_parts.append("</blockquote>")
                    in_blockquote = False
                
                if current_paragraph:
                    para_text = ' '.join(current_paragraph)
                    if para_text:
                        html_parts.append(f"<p>{para_text}</p>")
                    current_paragraph = []
                if in_list:
                    html_parts.append("</ul>")
                    in_list = False
                if in_ordered_list:
                    html_parts.append("</ol>")
                    in_ordered_list = False
                continue
            
            # Ordered list item (number.)
            if re.match(r'^\d+\.\s+', stripped_line):
                # Close blockquote if open
                if in_blockquote:
                    if current_blockquote:
                        blockquote_text = ' '.join(current_blockquote)
                        html_parts.append(f"<p>{blockquote_text}</p>")
                        current_blockquote = []
                    html_parts.append("</blockquote>")
                    in_blockquote = False
                if not in_ordered_list:
                    if in_list:
                        html_parts.append("</ul>")
                        in_list = False
                    html_parts.append("<ol>")
                    in_ordered_list = True
                list_content = self._process_markdown_inline(stripped_line[re.match(r'^\d+\.\s+', stripped_line).end():])
                html_parts.append(f"<li>{list_content}</li>")
                continue
            
            # Bullet point = list item
            if stripped_line.startswith('- '):
                # Close blockquote if open
                if in_blockquote:
                    if current_blockquote:
                        blockquote_text = ' '.join(current_blockquote)
                        html_parts.append(f"<p>{blockquote_text}</p>")
                        current_blockquote = []
                    html_parts.append("</blockquote>")
                    in_blockquote = False
                if not in_list:
                    if in_ordered_list:
                        html_parts.append("</ol>")
                        in_ordered_list = False
                    if current_paragraph:
                        para_text = ' '.join(current_paragraph)
                        if para_text:
                            html_parts.append(f"<p>{para_text}</p>")
                        current_paragraph = []
                    html_parts.append("<ul>")
                    in_list = True
                list_content = self._process_markdown_inline(stripped_line[2:])
                html_parts.append(f"<li>{list_content}</li>")
                continue
            
            # Subsection heading detection (standalone capitalized line)
            if self._is_subsection_heading(stripped_line):
                # Close blockquote if open
                if in_blockquote:
                    if current_blockquote:
                        blockquote_text = ' '.join(current_blockquote)
                        html_parts.append(f"<p>{blockquote_text}</p>")
                        current_blockquote = []
                    html_parts.append("</blockquote>")
                    in_blockquote = False
                # Close current paragraph if exists
                if current_paragraph:
                    para_text = ' '.join(current_paragraph)
                    if para_text:
                        html_parts.append(f"<p>{para_text}</p>")
                    current_paragraph = []
                # Close list if exists
                if in_list:
                    html_parts.append("</ul>")
                    in_list = False
                if in_ordered_list:
                    html_parts.append("</ol>")
                    in_ordered_list = False
                # Add heading
                html_parts.append(f"<h3>{stripped_line}</h3>")
                continue
            
            # Regular paragraph text
            # Close lists if we're starting a new paragraph
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            if in_ordered_list:
                html_parts.append("</ol>")
                in_ordered_list = False
            
            # Add line to current paragraph (process inline formatting)
            processed_line = self._process_markdown_inline(stripped_line)
            current_paragraph.append(processed_line)
        
        # Close any remaining structures
        if current_paragraph:
            para_text = ' '.join(current_paragraph)
            if para_text:
                html_parts.append(f"<p>{para_text}</p>")
        if in_list:
            html_parts.append("</ul>")
        if in_ordered_list:
            html_parts.append("</ol>")
        if in_blockquote:
            if current_blockquote:
                blockquote_text = ' '.join(current_blockquote)
                html_parts.append(f"<p>{blockquote_text}</p>")
            html_parts.append("</blockquote>")
        
        result = '\n'.join(html_parts)
        if not result.strip():
            return ""
        
        return result
    
    def _split_at_sentences(self, text: str) -> List[str]:
        """Split text at sentence boundaries"""
        # Simple sentence splitting on periods, exclamation, question marks
        sentences = re.split(r'[.!?]+\s+', text)
        return [s.strip() for s in sentences if s.strip()]
    
    def _format_lens_content(self, lens_text: str) -> str:
        """Format lens text with paragraph breaks"""
        if not lens_text:
            return ""
        
        # Use shorter max_words for lens cards (more compact)
        return self._segment_into_paragraphs(lens_text, max_words=100)
    
    def _parse_signals(self, signals_text: str, date_range: str = "") -> List[Dict[str, Any]]:
        """Parse signals from markdown text with date validation and editorial fixes"""
        signals = []
        signal_lines = signals_text.strip().split('\n')
        
        # Extract coverage end date for forecast detection
        coverage_end_date = None
        if date_range:
            # Parse date range like "Oct 21–Oct 28, 2025"
            date_match = re.search(r'(\w+ \d+)–(\w+ \d+), (\d{4})', date_range)
            if date_match:
                end_date_str = f"{date_match.group(2)}, {date_match.group(3)}"
                try:
                    from datetime import datetime
                    coverage_end_date = datetime.strptime(end_date_str, '%b %d, %Y')
                except Exception:
                    logger.warning(f"Could not parse coverage end date: {end_date_str}")
        
        for line in signal_lines:
            if line.startswith('- '):
                signal_text = line[2:]  # Remove '- '
                
                # Extract citation references - handle both [^id] and [^id:type] formats
                # This handles any number of sources (uses \d+ which matches one or more digits)
                citation_refs = re.findall(r'\[\^(\d+)(?::[^\]]+)?\]', signal_text)
                signal_text = re.sub(r'\[\^\d+(?::[^\]]+)?\]', '', signal_text)  # Remove citation refs
                
                # Extract metadata (strength, impact, trend)
                strength_match = re.search(r'strength: (\w+)', signal_text)
                impact_match = re.search(r'impact: (\w+)', signal_text)
                trend_match = re.search(r'trend: ([↗↘→?])', signal_text)
                
                # Apply editorial fixes
                # 1. Soften DYNA-1 claims
                signal_text = self._soften_dyna_claims(signal_text)
                
                # 2. Detect vendor-asserted claims
                is_vendor_asserted = False
                vendor_patterns = [r'\d+\+ (LLMs?|models?)', r'\d+\+ providers?']
                for pattern in vendor_patterns:
                    if re.search(pattern, signal_text):
                        # Check if citation references source [1] (TechCrunch sponsor page)
                        if 1 in [int(ref) for ref in citation_refs]:
                            is_vendor_asserted = True
                            break
                
                # 3. Detect forecast signals (date > coverage end date)
                is_forecast = False
                if coverage_end_date:
                    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', signal_text)
                    if date_match:
                        try:
                            signal_date = datetime.strptime(date_match.group(1), '%Y-%m-%d')
                            if signal_date > coverage_end_date:
                                is_forecast = True
                                logger.info(f"Signal dated {date_match.group(1)} marked as forecast (after {coverage_end_date.strftime('%Y-%m-%d')})")
                        except Exception:
                            logger.warning(f"Could not parse signal date: {date_match.group(1)}")
                
                signal = {
                    'text': signal_text.strip(),
                    'strength': strength_match.group(1) if strength_match else 'Medium',
                    'impact': impact_match.group(1) if impact_match else 'Medium',
                    'trend': trend_match.group(1) if trend_match else '?',
                    'citations': [int(ref) for ref in citation_refs],
                    'is_vendor_asserted': is_vendor_asserted,
                    'is_forecast': is_forecast
                }
                signals.append(signal)
        
        return signals
    
    def _parse_sources(self, sources_text: str, signals_html: str = "", 
                       analysis_sections: List[str] = None, raw_markdown: str = "",
                       ledger: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Parse sources from markdown text and filter to only cited sources"""
        sources = []
        source_lines = sources_text.strip().split('\n')
        
        for line in source_lines:
            if line.startswith('[^'):
                # Parse citation format: [^1]: or [^1:P]: Title — Publisher, Date. (cred: 0.90) — URL
                # Handle both old format [^1]: and new format [^1:P]:
                citation_match = re.match(r'\[\^(\d+)(?::([PDAGO]))?\]: (.+)', line)
                if citation_match:
                    citation_id = int(citation_match.group(1))
                    source_type_tag = citation_match.group(2)  # P/D/A/O/G or None
                    rest = citation_match.group(3)
                    
                    # Split by '—' to get title, additional_info, publisher/date/cred, url
                    parts = rest.split(' — ')
                    
                    # Handle different formats - could be 3 or 4+ parts depending on title complexity
                    if len(parts) >= 4:
                        # Format: Title — Extra info — Publisher, Date. (cred: X) — URL
                        title = ' — '.join(parts[:-2])  # Everything except last 2 parts
                        publisher_date = parts[-2].strip()
                        url_part = parts[-1].strip()
                    elif len(parts) >= 3:
                        # Format: Title — Publisher, Date. (cred: X) — URL
                        title = parts[0].strip()
                        publisher_date = parts[1].strip()
                        url_part = parts[2].strip()
                    else:
                        logger.warning(f"Skipping malformed source line: {line}")
                        continue
                    
                    # Extract credibility from publisher_date part
                    cred_match = re.search(r'\(cred: ([\d.]+)\)', publisher_date)
                    credibility = float(cred_match.group(1)) if cred_match else 0.5
                    
                    # Extract URL from url_part
                    url_match = re.search(r'https?://[^\s]+', url_part)
                    url = url_match.group(0) if url_match else None
                    
                    # CRITICAL ERROR CHECK - should never happen with Layer 1+2
                    if not url or url == "#" or len(url) < 10:
                        logger.error(f"❌ CRITICAL: Source [{citation_id}] '{title}' has no valid URL - THIS SHOULD NEVER HAPPEN")
                        logger.error(f"    This indicates a validation failure upstream. Source should have been rejected.")
                        logger.error(f"    Raw line: {line}")
                        logger.error(f"    Parts: {parts}")
                        logger.error(f"    URL part: {url_part}")
                        # Still create source but mark as invalid
                        url = "#INVALID-SOURCE-CONTACT-ADMIN"
                    
                    # Map type tag to full name
                    type_names = {
                        'P': 'Peer-reviewed',
                        'D': 'Doctrine',
                        'A': 'arXiv',
                        'O': 'Official',
                        'G': 'Grey'
                    }
                    source_type = type_names.get(source_type_tag, 'Unknown') if source_type_tag else None
                    
                    source = {
                        'id': citation_id,
                        'title': title,
                        'publisher_date': publisher_date,
                        'credibility': credibility,
                        'url': url,
                        'type': source_type,
                        'type_tag': source_type_tag or ''
                    }
                    sources.append(source)
        
        # Filter to only cited sources
        if signals_html or raw_markdown or analysis_sections:
            cited_source_ids = set()
            
            # Extract citation references from signals HTML (already processed, uses [id] format)
            if signals_html:
                citation_pattern = r'\[(\d+)\]'
                cited_source_ids.update(int(m.group(1)) for m in re.finditer(citation_pattern, signals_html))
            
            # Extract citation references from raw markdown (matches [^id] and [id] formats)
            # This handles any number of sources (uses \d+ which matches one or more digits)
            if raw_markdown:
                # Match both [^id] and [id] formats in raw markdown, also handles [^id:type] format
                citation_pattern = r'\[\^?(\d+)(?::[^\]]+)?\]'
                cited_source_ids.update(int(m.group(1)) for m in re.finditer(citation_pattern, raw_markdown))
            
            # Fallback: extract from analysis sections HTML if raw_markdown not provided (backward compatibility)
            if analysis_sections and not raw_markdown:
                all_analysis_text = ' '.join(analysis_sections)
                citation_pattern = r'\[(\d+)\]'
                cited_source_ids.update(int(m.group(1)) for m in re.finditer(citation_pattern, all_analysis_text))
            
            # Filter sources to only include cited ones
            filtered_sources = [s for s in sources if s['id'] in cited_source_ids]
            
            logger.info(f"Source filtering: {len(sources)} total sources, {len(filtered_sources)} cited sources")
            logger.info(f"Cited source IDs: {sorted(cited_source_ids)}")
            sources = filtered_sources

        if ledger:
            support_map: Dict[str, List[Dict[str, Any]]] = {}
            for claim in ledger.get('claims', []):
                claim_id = claim.get('id') or claim.get('claim_id')
                claim_text = claim.get('text') or claim.get('claim_text')
                for span in claim.get('support_spans', []):
                    source_key = str(span.get('source_id'))
                    support_map.setdefault(source_key, []).append({
                        'claim_id': claim_id,
                        'claim_text': claim_text,
                        'text': span.get('text', ''),
                    })
            for source in sources:
                key = str(source.get('id'))
                if key in support_map:
                    source['support_spans'] = support_map[key]

        return sources
    
    def _extract_json_ld_data(self, json_ld: Dict[str, Any], filtered_sources_count: int = None) -> Dict[str, Any]:
        """Extract relevant data from JSON-LD"""
        data = {}
        
        # Extract confidence and format to 2 decimal places
        if 'aggregateRating' in json_ld:
            confidence = json_ld['aggregateRating'].get('ratingValue', 0.5)
            data['confidence'] = round(float(confidence), 2)
        
        # Extract word count
        data['word_count'] = json_ld.get('wordCount', 0)
        
        # Extract temporal coverage
        if 'temporalCoverage' in json_ld:
            data['temporal_coverage'] = json_ld['temporalCoverage']
        
        # Extract keywords/topics
        if 'keywords' in json_ld:
            data['topics'] = json_ld['keywords']
        
        # Use filtered source count if provided, otherwise count from hasPart
        if filtered_sources_count is not None:
            data['sources_count'] = filtered_sources_count
        elif 'hasPart' in json_ld:
            data['sources_count'] = len(json_ld['hasPart'])
        
        return data
    
    def _render_signal_cards(self, signals: List[Dict[str, Any]]) -> str:
        """Render signals as HTML cards with editorial enhancements"""
        if not signals:
            return ""
        
        html = '<div class="signals-container">'
        
        for i, signal in enumerate(signals, 1):
            citations_html = ""
            if signal.get('citations'):
                citations_html = " " + " ".join([f'<sup><a href="#source-{cid}" class="citation-link">[{cid}]</a></sup>' 
                                               for cid in signal['citations']])
            
            # Add vendor disclosure if flagged
            vendor_disclosure = ""
            if signal.get('is_vendor_asserted', False):
                vendor_disclosure = ' <span class="credibility">(vendor-asserted via sponsor content)</span>'
            
            strength_class = f"badge-{signal['strength'].lower()}"
            impact_class = f"badge-{signal['impact'].lower()}"
            
            # Build metadata badges
            metadata_badges = f'''
                    <span class="badge {strength_class}">{signal['strength']}</span>
                    <span class="badge {impact_class}">{signal['impact']}</span>
                    <span class="trend-indicator">{signal['trend']}</span>'''
            
            # Add forecast badge if flagged
            if signal.get('is_forecast', False):
                metadata_badges += '<span class="badge badge-forecast">Forecast</span>'
            
            html += f'''
            <div class="signal-card">
                <div class="signal-content">
                    {signal['text']}{vendor_disclosure}{citations_html}
                </div>
                <div class="signal-metadata">
                    {metadata_badges}
                </div>
            </div>
            '''
        
        html += '</div>'
        return html
    
    def _render_provenance_banner(self, template_data: Dict[str, Any]) -> str:
        breakdown = template_data.get('confidence_breakdown')
        if not breakdown:
            return ""
        try:
            sd = float(breakdown.get('source_diversity', 0.0))
            ac = float(breakdown.get('anchor_coverage', 0.0))
            mt = float(breakdown.get('method_transparency', 0.0))
            rr = float(breakdown.get('replication_readiness', 0.0))
        except (TypeError, ValueError):
            return ""

        metrics = template_data.get('metrics') or {}
        anchor_cov = metrics.get('anchor_coverage', ac)
        quant_flags = metrics.get('quant_flags', 0)
        run_manifest = template_data.get('run_manifest') or {}
        advanced_tasks = run_manifest.get('advanced_tasks_executed') or []
        advanced_tokens = run_manifest.get('advanced_tokens_spent')

        advanced_sentence = ""
        if advanced_tasks:
            tasks_str = ", ".join(advanced_tasks)
            token_str = f" (~{advanced_tokens} tokens)" if isinstance(advanced_tokens, int) and advanced_tokens > 0 else ""
            advanced_sentence = f"Premium model auditors: {tasks_str}{token_str}."

        quant_sentence = ""
        if quant_flags:
            quant_sentence = f"Math guard flagged {quant_flags} issue(s); see quantitative appendix."

        description_parts = [part for part in [advanced_sentence, quant_sentence] if part]
        description = " ".join(description_parts)

        return f'''
        <section class="provenance-banner">
            <h2>Confidence Provenance</h2>
            <div class="provenance-grid">
                <div><span>Source Diversity</span><strong>{sd:.2f}</strong></div>
                <div><span>Anchor Coverage</span><strong>{ac:.2f}</strong></div>
                <div><span>Method Transparency</span><strong>{mt:.2f}</strong></div>
                <div><span>Replication Readiness</span><strong>{rr:.2f}</strong></div>
            </div>
            <p class="provenance-notes">Anchor coverage enforced at {anchor_cov:.2f}. {description}</p>
        </section>
        '''
    
    def _render_confidence_dials(self, template_data: Dict[str, Any]) -> str:
        """Render confidence breakdown sub-score dials for header."""
        breakdown = template_data.get('confidence_breakdown')
        if not breakdown:
            return ""
        try:
            sd = float(breakdown.get('source_diversity', 0.0))
            ac = float(breakdown.get('anchor_coverage', 0.0))
            mt = float(breakdown.get('method_transparency', 0.0))
            rr = float(breakdown.get('replication_readiness', 0.0))
        except (TypeError, ValueError):
            return ""
        
        return f'''
        <div class="confidence-dials">
            <span class="dial-item" title="Source Diversity: {sd:.2f}"><span class="dial-label">SD</span><span class="dial-value">{sd:.2f}</span></span>
            <span class="dial-item" title="Anchor Coverage: {ac:.2f}"><span class="dial-label">AC</span><span class="dial-value">{ac:.2f}</span></span>
            <span class="dial-item" title="Method Transparency: {mt:.2f}"><span class="dial-label">MT</span><span class="dial-value">{mt:.2f}</span></span>
            <span class="dial-item" title="Replication Readiness: {rr:.2f}"><span class="dial-label">RR</span><span class="dial-value">{rr:.2f}</span></span>
        </div>
        '''

    def _render_evidence_ledger(self, ledger: Dict[str, Any]) -> str:
        if not ledger or not ledger.get('claims'):
            return ""
        parts = ['<section class="evidence-ledger"><h2>Evidence Ledger</h2>']
        for claim in ledger.get('claims', []):
            claim_id = html.escape(str(claim.get('claim_id') or claim.get('id') or 'Claim'))
            claim_text = html.escape(claim.get('claim_text') or claim.get('text') or '')
            overreach = claim.get('overreach')
            wrapper_class = 'ledger-claim overreach' if overreach else 'ledger-claim'
            parts.append(f'<div class="{wrapper_class}"><h3>{claim_id}</h3><p>{claim_text}</p>')
            anchors = claim.get('anchors') or []
            if anchors:
                anchor_items = []
                for a in anchors:
                    title = html.escape(a.get('title', ''))
                    why_relevant = a.get('why_relevant', '')
                    doi = a.get('doi', '')
                    venue = a.get('venue', '')
                    
                    item = f"<li>{title}"
                    if why_relevant:
                        item += f" — {html.escape(why_relevant)}"
                    
                    # Render DOI as clickable link if available
                    if doi:
                        # Format DOI as link (e.g., https://doi.org/10.1234/example)
                        doi_url = doi if doi.startswith('http') else f"https://doi.org/{doi.lstrip('doi:').lstrip('/')}"
                        item += f' (<a href="{html.escape(doi_url)}" target="_blank" rel="noopener">DOI</a>)'
                    elif venue:
                        item += f' ({html.escape(venue)})'
                    
                    item += "</li>"
                    anchor_items.append(item)
                parts.append(f'<div class="ledger-anchors"><strong>Anchors</strong><ul>{"".join(anchor_items)}</ul></div>')
            spans = claim.get('support_spans') or []
            if spans:
                span_items = ''.join(
                    f"<li>Source {html.escape(str(span.get('source_id')))} — {html.escape(span.get('text', '')[:200])}{'...' if len(span.get('text', '')) > 200 else ''}</li>"
                    for span in spans[:3]
                )
                if len(spans) > 3:
                    span_items += f"<li>… {len(spans) - 3} more excerpts</li>"
                parts.append(f'<div class="ledger-support"><strong>Support</strong><ul>{span_items}</ul></div>')
            notes = claim.get('notes')
            if notes:
                parts.append(f'<p class="ledger-notes">{html.escape(notes)}</p>')
            parts.append('</div>')
        parts.append('</section>')
        return ''.join(parts)

    def _render_adversarial_section(self, adversarial: Dict[str, Any]) -> str:
        if not adversarial:
            return ""
        objections = adversarial.get('objections') or []
        boundaries = adversarial.get('boundary_conditions') or []
        tests = adversarial.get('falsification_tests') or []
        if not any([objections, boundaries, tests]):
            return ""
        parts = ['<section class="adversarial-review"><h2>Adversarial Review</h2>']
        if objections:
            items = ''.join(f'<li>{html.escape(item)}</li>' for item in objections)
            parts.append(f'<div><h3>Steelman Objections</h3><ul>{items}</ul></div>')
        if boundaries:
            items = ''.join(f'<li>{html.escape(item)}</li>' for item in boundaries)
            parts.append(f'<div><h3>Boundary Conditions</h3><ul>{items}</ul></div>')
        if tests:
            items = ''.join(f'<li>{html.escape(item)}</li>' for item in tests)
            parts.append(f'<div><h3>Falsification Tests</h3><ul>{items}</ul></div>')
        parts.append('</section>')
        return ''.join(parts)

    def _render_playbooks(self, playbooks: Dict[str, Any]) -> str:
        rows = playbooks.get('rows') if isinstance(playbooks, dict) else None
        if not rows:
            return ""
        header = "<tr><th>KPI</th><th>Threshold</th><th>Action</th><th>Risk Delta</th><th>Monitoring Lag</th></tr>"
        body = ''.join(
            f"<tr><td>{html.escape(row.get('kpi', ''))}</td>"
            f"<td>{html.escape(row.get('threshold', ''))}</td>"
            f"<td>{html.escape(row.get('action', ''))}</td>"
            f"<td>{html.escape(row.get('expected_delta_risk', ''))}</td>"
            f"<td>{html.escape(row.get('monitoring_lag', ''))}</td></tr>"
            for row in rows
        )
        return f'<section class="decision-playbooks"><h2>Decision Playbooks</h2><table>{header}{body}</table></section>'

    def _render_quant_patch(self, quant_patch: Dict[str, Any]) -> str:
        if not quant_patch:
            return ""
        warnings = quant_patch.get('warnings') or []
        equations = quant_patch.get('latex_equations') or []
        examples = quant_patch.get('examples') or []
        parts = ['<section class="quant-guard"><h2>Quantitative Guardrail</h2>']
        if warnings:
            warn_items = ''.join(f"<li>{html.escape(str(w.get('message') or w))}</li>" for w in warnings)
            parts.append(f'<div class="quant-warnings"><strong>Warnings</strong><ul>{warn_items}</ul></div>')
        if equations:
            eq_items = ''.join(f"<li><code>{html.escape(eq)}</code></li>" for eq in equations[:4])
            parts.append(f'<div class="quant-equations"><strong>Equations</strong><ul>{eq_items}</ul></div>')
        if examples:
            first = examples[0]
            rows = ''.join(
                f"<tr><td>{html.escape(str(k))}</td><td>{html.escape(f'{v}')}</td></tr>"
                for k, v in first.items()
            )
            parts.append(f'<div class="quant-examples"><strong>Worked Example</strong><table>{rows}</table></div>')
        parts.append('</section>')
        return ''.join(parts)

    def _render_source_citations(self, sources: List[Dict[str, Any]]) -> str:
        """Render sources - flag any invalid URLs as system errors"""
        if not sources:
            return ""
        
        html = '<div class="sources-container">'
        
        for source in sources:
            # Format publisher_date to include credibility once
            publisher_date = source['publisher_date']
            
            # Add type tag if available
            source_type = source.get('type') or ''
            type_tag = source.get('type_tag') or ''
            type_display = f" [{type_tag}]" if type_tag else ""
            type_label = f" ({source_type})" if source_type else ""
            
            if '(cred:' not in publisher_date:
                publisher_date += f" (cred: {source['credibility']:.2f})"
            
            url = source['url']
            
            # CRITICAL ERROR CHECK - should never happen with Layer 1+2
            if not url or url == "#" or "INVALID" in url or len(url) < 10:
                logger.error(f"❌ SYSTEM ERROR: Source [{source['id']}] has invalid URL: {url}")
                html += f'''
                <div class="source-item source-error" id="source-{source['id']}">
                    <span class="source-number">[{source['id']}{type_display}]</span>
                    <div class="source-content">
                        <div class="source-title">{source['title']}</div>
                        <div class="source-meta">{publisher_date}{type_label}</div>
                        <div class="source-error-message">
                            ⚠️ SYSTEM ERROR: Source URL validation failed. Contact administrator.
                        </div>
                    </div>
                </div>
                '''
                continue
            
            support_spans = source.get('support_spans', [])
            support_class = " has-support" if support_spans else ""
            support_html = ""
            if support_spans:
                tooltip_text = " | ".join(
                    f"{str(span.get('claim_id') or '')}: {span.get('text', '')}" for span in support_spans
                )
                list_items = []
                for span in support_spans[:2]:
                    claim_label = html.escape(str(span.get('claim_id') or ''))
                    excerpt = html.escape((span.get('text', '') or '')[:160])
                    list_items.append(f"<li><strong>{claim_label}</strong> {excerpt}</li>")
                if len(support_spans) > 2:
                    list_items.append(f"<li>… {len(support_spans) - 2} more excerpts in ledger</li>")
                support_html = (
                    f'<div class="source-support" title="{html.escape(tooltip_text)}">'
                    f'<ul>{"".join(list_items)}</ul>'
                    f'</div>'
                )

            html += f'''
            <div class="source-item{support_class}" id="source-{source['id']}">
                <span class="source-number">[{source['id']}{type_display}]</span>
                <div class="source-content">
                    <div class="source-title">{source['title']}</div>
                    <div class="source-meta">{publisher_date}{type_label}</div>
                    <div class="source-url">
                        <a href="{url}" target="_blank" rel="noopener">{url}</a>
                    </div>
                    {support_html}
                </div>
            </div>
            '''
        
        html += '</div>'
        return html
    
    def _render_template(self, data: Dict[str, Any]) -> str:
        """Render the HTML template with data"""
        try:
            with open(self.template_path, 'r', encoding='utf-8') as f:
                template = f.read()
            
            # Set defaults for missing template placeholders
            defaults = {
                'title': data.get('title', 'Intelligence Report'),
                'date_range': data.get('date_range', ''),
                'sources_count': data.get('sources_count', 0),
                'confidence': data.get('confidence', 0.0),
                'exec_summary': data.get('exec_summary', ''),
                'topline': data.get('topline', ''),
                'signals_html': data.get('signals_html', ''),
                'market_analysis': data.get('market_analysis', ''),
                'tech_deepdive': data.get('tech_deepdive', ''),
                'competitive': data.get('competitive', ''),
                'operator_lens': data.get('operator_lens', ''),
                'investor_lens': data.get('investor_lens', ''),
                'bd_lens': data.get('bd_lens', ''),
                'sources_html': data.get('sources_html', ''),
                'word_count': data.get('word_count', 0),
                'generation_timestamp': data.get('generation_timestamp', ''),
                # Thesis-specific defaults
                'foundations': data.get('foundations', ''),
                'formalization': data.get('formalization', ''),
                'mechanisms': data.get('mechanisms', ''),
                'applications': data.get('applications', ''),
                'limits': data.get('limits', ''),
                'synthesis': data.get('synthesis', ''),
                'thesis_alignment': data.get('thesis_alignment', 'N/A'),
                'thesis_theory_depth': data.get('thesis_theory_depth', 'N/A'),
                'thesis_clarity': data.get('thesis_clarity', 'N/A'),
                # Dynamic sections for thesis template
                'all_sections_html': data.get('all_sections_html', ''),
                'toc_html': data.get('toc_html', ''),
            }
            
            # Merge defaults with provided data (provided data takes precedence)
            merged_data = {**defaults, **data}
            
            # Log warnings for missing critical fields
            if not merged_data.get('title') or merged_data.get('title') == 'Intelligence Report':
                logger.warning("Title is missing or default")
            
            # Simple template substitution
            html = template
            for key, value in merged_data.items():
                placeholder = f"{{{{{key}}}}}"
                if isinstance(value, str):
                    html = html.replace(placeholder, value)
                elif isinstance(value, (int, float)):
                    html = html.replace(placeholder, str(value))
                else:
                    html = html.replace(placeholder, str(value))
            
            # Replace any remaining placeholders with empty string
            import re as regex_module
            html = regex_module.sub(r'\{\{(\w+)\}\}', '', html)
            
            return html
            
        except Exception as e:
            logger.error(f"Error rendering template: {str(e)}")
            return self._create_basic_html(data)
    
    def _inject_metadata(self, html: str, metadata: Dict[str, Any]) -> str:
        """Inject additional metadata into HTML"""
        # Add generation timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')
        html = html.replace('{{generation_timestamp}}', timestamp)
        
        # Add word count if available
        word_count = metadata.get('report_stats', {}).get('word_count', 0)
        html = html.replace('{{word_count}}', str(word_count))
        
        return html
    
    def _create_fallback_html(self, markdown: str, metadata: Dict[str, Any], report_dir: str = None) -> str:
        """Create a basic HTML fallback if conversion fails"""
        html = f'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Intelligence Report - STI</title>
    <style>
        body {{ font-family: Georgia, serif; max-width: 680px; margin: 0 auto; padding: 2rem; line-height: 1.6; }}
        h1 {{ color: #0066cc; border-bottom: 2px solid #e1e4e8; padding-bottom: 0.5rem; }}
        h2 {{ color: #333; margin-top: 2rem; }}
        .metadata {{ color: #666; font-size: 0.9em; margin-bottom: 2rem; }}
        pre {{ background: #f8f9fa; padding: 1rem; border-radius: 4px; overflow-x: auto; }}
        .hero-image-container {{ margin: 1rem 0; text-align: center; }}
        .hero-image-container img {{ max-width: 100%; height: auto; border-radius: 4px; }}
        .hero-image-attribution {{ font-size: 0.8em; color: #666; margin-top: 0.5rem; }}
    </style>
</head>
<body>
    <h1>Intelligence Report</h1>
    <div class="metadata">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
    <pre>{markdown}</pre>
</body>
</html>
        '''
        
        # Try to generate image even in fallback mode
        if report_dir and STIConfig and getattr(STIConfig, 'ENABLE_IMAGE_GENERATION', False):
            try:
                query = metadata.get('query', 'Technology Intelligence')
                # Determine intent from metadata or default to market
                agent_stats = metadata.get('agent_stats', {})
                intent_raw = agent_stats.get('intent', 'market')
                intent = "theory" if intent_raw == "theory" else "market"
                # Try to extract exec_summary from markdown
                exec_summary_match = re.search(r'## Executive Summary\n(.*?)(?=\n## |$)', markdown, re.DOTALL)
                exec_summary = exec_summary_match.group(1).strip() if exec_summary_match else ""
                html = self._generate_and_inject_images(html, query, report_dir, intent, exec_summary=exec_summary)
            except Exception as e:
                logger.warning(f"Image generation failed in fallback mode: {e}")
        
        return html
    
    def _create_basic_html(self, data: Dict[str, Any]) -> str:
        """Create basic HTML when template is not available"""
        title = data.get('title', 'Intelligence Report')
        exec_summary = data.get('exec_summary', '')
        topline = data.get('topline', '')
        
        return f'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - STI Intelligence</title>
    <style>
        body {{ font-family: Georgia, serif; max-width: 680px; margin: 0 auto; padding: 2rem; line-height: 1.6; }}
        h1 {{ color: #0066cc; border-bottom: 2px solid #e1e4e8; padding-bottom: 0.5rem; }}
        h2 {{ color: #333; margin-top: 2rem; }}
        .metadata {{ color: #666; font-size: 0.9em; margin-bottom: 2rem; }}
        .exec-summary {{ background: #f8f9fa; padding: 1.5rem; border-left: 4px solid #0066cc; margin: 2rem 0; }}
        .topline {{ font-size: 1.1em; margin: 1.5rem 0; }}
    </style>
</head>
<body>
    <header>
        <div class="sti-branding">Smart Technology Investments</div>
        <h1>{title}</h1>
        <div class="metadata">{data.get('date_range', '')}</div>
    </header>
    
    <article>
        <section class="exec-summary">
            <h2>Executive Summary</h2>
            <p>{exec_summary}</p>
        </section>
        
        <section class="topline">
            <h2>Topline</h2>
            <p>{topline}</p>
        </section>
        
        <section class="signals">
            <h2>Signals</h2>
            {data.get('signals_html', '')}
        </section>
        
        <section class="analysis">
            <h2>Market Analysis</h2>
            <p>{data.get('market_analysis', '')}</p>
        </section>
        
        <section class="lenses">
            <h2>Lenses</h2>
            <h3>Operator Lens</h3>
            <p>{data.get('operator_lens', '')}</p>
            <h3>Investor Lens</h3>
            <p>{data.get('investor_lens', '')}</p>
            <h3>BD Lens</h3>
            <p>{data.get('bd_lens', '')}</p>
        </section>
    </article>
    
    <footer class="sources">
        <h2>Sources</h2>
        {data.get('sources_html', '')}
    </footer>
</body>
</html>
        '''
    
    def _apply_house_style_title(self, title: str) -> str:
        """Apply house style: LLM-Driven, proper title case"""
        # Fix acronyms
        title = re.sub(r'\bLlm\b', 'LLM', title, flags=re.IGNORECASE)
        title = re.sub(r'\bAi\b', 'AI', title, flags=re.IGNORECASE)
        
        # Insert hyphens for compound modifiers
        title = re.sub(r'LLM Driven', 'LLM-Driven', title)
        
        # Title case with exceptions
        words = title.split()
        styled = []
        for i, word in enumerate(words):
            if word.lower() in ['and', 'or', 'the', 'a', 'an', 'of', 'for'] and i != 0:
                styled.append(word.lower())
            elif word in ['—', '–']:
                styled.append(word)
            else:
                styled.append(word.capitalize() if word.islower() else word)
        
        return ' '.join(styled)
    
    def _inject_vendor_disclosure(self, text: str) -> str:
        """Inject vendor disclosure tags for vendor-asserted claims"""
        # Patterns for vendor-asserted claims
        patterns = [
            (r'(\d+)\+ (LLMs?|models?)', r'\1+ \2 <span class="credibility">(vendor-asserted via sponsor content)</span>'),
            (r'(\d+)\+ providers?', r'\1+ providers <span class="credibility">(vendor-asserted via sponsor content)</span>'),
        ]
        
        for pattern, replacement in patterns:
            # Only apply once per paragraph to avoid duplication
            if '<span class="credibility">(vendor-asserted via sponsor content)</span>' not in text:
                text = re.sub(pattern, replacement, text)
        
        return text
    
    def _soften_dyna_claims(self, text: str) -> str:
        """Soften DYNA-1 deployment claims to be less assertive"""
        # Pattern for DYNA-1 commercial deployment claims
        pattern = r'DYNA-1 system is deployed commercially and performs 4 categories of complex manipulation tasks in production environments: (.*?)\.'
        replacement = r'Reports indicate DYNA-1 has commercial deployments; tasks cited include \1.'
        
        text = re.sub(pattern, replacement, text)
        
        # Additional softening patterns
        text = re.sub(r'DYNA-1.*?is deployed commercially', 'Reports indicate DYNA-1 commercial deployments', text)
        text = re.sub(r'performs 4 categories', 'tasks cited include', text)
        
        return text
    
    def _create_basic_template(self):
        """Create a basic template if none exists"""
        template_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{title}} - STI Intelligence</title>
    <style>
        /* Basic Bloomberg/FT inspired styles */
        body { 
            font-family: Georgia, serif; 
            max-width: 680px; 
            margin: 0 auto; 
            padding: 2rem; 
            line-height: 1.6; 
            color: #333;
        }
        h1 { 
            color: #0066cc; 
            border-bottom: 2px solid #e1e4e8; 
            padding-bottom: 0.5rem; 
            font-size: 2rem;
            margin-bottom: 1rem;
        }
        h2 { 
            color: #333; 
            margin-top: 2rem; 
            font-size: 1.5rem;
        }
        h3 { 
            color: #666; 
            margin-top: 1.5rem; 
            font-size: 1.2rem;
        }
        .sti-branding { 
            color: #999; 
            font-size: 0.9em; 
            margin-bottom: 0.5rem; 
        }
        .metadata { 
            color: #666; 
            font-size: 0.9em; 
            margin-bottom: 2rem; 
            border-bottom: 1px solid #e1e4e8;
            padding-bottom: 1rem;
        }
        .exec-summary { 
            background: #f8f9fa; 
            padding: 1.5rem; 
            border-left: 4px solid #0066cc; 
            margin: 2rem 0; 
            border-radius: 4px;
        }
        .provenance-banner {
            background: #eef2ff;
            border-left: 4px solid #4338ca;
            padding: 1.25rem;
            margin: 2rem 0;
            border-radius: 4px;
        }
        .provenance-banner h2 {
            margin-top: 0;
            font-size: 1.1rem;
        }
        .provenance-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 0.75rem;
            margin: 0.75rem 0;
        }
        .provenance-grid div {
            background: #fff;
            border: 1px solid #dbeafe;
            border-radius: 4px;
            padding: 0.75rem;
            text-align: center;
        }
        .provenance-grid span {
            display: block;
            font-size: 0.85em;
            color: #475569;
            margin-bottom: 0.25rem;
        }
        .provenance-grid strong {
            font-size: 1.2em;
            color: #111827;
        }
        .provenance-notes {
            font-size: 0.9em;
            color: #475569;
            margin: 0;
        }
        .topline { 
            font-size: 1.1em; 
            margin: 1.5rem 0; 
            font-weight: 500;
        }
        .signal-card {
            border: 1px solid #e1e4e8;
            border-radius: 6px;
            padding: 1rem;
            margin: 1rem 0;
            background: white;
        }
        .signal-metadata {
            margin-top: 0.5rem;
        }
        .badge {
            display: inline-block;
            padding: 0.2rem 0.5rem;
            border-radius: 3px;
            font-size: 0.8em;
            margin-right: 0.5rem;
        }
        .badge-high { background: #d4edda; color: #155724; }
        .badge-medium { background: #fff3cd; color: #856404; }
        .badge-low { background: #f8d7da; color: #721c24; }
        .trend-indicator { font-size: 1.2em; margin-left: 0.5rem; }
        .citation-link { color: #0066cc; text-decoration: none; }
        .citation-link:hover { text-decoration: underline; }
        .source-item {
            margin: 1rem 0;
            padding: 1rem;
            border-left: 3px solid #e1e4e8;
            background: #f8f9fa;
        }
        .source-item.has-support {
            border-left-color: #2563eb;
            background: #f0f6ff;
        }
        .source-number { 
            font-weight: bold; 
            color: #0066cc; 
            margin-right: 0.5rem; 
        }
        .source-title { font-weight: 500; margin-bottom: 0.25rem; }
        .source-meta { color: #666; font-size: 0.9em; margin-bottom: 0.25rem; }
        .source-url a { color: #0066cc; text-decoration: none; }
        .source-url a:hover { text-decoration: underline; }
        .credibility { color: #999; font-size: 0.8em; margin-left: 0.5rem; }
        .source-support { font-size: 0.85em; color: #334155; margin-top: 0.5rem; }
        .source-support ul { margin: 0.3rem 0 0 1.1rem; padding: 0; }
        .source-support li { margin-bottom: 0.2rem; line-height: 1.3; }
        
        @media print {
            body { max-width: none; padding: 1rem; }
            .signal-card { break-inside: avoid; }
            .source-item { break-inside: avoid; }
        }
        
        @media (max-width: 768px) {
            body { padding: 1rem; }
            h1 { font-size: 1.5rem; }
        }
    </style>
</head>
<body>
    <header>
        <div class="sti-branding">Smart Technology Investments</div>
        <h1>{{title}}</h1>
        <div class="metadata">{{date_range}} | Sources: {{sources_count}} | Confidence: {{confidence}}</div>
    </header>
    
    <article>
        <section class="exec-summary">
            <h2>Executive Summary</h2>
            <p>{{exec_summary}}</p>
        </section>
        
        <section class="topline">
            <h2>Topline</h2>
            <p>{{topline}}</p>
        </section>
        
        <section class="signals">
            <h2>Signals</h2>
            {{signals_html}}
        </section>
        
        <section class="analysis">
            <h2>Market Analysis</h2>
            <p>{{market_analysis}}</p>
            
            <h2>Technology Deep-Dive</h2>
            <p>{{tech_deepdive}}</p>
            
            <h2>Competitive Landscape</h2>
            <p>{{competitive}}</p>
        </section>
        
        <section class="lenses">
            <h2>Operator Lens</h2>
            <p>{{operator_lens}}</p>
            
            <h2>Investor Lens</h2>
            <p>{{investor_lens}}</p>
            
            <h2>BD Lens</h2>
            <p>{{bd_lens}}</p>
        </section>
    </article>
    
    <footer class="sources">
        <h2>Sources</h2>
        {{sources_html}}
    </footer>
    
    <div class="metadata">
        Generated: {{generation_timestamp}} | Word Count: {{word_count}}
    </div>
</body>
</html>'''
        
        with open(self.template_path, 'w', encoding='utf-8') as f:
            f.write(template_content)
        
        logger.info(f"Created basic template at {self.template_path}")

    def ensure_thesis_template(self):
        """Ensure thesis template exists, else create a basic thesis template"""
        template_dir = Path(self.template_path).parent
        template_dir.mkdir(exist_ok=True)
        if not os.path.exists(self.template_path):
            self._create_thesis_template()

    def _create_thesis_template(self):
        """Create a basic thesis-specific template"""
        template_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{title}} - STI Intelligence (Thesis)</title>
    <style>
        body { font-family: Georgia, serif; max-width: 760px; margin: 0 auto; padding: 2rem; line-height: 1.6; color: #333; }
        h1 { color: #0066cc; border-bottom: 2px solid #e1e4e8; padding-bottom: 0.5rem; }
        h2 { color: #333; margin-top: 2rem; }
        h3 { color: #666; margin-top: 1.2rem; }
        .metadata { color: #666; font-size: 0.9em; margin-bottom: 2rem; }
        .toc { background: #f8f9fa; padding: 1rem; border-left: 4px solid #0066cc; }
        .badge { display: inline-block; padding: 0.2rem 0.5rem; border-radius: 3px; font-size: 0.8em; margin-right: 0.5rem; }
        .badge-alignment { background: #e7f3ff; color: #004a99; }
        .badge-theory { background: #e8f5e9; color: #1b5e20; }
        .badge-clarity { background: #fff3cd; color: #856404; }
    </style>
</head>
<body>
    <header>
        <div class="sti-branding">Smart Technology Investments</div>
        <h1>{{title}}</h1>
        <div class="metadata">{{date_range}} | Sources: {{sources_count}} | Confidence: {{confidence}}</div>
        <div class="metadata">Alignment: <span class="badge badge-alignment">{{thesis_alignment}}</span>
            Theory Depth: <span class="badge badge-theory">{{thesis_theory_depth}}</span>
            Clarity: <span class="badge badge-clarity">{{thesis_clarity}}</span></div>
    </header>

    <nav class="toc">
        <strong>Outline</strong>
        <ul>
            <li><a href="#foundations">Foundations</a></li>
            <li><a href="#formalization">Formalization</a></li>
            <li><a href="#mechanisms">Mechanisms</a></li>
            <li><a href="#applications">Applications</a></li>
            <li><a href="#limits">Limits & Open Questions</a></li>
            <li><a href="#synthesis">Synthesis & Current Developments</a></li>
            <li><a href="#sources">Sources</a></li>
        </ul>
    </nav>

    <section id="foundations">
        <h2>Foundations</h2>
        {{foundations}}
    </section>
    <section id="formalization">
        <h2>Formalization</h2>
        {{formalization}}
    </section>
    <section id="mechanisms">
        <h2>Mechanisms</h2>
        {{mechanisms}}
    </section>
    <section id="applications">
        <h2>Applications</h2>
        {{applications}}
    </section>
    <section id="limits">
        <h2>Limits & Open Questions</h2>
        {{limits}}
    </section>
    <section id="synthesis">
        <h2>Synthesis & Current Developments</h2>
        {{synthesis}}
    </section>

    <footer id="sources">
        <h2>Sources</h2>
        {{sources_html}}
        <div class="metadata">Generated: {{generation_timestamp}} | Word Count: {{word_count}}</div>
    </footer>
</body>
</html>'''
        with open(self.template_path, 'w', encoding='utf-8') as f:
            f.write(template_content)
        logger.info(f"Created thesis template at {self.template_path}")


def main():
    """Example usage of HTML Converter Agent"""
    
    # Example markdown report
    sample_markdown = """# Tech Brief — AI Technology Trends
Date range: Oct 21–Oct 28, 2025 | Sources: 5 | Confidence: 0.80

## Executive Summary
AI infrastructure is shifting from model-first to governed, orchestrated stacks.

## Topline
Elloe AI fact-checked 100% of LLM outputs via an SDK/API layer.

## Signals (strength × impact × direction)
- 2025-10-27 — Elloe AI fact-checked 100% of LLM responses — strength: High | impact: High | trend: ↗︎  [^1]
- 2025-10-28 — Nexos.ai raised $8,000,000 in funding — strength: High | impact: Medium | trend: ↗︎  [^2]

## Market Analysis
The recent wave of startups signals a maturation of AI infrastructure.

## Technology Deep-Dive
The recent set of products points to a maturing stack.

## Competitive Landscape
Winners/Losers Identification: The near-term winners are startups.

## Operator Lens
Operators should view the recent announcements as a call to re-architect.

## Investor Lens
The flow of product announcements signals a capital reallocation.

## BD Lens
The current landscape creates a clear BD playbook.

## Sources
[^1]: Elloe AI wants to be the 'immune system' for AI — TechCrunch, 2025-10-28. (cred: 0.90) — https://techcrunch.com/2025/10/28/elloe-ai-wants-to-be-the-immune-system-for-ai-check-it-out-at-disrupt-2025/
[^2]: Meet the AI Disruptors 60 — TechCrunch, 2025-10-28. (cred: 0.90) — https://techcrunch.com/sponsor/greenfield-partners/meet-the-ai-disruptors-60-the-startups-defining-ais-future/
"""
    
    # Example JSON-LD data
    sample_json_ld = {
        "aggregateRating": {"ratingValue": 0.80},
        "wordCount": 1200,
        "temporalCoverage": "2025-10-21/2025-10-28",
        "keywords": ["AI", "Technology", "Infrastructure"]
    }
    
    # Example metadata
    sample_metadata = {
        "report_stats": {"word_count": 1200},
        "generation_timestamp": datetime.now().isoformat()
    }
    
    # Convert to HTML
    converter = HTMLConverterAgent()
    html_output = converter.convert(sample_markdown, sample_json_ld, sample_metadata)
    
    print("HTML Conversion Complete!")
    print(f"Generated HTML length: {len(html_output)} characters")
    
    # Save to file for testing
    with open("test_output.html", "w", encoding="utf-8") as f:
        f.write(html_output)
    print("Saved test output to test_output.html")


if __name__ == "__main__":
    main()
