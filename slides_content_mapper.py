"""
Content Schema Mapper for Cashmere Style Slide Generation

Maps structured report data to slide content objects, enabling scalable
content generation with voice/tone alignment.
"""

from typing import Dict, Any, List, Optional, Union, Tuple
from dataclasses import dataclass, field
from enum import Enum

from slides_template_config import SlidesTemplateConfig


class SlideLayoutType(Enum):
    """Layout types for slide creation"""
    TITLE = "title"
    CONTENT = "content"
    SECTION = "section"
    IMAGE_LEFT = "image_left"
    IMAGE_RIGHT = "image_right"
    TWO_COLUMN = "two_column"
    BLANK = "blank"


@dataclass
class TitleSlide:
    """Title slide content schema"""
    title: str
    subtitle: Optional[str] = None
    date: Optional[str] = None
    logo_url: Optional[str] = None
    background_image_url: Optional[str] = None
    overlay_alpha: float = 0.30


@dataclass
class ContentSlide:
    """Content slide with heading and bullets"""
    heading: str
    bullets: List[str] = field(default_factory=list)
    quote: Optional[str] = None
    image_url: Optional[str] = None
    image_position: str = "right"  # "left" or "right"


@dataclass
class ImageSlide:
    """Image-focused slide"""
    title: str
    image_url: str
    caption: Optional[str] = None
    image_position: str = "left"  # "left" or "right"


@dataclass
class CollageSlide:
    """Collage slide with multiple images"""
    images: List[str] = field(default_factory=list)  # List of image URLs
    big_word: Optional[str] = None
    sticker_url: Optional[str] = None


@dataclass
class SectionSlide:
    """Section header slide"""
    title: str
    subtitle: Optional[str] = None
    kicker: Optional[str] = None  # Optional small caps text above title


SlideContent = Union[TitleSlide, ContentSlide, ImageSlide, CollageSlide, SectionSlide]


class SlidesContentMapper:
    """
    Maps report data to structured slide content objects.
    
    Handles voice/tone alignment and content transformation.
    """
    
    # Voice/tone rules
    MAX_TITLE_LENGTH = 60  # Characters
    MAX_BULLET_LENGTH = 100  # Characters
    MAX_BULLETS_PER_SLIDE = 5
    
    @staticmethod
    def map_report_to_slides(
        slide_data: Dict[str, Any],
        report_dir: str
    ) -> List[SlideContent]:
        """
        Map report data to slide content objects.
        
        Args:
            slide_data: Extracted slide data from report
            report_dir: Path to report directory
            
        Returns:
            List of slide content objects in order
        """
        slides = []
        
        # 1. Title slide
        title_slide = TitleSlide(
            title=slide_data.get('title', ''),
            subtitle=slide_data.get('subtitle', ''),
            date=slide_data.get('date', ''),
            logo_url=slide_data.get('logo_url'),
            background_image_url=slide_data.get('hero_image'),
        )
        slides.append(title_slide)
        
        # 2. Collage slide (if images available)
        section_images = slide_data.get('section_images', [])
        if section_images:
            collage_slide = CollageSlide(
                images=section_images[:8],  # Max 8 images
                big_word=slide_data.get('big_word'),
                sticker_url=slide_data.get('sticker_url'),
            )
            slides.append(collage_slide)
        
        # 3. Content slides from sections with section dividers
        sections = slide_data.get('sections', {})
        
        # Use configurable section labels from config
        section_labels = SlidesTemplateConfig.SECTION_LABELS
        
        # Track which sections we've processed to avoid duplicates
        processed_sections = set()
        
        for section_name in section_labels:
            if section_name in sections and section_name not in processed_sections:
                processed_sections.add(section_name)
                
                # Create section divider slide before content
                section_slide = SectionSlide(
                    title=section_name,
                    kicker=None  # Can be enhanced later with kicker text
                )
                slides.append(section_slide)
                
                # Extract heading and bullets
                section_text = sections[section_name]
                heading, bullets = SlidesContentMapper._parse_section(section_text)
                
                if heading or bullets:
                    content_slide = ContentSlide(
                        heading=heading or section_name,
                        bullets=bullets,
                    )
                    slides.append(content_slide)
        
        # Handle any remaining sections not in SECTION_LABELS
        for section_name, section_text in sections.items():
            if section_name not in processed_sections:
                # Extract heading and bullets
                heading, bullets = SlidesContentMapper._parse_section(section_text)
                
                if heading or bullets:
                    content_slide = ContentSlide(
                        heading=heading or section_name,
                        bullets=bullets,
                    )
                    slides.append(content_slide)
        
        return slides
    
    @staticmethod
    def _parse_section(section_text: str) -> Tuple[str, List[str]]:
        """
        Parse section text into heading and bullets.
        
        Enhanced to:
        - Split long paragraphs (>3 sentences) into multiple bullets
        - Detect list-like content (numbered items) and convert to separate bullets
        - Ensure bullets are concise and digestible
        
        Args:
            section_text: Raw section text
            
        Returns:
            Tuple of (heading, bullets)
        """
        lines = section_text.split('\n')
        heading = ""
        bullets = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Detect numbered list items: (1), (2), 1., 2., etc.
            import re
            numbered_pattern = r'^[\(\[]?(\d+)[\.\)\]]?\s+(.+)$'
            numbered_match = re.match(numbered_pattern, line)
            if numbered_match:
                bullet_text = numbered_match.group(2).strip()
                if bullet_text:
                    bullets.append(bullet_text)
                continue
            
            # Check if it's a heading (short line, no bullet marker)
            if not line.startswith('-') and not line.startswith('*') and len(line) < 80:
                if not heading:
                    heading = line
                else:
                    # Convert to bullet if it's a short line
                    if len(line) < 100:
                        bullets.append(line)
            elif line.startswith('-') or line.startswith('*'):
                # Bullet point
                bullet_text = line.lstrip('- *').strip()
                if bullet_text:
                    bullets.append(bullet_text)
            else:
                # Long paragraph - split into bullets if >3 sentences
                sentences = line.split('. ')
                num_sentences = len([s for s in sentences if s.strip()])
                
                if num_sentences > 3 or len(line) > 100:
                    # Split long paragraphs into bullets
                    for sentence in sentences:
                        sentence = sentence.strip()
                        if not sentence:
                            continue
                        # Ensure sentence ends with period
                        if not sentence.endswith('.'):
                            sentence += '.'
                        # If sentence is still too long, try to shorten
                        if len(sentence) > 120:
                            # Split on commas and take meaningful parts
                            parts = sentence.split(',')
                            for part in parts:
                                part = part.strip()
                                if part and len(part) > 20:  # Only add meaningful parts
                                    if not part.endswith('.'):
                                        part += '.'
                                    bullets.append(part)
                        else:
                            bullets.append(sentence)
                else:
                    # Short paragraph - keep as single bullet
                    bullets.append(line)
        
        # Limit bullets and ensure they're concise
        limited_bullets = bullets[:SlidesContentMapper.MAX_BULLETS_PER_SLIDE]
        return heading, limited_bullets
    
    @staticmethod
    def apply_voice_rules(text: str, text_type: str = "body") -> str:
        """
        Apply Cashmere voice and tone rules: confident, poetic, grounded.
        
        Args:
            text: Input text
            text_type: Type of text ('title', 'heading', 'body', 'bullet')
            
        Returns:
            Processed text with confident, assertive tone
        """
        if not text:
            return text
        
        # Remove hedging words for confident tone
        hedging_replacements = {
            'possibly ': '',
            'might ': '',
            'could ': '',
            'may ': '',
            'perhaps ': '',
            'potentially ': '',
            'This could imply': 'This implies',
            'This might mean': 'This means',
            'This could suggest': 'This suggests',
            'will be able to': 'can',
            'should be able to': 'can',
        }
        for old, new in hedging_replacements.items():
            text = text.replace(old, new)
        
        # Active voice improvements (simple patterns)
        passive_to_active = {
            'is considered': 'considers',
            'are considered': 'consider',
            'is expected': 'expects',
            'are expected': 'expect',
            'is seen': 'sees',
            'are seen': 'see',
        }
        for passive, active in passive_to_active.items():
            # Simple replacement - could be enhanced with NLP
            text = text.replace(f' {passive} ', f' {active} ')
        
        # Shorten sentences for punchiness (split on periods, keep concise)
        if text_type in ['body', 'bullet']:
            sentences = text.split('. ')
            shortened = []
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                # Remove trailing period if present (we'll add it back)
                if sentence.endswith('.'):
                    sentence = sentence[:-1]
                # If sentence is too long (>120 chars), try to shorten
                if len(sentence) > 120:
                    # Split on commas and take first part if it's meaningful
                    parts = sentence.split(',')
                    if len(parts) > 1 and len(parts[0]) < 80:
                        sentence = parts[0].strip()
                shortened.append(sentence)
            text = '. '.join(shortened)
            if text and not text.endswith('.'):
                text += '.'
        
        # Power verb map for confident tone
        power_verb_map = {
            'enable': 'unlock',
            'make': 'deliver',
            'help': 'drive',
            'could': 'can',
            'should': 'will',
            'might': 'can',
        }
        # Apply power verbs only outside quantified statements
        # (preserve numbers, dates, named entities)
        words = text.split()
        for i, word in enumerate(words):
            # Check if word is in map (case-insensitive)
            word_lower = word.lower().rstrip('.,!?;:')
            if word_lower in power_verb_map:
                # Check if it's part of a quantified statement
                # (simple heuristic: check if nearby words are numbers)
                nearby_text = ' '.join(words[max(0, i-2):min(len(words), i+3)])
                if not any(c.isdigit() for c in nearby_text):
                    # Replace with power verb (preserve capitalization)
                    replacement = power_verb_map[word_lower]
                    if word[0].isupper():
                        replacement = replacement.capitalize()
                    words[i] = word.replace(word_lower, replacement)
        text = ' '.join(words)
        
        # Word mapping for more dynamic titles/headings
        if text_type in ['title', 'heading']:
            boring_word_map = {
                'considerations': 'priorities',
                'analysis': 'insights',
                'overview': 'perspective',
                'summary': 'takeaways',
                'review': 'assessment',
            }
            words = text.split()
            words = [boring_word_map.get(word.lower(), word) if word.lower() in boring_word_map else word 
                    for word in words]
            text = ' '.join(words)
            text = SlidesContentMapper._to_title_case(text)
            text = text[:SlidesContentMapper.MAX_TITLE_LENGTH]
        
        # Truncate long bullets
        elif text_type == 'bullet':
            if len(text) > SlidesContentMapper.MAX_BULLET_LENGTH:
                # Try to truncate at sentence boundary
                if '.' in text[:SlidesContentMapper.MAX_BULLET_LENGTH]:
                    text = text[:text.rfind('.', 0, SlidesContentMapper.MAX_BULLET_LENGTH) + 1]
                else:
                    text = text[:SlidesContentMapper.MAX_BULLET_LENGTH - 3] + '...'
        
        # Remove extra whitespace
        text = ' '.join(text.split())
        
        return text
    
    @staticmethod
    def _to_title_case(text: str) -> str:
        """Convert text to title case (capitalize first letter of each word)"""
        words = text.split()
        return ' '.join(word.capitalize() for word in words)
    
    @staticmethod
    def process_bullet_points(bullets: List[str]) -> List[str]:
        """
        Process bullet points for consistency and parallel structure.
        
        Args:
            bullets: List of bullet text strings
            
        Returns:
            Processed bullets with consistent formatting and parallel structure
        """
        processed = []
        for bullet in bullets:
            # Apply voice rules
            processed_bullet = SlidesContentMapper.apply_voice_rules(
                bullet, text_type='bullet'
            )
            
            # Ensure bullet starts with capital letter
            if processed_bullet:
                processed_bullet = (
                    processed_bullet[0].upper() + processed_bullet[1:]
                    if len(processed_bullet) > 1
                    else processed_bullet.upper()
                )
                processed.append(processed_bullet)
        
        # Enforce parallel structure (ensure all bullets start with same verb form if possible)
        # This is a simple heuristic - could be enhanced with NLP
        if len(processed) > 1:
            # Check if first words are verbs (simple heuristic: ends with common verb endings)
            first_words = [b.split()[0].lower() if b.split() else '' for b in processed]
            # If all start with same verb form (e.g., all end in -ing, -ed, or base form), keep as-is
            # Otherwise, try to normalize to base form (simplified - would need NLP for accuracy)
            pass  # Parallel structure enforcement could be added here with more sophisticated NLP
        
        return processed
    
    @staticmethod
    def slide_content_to_api_requests(
        slide_content: SlideContent,
        slide_id: str,
        template_elements: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """
        Convert slide content object to API requests.
        
        This is a helper method that can be used to generate API requests
        from content objects. The actual implementation in slides_generator.py
        will handle the requests, but this provides a structured way to
        think about the mapping.
        
        Args:
            slide_content: Slide content object
            slide_id: Target slide ID
            template_elements: Optional element mapping from template
            
        Returns:
            List of API request dictionaries
        """
        requests = []
        
        if isinstance(slide_content, TitleSlide):
            # Title slide requests would go here
            # This is a placeholder - actual implementation in slides_generator
            pass
        elif isinstance(slide_content, ContentSlide):
            # Content slide requests
            pass
        elif isinstance(slide_content, CollageSlide):
            # Collage slide requests
            pass
        
        return requests

