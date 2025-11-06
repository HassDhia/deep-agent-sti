"""
Image Generator for STI Intelligence Reports

Generates images using OpenAI's gpt-image-1 API with intent-aware prompts
for thesis-path vs market-path reports.
"""

import os
import base64
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict
from openai import OpenAI
from config import STIConfig

# LangChain for tailored prompt generation
try:
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import PromptTemplate
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("⚠️ LangChain not available - will use hardcoded prompts")

# For URL fallback if DALL-E returns URLs instead of base64
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

logger = logging.getLogger(__name__)


class ImageGenerator:
    """Generate images using OpenAI gpt-image-1 API with intent-aware prompts"""
    
    # STI brand constants for prompt building
    STI_BRAND_BASE = (
        "clean editorial photography, soft daylight, cool slate/steel palette, "
        "no text or lettering, single subject, generous negative space, "
        "magazine cover aesthetic, depth-of-field, subtle contrast, "
        "not a poster, not a collage, not an infographic, no charts, no UI, no labels"
    )
    
    # LangChain prompt templates for tailored descriptions
    HERO_PROMPT_TEMPLATE = """You are creating an editorial image description for an intelligence report hero image.

Report Query: {query}
Report Intent: {intent}
Executive Summary (context): {exec_summary}

STI Brand Requirements (MUST FOLLOW):
- Clean editorial photography style
- Soft daylight, cool slate/steel palette
- Single subject, generous negative space
- Magazine cover aesthetic, shallow depth-of-field
- 20-30% empty space at top for header
- NOT a poster, NOT a collage, NOT an infographic
- NO text, NO labels, NO charts, NO UI elements

VARIETY REQUIREMENTS (create unique compositions per report):
- Vary camera perspective: alternate between eye-level, slight low-angle, overhead, or three-quarter views
- Vary composition: center-framed, rule-of-thirds, asymmetric balance
- Vary setting context: different corporate spaces (atrium, lab, office, data center, manufacturing floor, cleanroom)
- Vary subject positioning: left of frame, right of frame, center, diagonal placement
- Vary lighting direction: side-lit, back-lit, front-lit, or directional window light
- Extract 2-3 unique keywords from the executive summary and emphasize different visual interpretations
- Choose a unique combination of the above elements that differs from typical corporate photography

Task: Generate a concise, tailored image description (2-3 sentences) that:
1. Reflects the specific topic/content from the executive summary
2. Suggests a single, elegant subject relevant to the report
3. Maintains minimal, editorial, Bloomberg/FT aesthetic
4. Uses specific details from the executive summary (companies, technologies, concepts mentioned)
5. Creates a visually distinct composition by choosing a unique combination of perspective, setting, and lighting

For market reports: Think corporate editorial photography - single object in spacious corporate setting, but vary the specific environment, angle, and lighting.
For thesis reports: Think abstract conceptual illustration - minimal geometric patterns suggesting theoretical frameworks, but vary the geometric abstraction style and composition.

Output ONLY the image description (no explanations, no markdown). Keep it under 100 words."""

    SECTION_PROMPT_TEMPLATE = """You are creating an editorial image description for a report section image.

Section Name: {section_name}
Section Content (first 1500 words): {section_content}
Report Query: {query}
Report Intent: {intent}

STI Brand Requirements (MUST FOLLOW):
- Clean editorial style, minimal composition
- Soft daylight, cool slate/steel palette
- Generous negative space, quiet editorial illustration
- NOT a dashboard, NOT an infographic
- NO text, NO labels, NO charts, NO widgets, NO icons

Section-Specific Style Guidelines:
- Market Analysis: Abstract systems motif - minimal network of arcs/nodes, soft gradients
- Technology Deep-Dive: Isometric technical line-drawing - thin ink lines, minimalist blueprint
- Competitive Landscape: Balanced radial diagram - neutral nodes, plain geometric shapes
- Thesis sections: Abstract conceptual motifs - minimal geometric patterns, restrained geometry

VARIETY REQUIREMENTS (create unique abstract interpretations per section):
- For Market Analysis: Vary network topology (star, mesh, hub-and-spoke, hierarchical, organic clusters)
- For Technology Deep-Dive: Vary technical drawing style (isometric, exploded view, cutaway, schematic, orthographic)
- For Competitive Landscape: Vary diagram structure (radial, matrix, concentric circles, cluster, grid)
- Extract unique technical terms or company names from section content and emphasize them visually in the abstraction
- Vary the geometric abstraction: sometimes more organic curves, sometimes more rigid geometry, sometimes flowing lines
- Choose a unique combination of topology/structure and abstraction style that differs from typical diagrams

Task: Generate a concise, tailored image description (2-3 sentences) that:
1. Reflects specific concepts, technologies, or themes from the section content
2. Uses abstract/minimal visual language (not literal representations)
3. Matches the section-specific style guideline above
4. Maintains editorial restraint and negative space emphasis
5. Creates a visually distinct interpretation by choosing a unique topology/abstraction combination

Output ONLY the image description (no explanations, no markdown). Keep it under 80 words."""
    
    def __init__(self, openai_api_key: str = None):
        logger.debug(f"🔧 ImageGenerator.__init__ called with api_key={'present' if openai_api_key else 'None'}")
        self.api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.warning("⚠️ OPENAI_API_KEY not found - image generation disabled")
            self.client = None
        else:
            logger.debug(f"✅ API key found (length: {len(self.api_key)}, starts with: {self.api_key[:7]}...)")
            try:
                # Configure timeout for image generation (longer than usual due to generation time)
                timeout = getattr(STIConfig, 'IMAGE_GENERATION_TIMEOUT', 120.0)  # 2 minutes default
                
                # Get organization ID from environment or config (for verified org)
                organization = os.getenv("OPENAI_ORGANIZATION") or getattr(STIConfig, 'OPENAI_ORGANIZATION', None)
                
                client_params = {
                    "api_key": self.api_key,
                    "timeout": timeout
                }
                
                # Add organization if specified (binds requests to verified org)
                if organization:
                    client_params["organization"] = organization
                    logger.debug(f"🔗 Using organization: {organization}")
                
                self.client = OpenAI(**client_params)
                logger.debug(f"✅ OpenAI client initialized successfully (timeout: {timeout}s)")
            except Exception as e:
                logger.error(f"❌ Failed to initialize OpenAI client: {e}")
                self.client = None
            
            # Initialize LangChain LLM for tailored prompt generation
            if LANGCHAIN_AVAILABLE and self.api_key:
                try:
                    llm_params = {
                        "api_key": self.api_key,
                        "model": getattr(STIConfig, 'DEFAULT_MODEL', 'gpt-4-turbo-preview'),
                        "temperature": 0.3  # Slightly higher temperature for creative variation while maintaining brand consistency
                    }
                    if organization:
                        llm_params["openai_organization"] = organization
                    self.llm = ChatOpenAI(**llm_params)
                    logger.debug("✅ LangChain LLM initialized for tailored prompt generation")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to initialize LangChain LLM: {e}")
                    logger.warning("   Will fallback to hardcoded prompts")
                    self.llm = None
            else:
                self.llm = None
                if not LANGCHAIN_AVAILABLE:
                    logger.debug("ℹ️ LangChain not available - using hardcoded prompts")
    
    def generate_hero_image(self, query: str, report_dir: str, intent: str = "market", 
                           exec_summary: str = None) -> Optional[Tuple[str, str]]:
        """
        Generate hero image for report.
        
        Args:
            query: Report query/title
            report_dir: Directory to save image
            intent: "market" or "theory"
            exec_summary: Executive summary text for tailored prompt generation (optional)
            
        Returns:
            Tuple of (relative_image_path, attribution_text) or None if failed
        """
        logger.info(f"🎨 generate_hero_image called: query='{query}', report_dir='{report_dir}', intent='{intent}'")
        
        # Check configuration
        logger.debug(f"🔍 Configuration check:")
        logger.debug(f"   - ENABLE_IMAGE_GENERATION: {STIConfig.ENABLE_IMAGE_GENERATION}")
        logger.debug(f"   - DALL_E_MODEL: {STIConfig.DALL_E_MODEL}")
        logger.debug(f"   - DALL_E_IMAGE_SIZE: {STIConfig.DALL_E_IMAGE_SIZE}")
        logger.debug(f"   - Client initialized: {self.client is not None}")
        
        if not STIConfig.ENABLE_IMAGE_GENERATION:
            logger.warning("⚠️ Image generation disabled in config (ENABLE_IMAGE_GENERATION=False)")
            return None
        
        if not self.client:
            logger.warning("⚠️ OpenAI client not initialized - cannot generate images")
            return None
        
        # Validate report_dir
        report_path = Path(report_dir)
        if not report_path.exists():
            logger.error(f"❌ Report directory does not exist: {report_dir}")
            return None
        logger.debug(f"✅ Report directory exists: {report_dir}")
        
        try:
            # Generate intent-aware prompt (use LLM if exec_summary provided, else fallback)
            if exec_summary and self.llm and LANGCHAIN_AVAILABLE:
                logger.info("🤖 Using LLM to generate tailored hero prompt from executive summary")
                prompt = self._generate_hero_prompt_llm(query, intent, exec_summary)
            else:
                if exec_summary and not self.llm:
                    logger.debug("ℹ️ Exec summary provided but LLM not available - using hardcoded prompt")
                prompt = self._build_hero_prompt(query, intent)
            logger.info(f"📝 Generated prompt (length: {len(prompt)}): {prompt[:100]}...")
            logger.debug(f"📝 Full prompt: {prompt}")
            
            # Get model and size, validate based on model
            model = STIConfig.DALL_E_MODEL
            size = STIConfig.DALL_E_IMAGE_SIZE
            
            # Valid sizes per model
            ALLOWED_GPT_IMAGE1_SIZES = {"1024x1024", "1536x1024", "1024x1536"}
            ALLOWED_DALLE3_SIZES = {"1024x1024", "1792x1024", "1024x1792"}
            
            # Normalize invalid size based on model
            if model == "gpt-image-1" and size not in ALLOWED_GPT_IMAGE1_SIZES:
                logger.warning(f"⚠️ Size '{size}' not valid for gpt-image-1. Falling back to 1536x1024.")
                size = "1536x1024"  # landscape hero
            elif model.startswith("dall-e") and size not in ALLOWED_DALLE3_SIZES:
                logger.warning(f"⚠️ Size '{size}' not valid for {model}. Falling back to 1792x1024.")
                size = "1792x1024"  # landscape hero for DALL-E 3
            
            # Prepare API parameters
            api_params = {
                "model": model,
                "prompt": prompt,
                "size": size,
                "n": 1
            }
            
            # Add style="natural" for DALL-E 3 to reduce over-dramatic/cluttered outputs
            if model.startswith("dall-e"):
                api_params["style"] = "natural"
                api_params["quality"] = "standard"  # Avoid hyper-detail, keep quality standard
                logger.debug(f"📤 Added style='natural' and quality='standard' for DALL-E model")
            
            # Only add response_format for DALL-E models if we want base64 (optional)
            # DALL-E 3 returns URLs by default, which our URL fallback handles
            # Uncomment below if you prefer base64 over URL downloads for DALL-E 3
            # if model.lower().startswith("dall-e"):
            #     api_params["response_format"] = "b64_json"
            #     logger.debug(f"📤 Added response_format for DALL-E model")
            
            logger.debug(f"📤 API call parameters: model={api_params['model']}, size={api_params['size']}")
            if "style" in api_params:
                logger.debug(f"   style={api_params['style']}, quality={api_params.get('quality', 'default')}")
            if "response_format" in api_params:
                logger.debug(f"   response_format={api_params['response_format']} (DALL-E only)")
            logger.info(f"🚀 Calling OpenAI API: model='{model}', size='{size}'")
            
            # Call OpenAI API with explicit timeout handling
            logger.info("⏳ Waiting for image generation (this may take 30-60 seconds)...")
            try:
                response = self.client.images.generate(**api_params)
                logger.info("✅ OpenAI API call successful")
            except Exception as api_error:
                error_str = str(api_error)
                if "timeout" in error_str.lower():
                    logger.error(f"❌ Image generation timed out - API call took too long")
                    logger.error(f"   Consider increasing IMAGE_GENERATION_TIMEOUT in config")
                raise
            
            if not hasattr(response, 'data') or not response.data:
                logger.error(f"❌ Response missing 'data' attribute or empty: {response}")
                return None
            
            first_item = response.data[0]
            
            # Prefer base64 if present (gpt-image-1 always returns base64 by default)
            image_bytes = None
            if hasattr(first_item, 'b64_json') and first_item.b64_json:
                logger.info("🔓 Decoding base64 image from response...")
                image_b64 = first_item.b64_json
                logger.debug(f"🔍 Base64 string length: {len(image_b64)}")
                image_bytes = base64.b64decode(image_b64)
                logger.info(f"✅ Decoded {len(image_bytes)} bytes from base64")
            elif hasattr(first_item, 'url') and first_item.url:
                # Fallback for DALL-E URL responses
                if not HTTPX_AVAILABLE:
                    logger.error("❌ httpx not available - cannot download image from URL")
                    return None
                logger.info(f"📥 Downloading image from URL: {first_item.url[:50]}...")
                try:
                    img_response = httpx.get(first_item.url, timeout=30.0)
                    img_response.raise_for_status()
                    image_bytes = img_response.content
                    logger.info(f"✅ Downloaded {len(image_bytes)} bytes from URL")
                except Exception as e:
                    logger.error(f"❌ Failed to download image from URL: {e}")
                    return None
            else:
                logger.error(f"❌ Response missing both 'b64_json' and 'url' attributes")
                logger.error(f"   Available attributes: {[attr for attr in dir(first_item) if not attr.startswith('_')]}")
                return None
            
            # Prepare save path
            images_dir = report_path / "images"
            logger.debug(f"📁 Target images directory: {images_dir}")
            
            try:
                images_dir.mkdir(exist_ok=True, parents=True)
                logger.info(f"✅ Created/verified images directory: {images_dir}")
            except Exception as e:
                logger.error(f"❌ Failed to create images directory: {e}")
                import traceback
                logger.debug(f"Traceback:\n{traceback.format_exc()}")
                return None
            
            query_slug = self._slugify_query(query)
            filename = f"hero_{query_slug}.png"
            filepath = images_dir / filename
            logger.debug(f"📝 Target filepath: {filepath}")
            
            # Save file
            try:
                logger.info(f"💾 Writing image file: {filepath}")
                filepath.write_bytes(image_bytes)
                file_size = filepath.stat().st_size
                logger.info(f"✅ Successfully wrote {file_size} bytes to {filepath}")
                
                # Verify file exists
                if not filepath.exists():
                    logger.error(f"❌ File was written but does not exist: {filepath}")
                    return None
                    
            except Exception as e:
                logger.error(f"❌ Failed to write image file: {e}")
                import traceback
                logger.debug(f"Traceback:\n{traceback.format_exc()}")
                return None
            
            relative_path = f"images/{filename}"
            attribution = f"Image generated with OpenAI {model}"
            
            logger.info(f"🎉 Generated hero image successfully: {relative_path}")
            return relative_path, attribution
            
        except Exception as e:
            # Enhanced error logging
            import traceback
            error_type = type(e).__name__
            error_msg = str(e)
            logger.error(f"❌ Image generation failed: {error_type}: {error_msg}")
            logger.error(f"❌ Full traceback:\n{traceback.format_exc()}")
            
            # Check for specific API error types
            if hasattr(e, 'status_code'):
                logger.error(f"❌ HTTP Status Code: {e.status_code}")
                if e.status_code == 400:
                    logger.error(f"❌ 400 Bad Request - Invalid API parameters:")
                    logger.error(f"   Error message: {error_msg}")
                    if "size" in error_msg.lower() or "dimension" in error_msg.lower():
                        logger.error(f"   → Invalid image size")
                        logger.error(f"   → Valid sizes for gpt-image-1: 1024x1024, 1536x1024, 1024x1536")
                    if "quality" in error_msg.lower():
                        logger.error(f"   → Quality parameter issue (gpt-image-1 doesn't support quality)")
                    if "response_format" in error_msg.lower():
                        logger.error(f"   → response_format not supported by gpt-image-1")
                elif e.status_code == 429:
                    logger.warning("⚠️ Rate limit hit for image generation")
                elif e.status_code == 401:
                    logger.error("❌ Invalid API key for image generation")
                else:
                    logger.error(f"❌ API error {e.status_code}: {error_msg}")
            
            # Check error message content
            error_lower = error_msg.lower()
            if "rate_limit" in error_lower or "429" in error_lower:
                logger.warning(f"⚠️ Rate limit: {error_msg}")
            elif "content_policy" in error_lower or "moderation" in error_lower:
                logger.warning(f"⚠️ Content moderation: {error_msg}")
            elif "model" in error_lower:
                logger.error(f"❌ Model error: {error_msg}")
            elif "size" in error_lower or "dimension" in error_lower:
                logger.error(f"❌ Size error: {error_msg}")
            elif "quality" in error_lower:
                logger.error(f"❌ Quality parameter error (not supported by gpt-image-1)")
            elif "b64_json" in error_lower or "response_format" in error_lower:
                logger.error(f"❌ Response format error: {error_msg}")
            
            return None
    
    def _sti_prompt(self, core: str) -> str:
        """STI brand prompt builder - injects brand constants and anti-pattern guards"""
        return f"{core}. {self.STI_BRAND_BASE}"
    
    def _extract_diversity_keywords(self, text: str, query: str) -> str:
        """Extract unique keywords from text to seed visual diversity"""
        if not text:
            return ""
        
        combined_text = (text + ' ' + query).lower()
        
        # Technology/domain keywords that suggest visual interpretations
        tech_keywords = [
            'drone', 'swarm', 'autonomous', 'ai', 'machine learning', 'quantum', 
            'blockchain', 'crypto', 'neural', 'robotic', 'sensor', 'satellite',
            'semiconductor', 'chip', 'processor', 'cloud', 'edge', '5g', 'iot'
        ]
        
        # Extract matching keywords
        found_keywords = []
        for keyword in tech_keywords:
            if keyword.lower() in combined_text:
                found_keywords.append(keyword)
        
        # Return up to 3 unique keywords for visual emphasis
        if found_keywords:
            unique_keywords = list(dict.fromkeys(found_keywords))[:3]  # Preserve order, remove dupes
            return f"Emphasize visual interpretation of: {', '.join(unique_keywords)}"
        
        return ""
    
    def _get_variation_seed(self, query: str) -> Dict[str, str]:
        """Generate deterministic variation based on query hash for consistent but varied styles"""
        import hashlib
        
        query_hash = int(hashlib.md5(query.encode()).hexdigest(), 16)
        
        perspectives = ['eye-level', 'slight low-angle', 'overhead', 'three-quarter view']
        compositions = ['center-framed', 'rule-of-thirds left', 'rule-of-thirds right', 'asymmetric']
        settings = ['corporate atrium', 'modern lab space', 'data center corridor', 'office with view', 'cleanroom', 'manufacturing floor']
        lighting = ['side-lit from left', 'back-lit silhouette', 'front-lit soft', 'directional window light']
        
        return {
            'perspective': perspectives[query_hash % len(perspectives)],
            'composition': compositions[(query_hash // 10) % len(compositions)],
            'setting': settings[(query_hash // 100) % len(settings)],
            'lighting': lighting[(query_hash // 1000) % len(lighting)]
        }
    
    def _generate_hero_prompt_llm(self, query: str, intent: str, exec_summary: str) -> str:
        """Generate tailored hero prompt using LLM based on executive summary"""
        if not LANGCHAIN_AVAILABLE or not self.llm:
            logger.warning("⚠️ LangChain not available - falling back to hardcoded prompt")
            return self._build_hero_prompt(query, intent)
        
        try:
            from langchain_core.prompts import PromptTemplate
            
            template = PromptTemplate(
                input_variables=["query", "intent", "exec_summary"],
                template=self.HERO_PROMPT_TEMPLATE
            )
            
            # Truncate exec_summary if too long (keep first 800 chars for context)
            exec_summary_truncated = exec_summary[:800] if exec_summary else ""
            
            # Add diversity seed based on query for consistent but varied styles
            variation_seed = self._get_variation_seed(query)
            diversity_keywords = self._extract_diversity_keywords(exec_summary_truncated, query)
            
            # Enhance exec_summary with diversity cues
            enhanced_summary = exec_summary_truncated
            if diversity_keywords:
                enhanced_summary = f"{exec_summary_truncated}\n\nVisual emphasis: {diversity_keywords}"
            if variation_seed:
                enhanced_summary += f"\n\nSuggested variation: {variation_seed['perspective']} view, {variation_seed['composition']}, {variation_seed['setting']}, {variation_seed['lighting']}"
            
            prompt = template.format(
                query=query,
                intent="thesis" if intent == "thesis" else "market",
                exec_summary=enhanced_summary
            )
            
            logger.debug(f"🤖 Invoking LLM for hero prompt generation...")
            response = self.llm.invoke(prompt)
            llm_description = response.content.strip()
            
            # Clean up any markdown formatting or extra text
            llm_description = llm_description.replace("**", "").replace("*", "").strip()
            
            # Apply STI brand constants to ensure consistency
            final_prompt = f"{llm_description}. {self.STI_BRAND_BASE}"
            
            logger.debug(f"✅ LLM generated hero prompt (length: {len(final_prompt)})")
            return final_prompt
            
        except Exception as e:
            logger.warning(f"⚠️ LLM prompt generation failed: {e}")
            logger.warning("   Falling back to hardcoded prompt")
            return self._build_hero_prompt(query, intent)
    
    def _build_hero_prompt(self, query: str, intent: str) -> str:
        """Build intent-aware prompt for hero image - minimal editorial style"""
        logger.debug(f"🎨 Building hero prompt: query='{query}', intent='{intent}'")
        
        if intent == "thesis":
            # Thesis hero: abstract conceptual, minimal
            core = (
                f"Editorial hero image for '{query}'. "
                f"Abstract conceptual motif suggesting theoretical frameworks, "
                f"minimal composition, soft geometric shapes, scholarly aesthetic, "
                f"20-30% empty space at top for header, shallow depth-of-field"
            )
        else:
            # Market hero: single subject, corporate editorial
            core = (
                f"Editorial hero image for '{query}'. "
                f"Single drone in a spacious, glass corporate atrium, mid-frame, "
                f"20-30% empty space above for header, soft daylight, "
                f"cool slate/steel palette with a discreet blue accent, "
                f"shallow depth-of-field"
            )
        
        prompt = self._sti_prompt(core)
        logger.debug(f"✅ Built hero prompt: {prompt[:100]}...")
        return prompt
    
    def generate_section_image(self, section_name: str, section_content: str, query: str, 
                               intent: str, report_dir: str) -> Optional[Tuple[str, str]]:
        """
        Generate section-specific image for report section.
        
        Args:
            section_name: Name of the section (e.g., "Market Analysis", "Technology Deep-Dive")
            section_content: Content summary or excerpt from the section (first 500 chars)
            query: Report query/title
            intent: "market" or "theory"
            report_dir: Directory to save image
            
        Returns:
            Tuple of (relative_image_path, attribution_text) or None if failed
        """
        logger.info(f"🎨 generate_section_image called: section='{section_name}', query='{query}', intent='{intent}'")
        
        # Check configuration
        if not STIConfig.ENABLE_IMAGE_GENERATION:
            logger.warning("⚠️ Image generation disabled in config")
            return None
        
        if not getattr(STIConfig, 'ENABLE_SECTION_IMAGES', True):
            logger.debug("ℹ️ Section images disabled in config")
            return None
        
        if not self.client:
            logger.warning("⚠️ OpenAI client not initialized - cannot generate images")
            return None
        
        # Validate report_dir
        report_path = Path(report_dir)
        if not report_path.exists():
            logger.error(f"❌ Report directory does not exist: {report_dir}")
            return None
        
        try:
            # Generate section-specific prompt (use LLM if content provided, else fallback)
            if section_content and self.llm and LANGCHAIN_AVAILABLE:
                logger.info("🤖 Using LLM to generate tailored section prompt from content")
                prompt = self._generate_section_prompt_llm(section_name, section_content, query, intent)
            else:
                if section_content and not self.llm:
                    logger.debug("ℹ️ Section content provided but LLM not available - using hardcoded prompt")
                prompt = self._build_section_prompt(section_name, section_content or "", query, intent)
            logger.info(f"📝 Generated section prompt (length: {len(prompt)}): {prompt[:100]}...")
            logger.debug(f"📝 Full prompt: {prompt}")
            
            # Get model and size, validate based on model
            model = STIConfig.DALL_E_MODEL
            size = STIConfig.DALL_E_IMAGE_SIZE
            
            # Valid sizes per model
            ALLOWED_GPT_IMAGE1_SIZES = {"1024x1024", "1536x1024", "1024x1536"}
            ALLOWED_DALLE3_SIZES = {"1024x1024", "1792x1024", "1024x1792"}
            
            # Normalize invalid size based on model
            if model == "gpt-image-1" and size not in ALLOWED_GPT_IMAGE1_SIZES:
                logger.warning(f"⚠️ Size '{size}' not valid for gpt-image-1. Falling back to 1536x1024.")
                size = "1536x1024"
            elif model.startswith("dall-e") and size not in ALLOWED_DALLE3_SIZES:
                logger.warning(f"⚠️ Size '{size}' not valid for {model}. Falling back to 1792x1024.")
                size = "1792x1024"
            
            # Prepare API parameters
            api_params = {
                "model": model,
                "prompt": prompt,
                "size": size,
                "n": 1
            }
            
            # Add style="natural" for DALL-E 3 to reduce over-dramatic/cluttered outputs
            if model.startswith("dall-e"):
                api_params["style"] = "natural"
                api_params["quality"] = "standard"  # Avoid hyper-detail, keep quality standard
                logger.debug(f"📤 Added style='natural' and quality='standard' for DALL-E model")
            
            logger.debug(f"📤 API call parameters: model={api_params['model']}, size={api_params['size']}")
            if "style" in api_params:
                logger.debug(f"   style={api_params['style']}, quality={api_params.get('quality', 'default')}")
            logger.info(f"🚀 Calling OpenAI API for section image: model='{model}', size='{size}'")
            
            # Call OpenAI API
            logger.info("⏳ Waiting for section image generation (this may take 30-60 seconds)...")
            try:
                response = self.client.images.generate(**api_params)
                logger.info("✅ OpenAI API call successful")
            except Exception as api_error:
                error_str = str(api_error)
                if "timeout" in error_str.lower():
                    logger.error(f"❌ Section image generation timed out")
                    logger.error(f"   Consider increasing IMAGE_GENERATION_TIMEOUT in config")
                raise
            
            if not hasattr(response, 'data') or not response.data:
                logger.error(f"❌ Response missing 'data' attribute or empty: {response}")
                return None
            
            first_item = response.data[0]
            
            # Extract image bytes (same logic as hero image)
            image_bytes = None
            if hasattr(first_item, 'b64_json') and first_item.b64_json:
                logger.info("🔓 Decoding base64 image from response...")
                image_b64 = first_item.b64_json
                image_bytes = base64.b64decode(image_b64)
                logger.info(f"✅ Decoded {len(image_bytes)} bytes from base64")
            elif hasattr(first_item, 'url') and first_item.url:
                if not HTTPX_AVAILABLE:
                    logger.error("❌ httpx not available - cannot download image from URL")
                    return None
                logger.info(f"📥 Downloading image from URL: {first_item.url[:50]}...")
                try:
                    img_response = httpx.get(first_item.url, timeout=30.0)
                    img_response.raise_for_status()
                    image_bytes = img_response.content
                    logger.info(f"✅ Downloaded {len(image_bytes)} bytes from URL")
                except Exception as e:
                    logger.error(f"❌ Failed to download image from URL: {e}")
                    return None
            else:
                logger.error(f"❌ Response missing both 'b64_json' and 'url' attributes")
                return None
            
            # Prepare save path
            images_dir = report_path / "images"
            try:
                images_dir.mkdir(exist_ok=True, parents=True)
                logger.info(f"✅ Created/verified images directory: {images_dir}")
            except Exception as e:
                logger.error(f"❌ Failed to create images directory: {e}")
                return None
            
            # Generate filename
            section_slug = self._slugify_query(section_name)
            query_slug = self._slugify_query(query)
            filename = f"section_{section_slug}_{query_slug}.png"
            filepath = images_dir / filename
            
            # Save file
            try:
                logger.info(f"💾 Writing section image file: {filepath}")
                filepath.write_bytes(image_bytes)
                file_size = filepath.stat().st_size
                logger.info(f"✅ Successfully wrote {file_size} bytes to {filepath}")
                
                if not filepath.exists():
                    logger.error(f"❌ File was written but does not exist: {filepath}")
                    return None
                    
            except Exception as e:
                logger.error(f"❌ Failed to write section image file: {e}")
                return None
            
            relative_path = f"images/{filename}"
            attribution = f"Image generated with OpenAI {model}"
            
            logger.info(f"🎉 Generated section image successfully: {relative_path}")
            return relative_path, attribution
            
        except Exception as e:
            import traceback
            error_type = type(e).__name__
            error_msg = str(e)
            logger.error(f"❌ Section image generation failed: {error_type}: {error_msg}")
            logger.debug(f"❌ Full traceback:\n{traceback.format_exc()}")
            return None
    
    def _generate_section_prompt_llm(self, section_name: str, section_content: str, query: str, intent: str) -> str:
        """Generate tailored section prompt using LLM based on section content"""
        if not LANGCHAIN_AVAILABLE or not self.llm:
            logger.warning("⚠️ LangChain not available - falling back to hardcoded prompt")
            return self._build_section_prompt(section_name, section_content, query, intent)
        
        try:
            from langchain_core.prompts import PromptTemplate
            
            template = PromptTemplate(
                input_variables=["section_name", "section_content", "query", "intent"],
                template=self.SECTION_PROMPT_TEMPLATE
            )
            
            # Truncate section_content if too long (keep first 1500 chars for context)
            section_content_truncated = section_content[:1500] if section_content else ""
            
            # Add diversity keywords for section-specific variation
            diversity_keywords = self._extract_diversity_keywords(section_content_truncated, query)
            
            # Enhance section content with diversity cues
            enhanced_content = section_content_truncated
            if diversity_keywords:
                enhanced_content = f"{section_content_truncated}\n\nVisual emphasis: {diversity_keywords}"
            
            prompt = template.format(
                section_name=section_name,
                section_content=enhanced_content,
                query=query,
                intent="thesis" if intent == "thesis" else "market"
            )
            
            logger.debug(f"🤖 Invoking LLM for section prompt generation...")
            response = self.llm.invoke(prompt)
            llm_description = response.content.strip()
            
            # Clean up any markdown formatting or extra text
            llm_description = llm_description.replace("**", "").replace("*", "").strip()
            
            # Apply STI brand constants with additional anti-pattern guards
            final_prompt = f"{llm_description}. {self.STI_BRAND_BASE}, not a dashboard, not an infographic, no widgets, no icons"
            
            logger.debug(f"✅ LLM generated section prompt (length: {len(final_prompt)})")
            return final_prompt
            
        except Exception as e:
            logger.warning(f"⚠️ LLM section prompt generation failed: {e}")
            logger.warning("   Falling back to hardcoded prompt")
            return self._build_section_prompt(section_name, section_content, query, intent)
    
    def _build_section_prompt(self, section_name: str, section_content: str, query: str, intent: str) -> str:
        """Build section-specific prompt - minimal, abstract, editorial style (not infographics)"""
        logger.debug(f"🎨 Building section prompt: section='{section_name}', intent='{intent}'")
        
        # Normalize section name for matching
        section_lower = section_name.lower()
        
        if intent == "theory" or intent == "thesis":
            # Thesis-path section prompts: abstract, minimal
            if "foundational" in section_lower or "foundation" in section_lower:
                core = (
                    f"Abstract systems motif suggesting theoretical frameworks for '{query}': "
                    f"minimal geometric patterns, soft gradients, restrained geometry, "
                    f"quiet editorial illustration, negative space emphasized"
                )
            elif "mechanism" in section_lower or "formalization" in section_lower:
                core = (
                    f"Minimal process visualization for '{query}': "
                    f"simple flow lines and nodes, muted tones, "
                    f"quiet editorial illustration, ample whitespace"
                )
            elif "application" in section_lower or "synthesis" in section_lower:
                core = (
                    f"Abstract motif suggesting practical implementation for '{query}': "
                    f"minimal composition, soft gradients, restrained geometry, "
                    f"editorial illustration style, negative space emphasized"
                )
            else:
                # Generic thesis section
                core = (
                    f"Abstract conceptual motif for '{query}' in context of {section_name}: "
                    f"minimal composition, soft tones, quiet editorial illustration, "
                    f"generous negative space"
                )
        else:
            # Market-path section prompts: abstract, not dashboards/infographics
            if "market analysis" in section_lower or "market" in section_lower:
                core = (
                    f"Abstract systems motif suggesting airspace coordination for '{query}': "
                    f"minimal network of a few arcs and nodes on a light background, "
                    f"soft gradients, restrained geometry, "
                    f"quiet editorial illustration, negative space emphasized"
                )
            elif "technology" in section_lower or "deep" in section_lower or "tech" in section_lower:
                core = (
                    f"Isometric technical line-drawing of a modern quadcopter assembly "
                    f"on a clean light backdrop for '{query}': "
                    f"thin ink lines, a few shaded surfaces, muted slate/ink tones, "
                    f"minimalist blueprint aesthetic"
                )
            elif "competitive" in section_lower or "landscape" in section_lower:
                core = (
                    f"Balanced radial diagram with 6 neutral nodes connected to a central hub "
                    f"for '{query}': plain geometric shapes only, soft shadows, "
                    f"ample whitespace, corporate editorial graphic"
                )
            elif "operator" in section_lower:
                core = (
                    f"Abstract operational motif for '{query}': "
                    f"minimal workflow lines, restrained geometry, soft tones, "
                    f"quiet editorial illustration, negative space"
                )
            elif "investor" in section_lower:
                core = (
                    f"Abstract investment flow motif for '{query}': "
                    f"minimal directional lines, simple nodes, soft gradients, "
                    f"quiet editorial illustration, negative space emphasized"
                )
            elif "bd" in section_lower or "business development" in section_lower:
                core = (
                    f"Abstract partnership network motif for '{query}': "
                    f"minimal connected nodes, restrained geometry, soft tones, "
                    f"quiet editorial illustration, ample whitespace"
                )
            else:
                # Generic market section
                core = (
                    f"Abstract editorial motif for '{query}' in context of {section_name}: "
                    f"minimal composition, soft tones, quiet illustration, "
                    f"generous negative space"
                )
        
        # Apply STI brand constants with additional anti-pattern guards
        prompt = f"{core}. {self.STI_BRAND_BASE}, not a dashboard, not an infographic, no widgets, no icons"
        logger.debug(f"✅ Built section prompt: {prompt[:100]}...")
        return prompt
    
    def _slugify_query(self, query: str) -> str:
        """Convert query to filesystem-safe slug"""
        import re
        slug = re.sub(r'[^a-z0-9]+', '_', query.lower())
        result = slug[:30]
        logger.debug(f"🔤 Slugified '{query}' → '{result}'")
        return result

