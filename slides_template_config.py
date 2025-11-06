"""
Template Configuration for Cashmere Style Slide Generation

Separates style constants, theme colors, fonts, layouts, and placeholder registry
from the main slide generator logic for easier maintenance and customization.
"""

from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass


@dataclass
class ThemeColor:
    """Theme color definition with theme reference and RGB fallback"""
    theme_name: Optional[str] = None  # e.g., "ACCENT1", "DARK1"
    rgb_fallback: Optional[Dict[str, float]] = None  # {'red': 0.0, 'green': 0.0, 'blue': 0.0}


@dataclass
class FontConfig:
    """Font family configuration"""
    primary: str
    fallback: str
    title: str
    body: str
    meta: str
    fallbacks: List[str] = None  # List of fallback fonts in order of preference


@dataclass
class LayoutMapping:
    """Mapping between logical layout names and template layout IDs"""
    title: Optional[str] = None
    content: Optional[str] = None
    section: Optional[str] = None
    image_left: Optional[str] = None
    image_right: Optional[str] = None
    two_column: Optional[str] = None


class SlidesTemplateConfig:
    """
    Configuration class for Cashmere-style slide templates.
    
    Cashmere Style Philosophy:
    - Confident, poetic, grounded voice
    - Clean typography with clear hierarchy
    - Subtle, refined color palette (charcoal text, accent highlights)
    - Generous spacing and elegant line height
    - Professional sans-serif fonts (Montserrat/Lato)
    - Consistent visual rhythm across slides
    
    This configuration separates style constants from logic for easier maintenance
    and brand consistency across all generated decks.
    """
    
    # ============================================================================
    # Theme Colors
    # ============================================================================
    # Use theme color references when available, with RGB fallbacks
    
    THEME_COLORS = {
        'PRIMARY_TEXT': ThemeColor(
            theme_name=None,  # Use RGB for text colors
            # Cashmere: Charcoal instead of pure black for softer, refined look
            rgb_fallback={'red': 0.2, 'green': 0.2, 'blue': 0.2}  # #333333 Charcoal
        ),
        'SECONDARY_TEXT': ThemeColor(
            theme_name=None,
            rgb_fallback={'red': 0.2, 'green': 0.2, 'blue': 0.2}  # Dark gray
        ),
        'SUBTLE_TEXT': ThemeColor(
            theme_name=None,
            rgb_fallback={'red': 0.5, 'green': 0.5, 'blue': 0.5}  # Medium gray
        ),
        'HERO_TEXT': ThemeColor(
            theme_name=None,
            rgb_fallback={'red': 1.0, 'green': 1.0, 'blue': 1.0}  # White
        ),
        'DATE_TEXT': ThemeColor(
            theme_name=None,
            rgb_fallback={'red': 0.8, 'green': 0.8, 'blue': 0.8}  # Light gray
        ),
        'OVERLAY': ThemeColor(
            theme_name=None,
            rgb_fallback={'red': 0.1, 'green': 0.1, 'blue': 0.1}  # Dark overlay
        ),
        'ACCENT': ThemeColor(
            theme_name='ACCENT1',  # Use theme accent color if available
            # Cashmere accent color - update with actual brand color
            rgb_fallback={'red': 0.203, 'green': 0.286, 'blue': 0.369}  # Dark blue
        ),
        'BULLET_COLOR': ThemeColor(
            theme_name='ACCENT1',  # Use accent color for bullets
            rgb_fallback={'red': 0.203, 'green': 0.286, 'blue': 0.369}  # Match accent
        ),
        'BACKGROUND': ThemeColor(
            theme_name='BACKGROUND1',  # Use theme background
            # Cashmere: Off-white or subtle textured background
            rgb_fallback={'red': 0.98, 'green': 0.97, 'blue': 0.95}  # Light ivory
        ),
    }
    
    # Alternate color for placeholder shapes when images fail
    ALTERNATE_IMAGE_FILL_COLOR = ThemeColor(
        theme_name=None,
        rgb_fallback={'red': 0.9, 'green': 0.9, 'blue': 0.9}  # Light gray placeholder
    )
    
    # ============================================================================
    # Typography - Cashmere Style
    # ============================================================================
    # Cashmere brand font: Use a modern sans-serif Google Font (e.g., Montserrat, Lato)
    # If brand font not available, fallback to Roboto, then Arial
    # All fonts should be Google Fonts for API compatibility
    
    # Primary Cashmere font (should be a Google Font)
    CASHMERE_FONT_FAMILY = 'Montserrat'  # Modern sans-serif, Cashmere brand font
    # Alternative: 'Lato' or actual brand font name if it's a Google Font
    
    # Font fallback chain (prefer Google Fonts to avoid Arial default)
    FONT_FALLBACKS = ['Montserrat', 'Roboto', 'Arial']
    
    # Font weight and style flags
    TITLE_BOLD = True
    SUBTITLE_ITALIC = False
    BODY_BOLD = False
    
    FONTS = FontConfig(
        primary=CASHMERE_FONT_FAMILY,
        fallback='Arial',      # Last resort fallback
        title=CASHMERE_FONT_FAMILY,
        body=CASHMERE_FONT_FAMILY,
        meta=CASHMERE_FONT_FAMILY,
        fallbacks=FONT_FALLBACKS
    )
    
    # Font sizes (in PT)
    FONT_SIZES = {
        'HERO_TITLE': 56,      # Slightly larger for cinematic look
        'HERO_SUBTITLE': 24,
        'CONTENT_TITLE': 36,
        'BODY': 18,
        'META': 14,
        'FOOTNOTE': 12,        # Sources, captions
    }
    
    # ============================================================================
    # Spacing & Line Height
    # ============================================================================
    
    SPACING = {
        'TITLE_TO_BODY': 16,   # Space after title (PT)
        'BULLET_ABOVE': 5,      # Space before bullet (PT) - reduced from 8
        'BULLET_BELOW': 5,      # Space after bullet (PT) - reduced from 8
        'BULLET_INDENT': 20,    # Bullet indentation (PT)
    }
    
    # Left accent rule (for bullet readability)
    LEFT_RULE_WIDTH = 3  # Width of accent rule in PT
    LEFT_RULE_GAP = 6  # Gap between rule and text box in PT
    
    # Bullet indentation levels
    BULLET_INDENT_PRIMARY = 20  # Primary bullet indent (PT)
    BULLET_INDENT_SECONDARY = 12  # Secondary bullet indent (PT)
    
    # Overflow policies
    MAX_BULLETS = 5  # Maximum bullets per slide
    MAX_BULLET_CHARS = 100  # Maximum characters per bullet
    
    # Line spacing (percentage for line height)
    LINE_SPACING = 115  # 115% line height for readability and elegance
    
    # Spacing mode for bullet lists
    SPACING_MODE = 'COLLAPSE_LISTS'  # Keep bullet lists tight, no extra spacing between items
    
    # Text alignment
    BODY_TEXT_ALIGNMENT = 'START'  # 'START' for left-align, 'JUSTIFIED' for clean edges
    
    # ============================================================================
    # Layout (in EMU - 1 cm = 360,000 EMU)
    # ============================================================================
    
    LAYOUT = {
        'MARGIN_LEFT_CONTENT': int(1.5 * 360000),   # 540,000 EMU = 1.5 cm
        'MARGIN_TOP_CONTENT': int(2.0 * 360000),    # 720,000 EMU = 2 cm
        'MAX_WIDTH_BODY': int(22.0 * 360000),       # 7,920,000 EMU = 22 cm
    }
    
    # Layout positioning (normalized coordinates: 0.0 to 1.0)
    TITLE_Y_POSITION = 0.10  # 10% from top for consistent title positioning
    BODY_MARGIN_LEFT = 0.06  # 6% margin from left edge (improved optical margin)
    BODY_MARGIN_RIGHT = 0.06  # 6% margin from right edge
    BODY_BOX_HEIGHT_RATIO = 0.70  # Body text box height as ratio of slide height
    
    # Two-column layout coordinates (normalized)
    TWO_COLUMN_LAYOUT = {
        'text_box': {'x': 0.05, 'y': 0.1, 'width': 0.55, 'height': 0.8},
        'image_box': {'x': 0.65, 'y': 0.15, 'width': 0.3, 'height': 0.7}
    }
    
    # ============================================================================
    # Layout Mappings
    # ============================================================================
    # Maps logical layout names to template layout IDs or predefined layouts
    # These are discovered from the template or use predefined layouts
    
    LAYOUT_MAPPINGS = LayoutMapping(
        title=None,           # Will be discovered from template or use 'TITLE'
        content=None,         # Will be discovered from template or use 'TITLE_AND_BODY'
        section=None,         # Will be discovered from template or use 'SECTION_HEADER'
        image_left=None,      # Will be discovered from template or use 'TITLE_AND_BODY'
        image_right=None,     # Will be discovered from template or use 'TITLE_AND_BODY'
        two_column=None,      # Will be discovered from template or use 'TITLE_AND_TWO_COLUMNS'
    )
    
    # Predefined layout fallbacks (Google Slides built-in layouts)
    PREDEFINED_LAYOUTS = {
        'TITLE': 'TITLE',
        'CONTENT': 'TITLE_AND_BODY',
        'SECTION': 'SECTION_HEADER',
        'TWO_COLUMN': 'TITLE_AND_TWO_COLUMNS',
        'BLANK': 'BLANK',
    }
    
    # ============================================================================
    # Section Slide Configuration
    # ============================================================================
    
    # Section slide background uses accent color
    SECTION_BG_COLOR = 'ACCENT'  # Reference to THEME_COLORS['ACCENT']
    
    # Section title casing
    SECTION_TITLE_CASE = 'TITLE'  # 'TITLE' or 'SENTENCE'
    
    # Configurable section labels (detected from report structure)
    SECTION_LABELS = [
        'Topline',
        'Market Analysis',
        'Technology Deep-Dive',
        'Competitive Landscape',
        'Operator Lens',
        'Investor Lens',
        'BD Lens',
    ]
    
    # ============================================================================
    # Hero Overlay Configuration (Luminance-Aware)
    # ============================================================================
    
    # Overlay opacity based on image luminance
    HERO_OVERLAY_OPACITY = {
        'dark': 0.25,   # Luminance < 0.45
        'mid': 0.30,    # Luminance 0.45-0.75
        'light': 0.45,  # Luminance > 0.75
    }
    
    # ============================================================================
    # Placeholder Token Registry
    # ============================================================================
    # All supported placeholder tokens and their descriptions
    
    PLACEHOLDERS = {
        # Hero Slide
        'TITLE': {
            'description': 'Main report title (large, prominent)',
            'slide_type': 'hero',
            'required': True,
            'element_type': 'text',
        },
        'SUBTITLE': {
            'description': 'Executive summary first sentence (medium)',
            'slide_type': 'hero',
            'required': True,
            'element_type': 'text',
        },
        'DATE': {
            'description': 'Report date (small, bottom corner)',
            'slide_type': 'hero',
            'required': True,
            'element_type': 'text',
        },
        'LOGO': {
            'description': 'Logo image (optional)',
            'slide_type': 'hero',
            'required': False,
            'element_type': 'image',
        },
        'HERO_OVERLAY': {
            'description': 'Dark overlay rectangle for text readability (alt text identifier)',
            'slide_type': 'hero',
            'required': False,
            'element_type': 'shape',
        },
        
        # Collage Slide
        'IMG_1': {
            'description': 'First section image',
            'slide_type': 'collage',
            'required': True,
            'element_type': 'image',
        },
        'IMG_2': {
            'description': 'Second section image',
            'slide_type': 'collage',
            'required': True,
            'element_type': 'image',
        },
        'IMG_3': {
            'description': 'Third section image',
            'slide_type': 'collage',
            'required': True,
            'element_type': 'image',
        },
        'IMG_4': {
            'description': 'Fourth section image',
            'slide_type': 'collage',
            'required': True,
            'element_type': 'image',
        },
        'IMG_5': {
            'description': 'Fifth section image (optional)',
            'slide_type': 'collage',
            'required': False,
            'element_type': 'image',
        },
        'IMG_6': {
            'description': 'Sixth section image (optional)',
            'slide_type': 'collage',
            'required': False,
            'element_type': 'image',
        },
        'IMG_7': {
            'description': 'Seventh section image (optional)',
            'slide_type': 'collage',
            'required': False,
            'element_type': 'image',
        },
        'IMG_8': {
            'description': 'Eighth section image (optional)',
            'slide_type': 'collage',
            'required': False,
            'element_type': 'image',
        },
        'BIGWORD': {
            'description': 'Large angled word/text',
            'slide_type': 'collage',
            'required': True,
            'element_type': 'text',
        },
        'STICKER': {
            'description': 'Sticker/badge image (optional)',
            'slide_type': 'collage',
            'required': False,
            'element_type': 'image',
        },
        
        # Content Slides
        'H1': {
            'description': 'Section heading (large, bold)',
            'slide_type': 'content',
            'required': True,
            'element_type': 'text',
        },
        'BULLETS': {
            'description': 'Bullet points (will be auto-formatted)',
            'slide_type': 'content',
            'required': True,
            'element_type': 'text',
        },
        'QUOTE': {
            'description': 'Highlighted quote (optional)',
            'slide_type': 'content',
            'required': False,
            'element_type': 'text',
        },
    }
    
    # ============================================================================
    # Alt Text Identifiers
    # ============================================================================
    # Special identifiers used in alt text (title/description) for element discovery
    
    ALT_TEXT_MAP = {
        'HERO_OVERLAY': 'HERO_OVERLAY',
        'BIGWORD': 'BIGWORD',
        'BULLETS': 'BULLETS',
        'H1': 'H1',
        'LOGO': 'LOGO',
    }
    
    # ============================================================================
    # Template Metadata
    # ============================================================================
    
    TEMPLATE_VERSION = "1.0.0"
    TEMPLATE_CHANGELOG = [
        "1.0.0 - Initial Cashmere-style template configuration"
    ]
    
    # ============================================================================
    # Helper Methods
    # ============================================================================
    
    @classmethod
    def get_placeholder_token(cls, name: str) -> str:
        """Get the placeholder token string for a given name"""
        return f"{{{{{name}}}}}"
    
    @classmethod
    def get_all_placeholders(cls) -> List[str]:
        """Get all placeholder token strings"""
        return [cls.get_placeholder_token(name) for name in cls.PLACEHOLDERS.keys()]
    
    @classmethod
    def get_placeholders_by_slide_type(cls, slide_type: str) -> List[str]:
        """Get placeholders for a specific slide type"""
        return [
            cls.get_placeholder_token(name)
            for name, config in cls.PLACEHOLDERS.items()
            if config['slide_type'] == slide_type
        ]
    
    @classmethod
    def get_required_placeholders(cls, slide_type: str) -> List[str]:
        """Get required placeholders for a specific slide type"""
        return [
            cls.get_placeholder_token(name)
            for name, config in cls.PLACEHOLDERS.items()
            if config['slide_type'] == slide_type and config['required']
        ]
    
    @classmethod
    def resolve_theme_color(cls, color_name: str, use_theme: bool = True) -> Dict[str, Any]:
        """
        Resolve theme color to API format.
        
        Args:
            color_name: Name from THEME_COLORS dict
            use_theme: If True, prefer theme color; if False, use RGB fallback
            
        Returns:
            Color dict in Google Slides API format
        """
        if color_name not in cls.THEME_COLORS:
            raise ValueError(f"Unknown color name: {color_name}")
        
        theme_color = cls.THEME_COLORS[color_name]
        
        # If theme name exists and we want to use it, return theme color
        if use_theme and theme_color.theme_name:
            return {
                "themeColor": theme_color.theme_name
            }
        
        # Otherwise, use RGB fallback
        if theme_color.rgb_fallback:
            return {
                "opaqueColor": {
                    "rgbColor": theme_color.rgb_fallback
                }
            }
        
        # Fallback to black if no RGB provided
        return {
            "opaqueColor": {
                "rgbColor": {"red": 0.0, "green": 0.0, "blue": 0.0}
            }
        }
    
    @classmethod
    def get_font_family(cls, font_type: str = 'primary') -> str:
        """Get font family for a given type"""
        if font_type == 'title':
            return cls.FONTS.title
        elif font_type == 'body':
            return cls.FONTS.body
        elif font_type == 'meta':
            return cls.FONTS.meta
        else:
            return cls.FONTS.primary
    
    @classmethod
    def get_font_size(cls, size_type: str) -> int:
        """Get font size for a given type"""
        return cls.FONT_SIZES.get(size_type, cls.FONT_SIZES['BODY'])
    
    @classmethod
    def get_spacing(cls, spacing_type: str) -> int:
        """Get spacing value for a given type"""
        return cls.SPACING.get(spacing_type, 0)
    
    @classmethod
    def get_layout_dimension(cls, dimension_type: str) -> int:
        """Get layout dimension for a given type (in EMU)"""
        return cls.LAYOUT.get(dimension_type, 0)

