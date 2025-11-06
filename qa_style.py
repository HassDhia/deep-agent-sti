"""
Style QA Module for Google Slides Presentations

Validates that generated presentations meet Cashmere style guidelines:
- Fonts, sizes, colors
- Layout positioning
- Bullet counts and lengths
- Image placeholders
- Line spacing and paragraph styles
"""

import logging
from typing import Dict, Any, List, Optional
from slides_template_config import SlidesTemplateConfig

logger = logging.getLogger(__name__)


class StyleQA:
    """
    Automated style quality assurance for Google Slides presentations.
    
    Validates fonts, colors, layout, bullets, and other style elements
    against Cashmere design system standards.
    """
    
    # Tolerance values for validation
    FONT_SIZE_TOLERANCE = 2  # ±2 PT for font sizes
    POSITION_TOLERANCE = 4  # ±4 PT for layout positions
    COLOR_TOLERANCE = 0.1  # ±0.1 RGB for color matching
    
    def __init__(self, slides_service):
        """
        Initialize Style QA.
        
        Args:
            slides_service: Google Slides API service object
        """
        self.slides_service = slides_service
    
    def validate_presentation(self, presentation_id: str) -> Dict[str, Any]:
        """
        Validate a generated presentation against style guidelines.
        
        Args:
            presentation_id: Google Slides presentation ID
        
        Returns:
            Dict with 'errors', 'warnings', 'info' lists
        """
        report = {
            'errors': [],
            'warnings': [],
            'info': []
        }
        
        try:
            # Fetch presentation
            presentation = self.slides_service.presentations().get(
                presentationId=presentation_id
            ).execute()
            
            slides = presentation.get('slides', [])
            
            # Validate each slide
            for slide_index, slide in enumerate(slides):
                slide_id = slide.get('objectId')
                page_elements = slide.get('pageElements', [])
                
                # Validate fonts
                font_errors = self._validate_fonts(page_elements, slide_index)
                report['errors'].extend(font_errors)
                
                # Validate font sizes
                size_errors, size_warnings = self._validate_font_sizes(
                    page_elements, slide_index
                )
                report['errors'].extend(size_errors)
                report['warnings'].extend(size_warnings)
                
                # Validate colors
                color_errors = self._validate_colors(page_elements, slide_index)
                report['errors'].extend(color_errors)
                
                # Validate paragraph styles
                para_errors = self._validate_paragraph_styles(
                    page_elements, slide_index
                )
                report['errors'].extend(para_errors)
                
                # Validate layout positioning
                layout_warnings = self._validate_layout_positioning(
                    page_elements, slide_index
                )
                report['warnings'].extend(layout_warnings)
                
                # Validate bullets
                bullet_errors = self._validate_bullets(
                    page_elements, slide_index
                )
                report['errors'].extend(bullet_errors)
                
                # Check for image placeholders
                placeholder_info = self._check_image_placeholders(
                    page_elements, slide_index
                )
                report['info'].extend(placeholder_info)
            
            logger.info(
                f"Style QA complete: {len(report['errors'])} errors, "
                f"{len(report['warnings'])} warnings, "
                f"{len(report['info'])} info items"
            )
            
        except Exception as e:
            logger.error(f"Style QA validation failed: {e}")
            report['errors'].append({
                'type': 'validation_error',
                'message': f"Failed to validate presentation: {str(e)}"
            })
        
        return report
    
    def _validate_fonts(self, page_elements: List[Dict], slide_index: int) -> List[Dict]:
        """Validate that all fonts are in the fallback chain."""
        errors = []
        fallbacks = SlidesTemplateConfig.FONT_FALLBACKS or []
        
        for element in page_elements:
            shape = element.get('shape', {})
            text = shape.get('text', {})
            text_elements = text.get('textElements', [])
            
            for text_elem in text_elements:
                text_run = text_elem.get('textRun', {})
                style = text_run.get('style', {})
                font_family = style.get('fontFamily')
                
                if font_family and fallbacks:
                    if font_family not in fallbacks:
                        errors.append({
                            'type': 'font_family',
                            'slide': slide_index,
                            'element': element.get('objectId'),
                            'message': f"Font '{font_family}' not in fallback chain. "
                                      f"Expected one of: {fallbacks}"
                        })
        
        return errors
    
    def _validate_font_sizes(self, page_elements: List[Dict], 
                             slide_index: int) -> tuple:
        """Validate font sizes match expected ranges."""
        errors = []
        warnings = []
        
        # Expected sizes from config
        hero_title_size = SlidesTemplateConfig.get_font_size('HERO_TITLE')
        hero_subtitle_size = SlidesTemplateConfig.get_font_size('HERO_SUBTITLE')
        content_title_size = SlidesTemplateConfig.get_font_size('CONTENT_TITLE')
        body_size = SlidesTemplateConfig.get_font_size('BODY')
        
        for element in page_elements:
            shape = element.get('shape', {})
            text = shape.get('text', {})
            text_elements = text.get('textElements', [])
            
            for text_elem in text_elements:
                text_run = text_elem.get('textRun', {})
                style = text_run.get('style', {})
                fontSize = style.get('fontSize', {})
                
                if fontSize:
                    magnitude = fontSize.get('magnitude', 0)
                    unit = fontSize.get('unit', 'PT')
                    
                    if unit == 'PT':
                        # Check if size is within expected ranges
                        is_title = magnitude >= (content_title_size - self.FONT_SIZE_TOLERANCE)
                        is_body = abs(magnitude - body_size) <= self.FONT_SIZE_TOLERANCE
                        
                        if not (is_title or is_body):
                            if magnitude > 100:  # Very large - likely error
                                errors.append({
                                    'type': 'font_size',
                                    'slide': slide_index,
                                    'element': element.get('objectId'),
                                    'message': f"Font size {magnitude}PT is outside expected "
                                              f"ranges (title: {content_title_size}±{self.FONT_SIZE_TOLERANCE}, "
                                              f"body: {body_size}±{self.FONT_SIZE_TOLERANCE})"
                                })
                            else:
                                warnings.append({
                                    'type': 'font_size',
                                    'slide': slide_index,
                                    'element': element.get('objectId'),
                                    'message': f"Font size {magnitude}PT may be outside "
                                              f"expected range"
                                })
        
        return errors, warnings
    
    def _validate_colors(self, page_elements: List[Dict], slide_index: int) -> List[Dict]:
        """Validate colors match theme (charcoal text, ivory background, accent for rules)."""
        errors = []
        
        # Get theme colors
        primary_text_color = SlidesTemplateConfig.resolve_theme_color('PRIMARY_TEXT')
        accent_color = SlidesTemplateConfig.resolve_theme_color('ACCENT')
        background_color = SlidesTemplateConfig.resolve_theme_color('BACKGROUND')
        
        for element in page_elements:
            shape = element.get('shape', {})
            
            # Check text color
            text = shape.get('text', {})
            text_elements = text.get('textElements', [])
            
            for text_elem in text_elements:
                text_run = text_elem.get('textRun', {})
                style = text_run.get('style', {})
                foreground_color = style.get('foregroundColor', {})
                
                if foreground_color:
                    opaque_color = foreground_color.get('opaqueColor', {})
                    rgb_color = opaque_color.get('rgbColor', {})
                    
                    if rgb_color:
                        # Check if text color is accent (should only be on rules, not text)
                        r = rgb_color.get('red', 0)
                        g = rgb_color.get('green', 0)
                        b = rgb_color.get('blue', 0)
                        
                        # Simple heuristic: if color is very different from charcoal,
                        # it might be accent on text (error)
                        # (This is a simplified check - could be enhanced)
                        primary_rgb = primary_text_color.get('rgbColor', {})
                        if primary_rgb:
                            primary_r = primary_rgb.get('red', 0)
                            primary_g = primary_rgb.get('green', 0)
                            primary_b = primary_rgb.get('blue', 0)
                            
                            # Check if color is significantly different (possible accent)
                            diff = abs(r - primary_r) + abs(g - primary_g) + abs(b - primary_b)
                            if diff > 0.3:  # Significant difference
                                errors.append({
                                    'type': 'text_color',
                                    'slide': slide_index,
                                    'element': element.get('objectId'),
                                    'message': f"Text color ({r:.2f}, {g:.2f}, {b:.2f}) may be "
                                              f"accent color. Text should be charcoal for "
                                              f"readability."
                                })
            
            # Check background color (for page)
            # (This would be checked at slide level, not element level)
        
        return errors
    
    def _validate_paragraph_styles(self, page_elements: List[Dict], 
                                  slide_index: int) -> List[Dict]:
        """Validate paragraph styles (line spacing, spacing mode)."""
        errors = []
        
        expected_line_spacing = SlidesTemplateConfig.LINE_SPACING
        expected_spacing_mode = SlidesTemplateConfig.SPACING_MODE
        
        for element in page_elements:
            shape = element.get('shape', {})
            text = shape.get('text', {})
            text_elements = text.get('textElements', [])
            
            for text_elem in text_elements:
                text_run = text_elem.get('textRun', {})
                paragraph_style = text_run.get('paragraphStyle', {})
                
                line_spacing = paragraph_style.get('lineSpacing', {})
                spacing_mode = paragraph_style.get('spacingMode')
                
                if line_spacing and isinstance(line_spacing, dict):
                    spacing_magnitude = line_spacing.get('magnitude', 0)
                    # Check if line spacing matches expected (115%)
                    if abs(spacing_magnitude - expected_line_spacing) > 5:
                        errors.append({
                            'type': 'line_spacing',
                            'slide': slide_index,
                            'element': element.get('objectId'),
                            'message': f"Line spacing {spacing_magnitude}% does not match "
                                      f"expected {expected_line_spacing}%"
                        })
                
                if spacing_mode and spacing_mode != expected_spacing_mode:
                    errors.append({
                        'type': 'spacing_mode',
                        'slide': slide_index,
                        'element': element.get('objectId'),
                        'message': f"Spacing mode '{spacing_mode}' does not match expected "
                                  f"'{expected_spacing_mode}'"
                    })
        
        return errors
    
    def _validate_layout_positioning(self, page_elements: List[Dict], 
                                    slide_index: int) -> List[Dict]:
        """Validate layout positioning (title Y, margins)."""
        warnings = []
        
        # This would require comparing against expected positions
        # Simplified check: ensure elements are within slide bounds
        
        for element in page_elements:
            transform = element.get('transform', {})
            translate_x = transform.get('translateX', {})
            translate_y = transform.get('translateY', {})
            
            if isinstance(translate_x, dict):
                x = translate_x.get('magnitude', 0)
                if x < 0 or x > 9144000:  # Slide width in EMU
                    warnings.append({
                        'type': 'layout_position',
                        'slide': slide_index,
                        'element': element.get('objectId'),
                        'message': f"Element X position {x} is outside slide bounds"
                    })
        
        return warnings
    
    def _validate_bullets(self, page_elements: List[Dict], 
                         slide_index: int) -> List[Dict]:
        """Validate bullet counts and lengths."""
        errors = []
        
        max_bullets = SlidesTemplateConfig.MAX_BULLETS
        max_chars = SlidesTemplateConfig.MAX_BULLET_CHARS
        
        for element in page_elements:
            shape = element.get('shape', {})
            text = shape.get('text', {})
            text_elements = text.get('textElements', [])
            
            # Check if element has bullets
            has_bullets = False
            bullet_count = 0
            longest_bullet = 0
            
            for text_elem in text_elements:
                text_run = text_elem.get('textRun', {})
                paragraph_style = text_run.get('paragraphStyle', {})
                
                # Check for bullet markers
                if paragraph_style.get('bullet') or text_run.get('text', '').startswith('•'):
                    has_bullets = True
                    bullet_text = text_run.get('text', '')
                    bullet_count += 1
                    longest_bullet = max(longest_bullet, len(bullet_text))
            
            if has_bullets:
                if bullet_count > max_bullets:
                    errors.append({
                        'type': 'bullet_count',
                        'slide': slide_index,
                        'element': element.get('objectId'),
                        'message': f"Bullet count {bullet_count} exceeds maximum {max_bullets}"
                    })
                
                if longest_bullet > max_chars:
                    errors.append({
                        'type': 'bullet_length',
                        'slide': slide_index,
                        'element': element.get('objectId'),
                        'message': f"Longest bullet ({longest_bullet} chars) exceeds "
                                  f"maximum {max_chars} chars"
                    })
        
        return errors
    
    def _check_image_placeholders(self, page_elements: List[Dict], 
                                  slide_index: int) -> List[Dict]:
        """Check for image placeholders (indicating failed image loads)."""
        info = []
        
        for element in page_elements:
            shape = element.get('shape', {})
            text = shape.get('text', {})
            text_content = text.get('content', '')
            
            # Check for placeholder text
            if 'Image not available' in text_content or 'placeholder' in text_content.lower():
                info.append({
                    'type': 'image_placeholder',
                    'slide': slide_index,
                    'element': element.get('objectId'),
                    'message': "Image placeholder detected - image may have failed to load"
                })
        
        return info

