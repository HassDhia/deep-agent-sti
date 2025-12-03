"""
Image Generator for STI Intelligence Reports

Generates images using OpenAI's gpt-image-1 API with intent-aware prompts
for thesis-path vs market-path reports.
"""

import os
import json
import base64
import logging
import random
import re
import secrets
import hashlib
from pathlib import Path
from typing import Optional, Tuple, Dict, List, Any
from openai import OpenAI
from config import STIConfig
from metrics import friendly_metric_name

# For URL fallback if DALL-E returns URLs instead of base64
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

logger = logging.getLogger(__name__)

TEMPLATE_VERSION = "2025-11-29.1"


class ImageGenerator:
    def _record_image_manifest(self, report_path: Path, entry: Dict[str, str]) -> None:
        manifest_dir = report_path / "images"
        manifest_dir.mkdir(exist_ok=True, parents=True)
        manifest_path = manifest_dir / "manifest.json"
        try:
            if manifest_path.exists():
                with open(manifest_path, 'r', encoding='utf-8') as handle:
                    existing = json.load(handle)
            else:
                existing = []
        except Exception:
            existing = []
        existing.append(entry)
        try:
            with open(manifest_path, 'w', encoding='utf-8') as handle:
                json.dump(existing, handle, indent=2, ensure_ascii=False)
        except Exception as exc:
            logger.debug(f"Could not write image manifest: {exc}")
    """Generate images using OpenAI gpt-image-1 API with intent-aware prompts"""
    
    # STI brand constants for prompt building
    STI_IMAGE_STYLE = (
        "polished editorial photography, cinematic but minimal, deep contrast, subtle cool-tone grading, "
        "generous negative space, modern materials, natural poses, realistic lighting, no text, no logos, "
        "no UI, no charts, no infographics, no collage, no poster layout, single clear focal area"
    )

    STYLE_VARIANTS = {
        "hero": {
            "framing": [
                "three-quarter view from eye level",
                "slightly elevated angle looking down",
                "tight medium shot on the collaboration moment",
                "grounded eye-level framing focused on the active bay",
            ],
            "lighting": [
                "polished editorial lighting with soft shadows",
                "warm directional light with gentle falloff",
                "cool high-contrast lighting with crisp edges",
                "diffused skylight with controlled highlights",
            ],
            "palette": [
                "dark neutrals with electric blue accents",
                "graphite and steel with restrained teal",
                "ivory and charcoal with cyan pins",
                "slate base with subtle brass highlights",
            ],
            "geometry": [
                "layered geometric planes",
                "minimal coaxial arcs",
                "subtle ribbon-like contours",
                "clean architectural facets",
            ],
            "environment": [
                "open negative-space retail bay",
                "structured architectural backdrop",
                "calm studio void",
                "measured spatial grid",
            ],
        },
        "section": {
            "framing": [
                "planar orthographic layout",
                "gentle isometric framing",
                "radial diagram posture",
                "stacked elevation view",
            ],
            "lighting": [
                "soft studio glow with restrained highlights",
                "sheeted daylight gradients",
                "half-toned studio wash",
                "calm perimeter glow",
            ],
            "palette": [
                "mist gray with electric blue pulses",
                "cool slate with ivory bands",
                "graphite base with cyan sparks",
                "charcoal with muted teal overlays",
            ],
            "geometry": [
                "clean networked arcs",
                "floating planes and dots",
                "disciplined concentric ribbons",
                "stacked line work",
            ],
            "environment": [
                "dark minimal background",
                "calm studio backdrop",
                "soft gradient void",
                "architectural plinth",
            ],
        },
    }

    ABSTRACT_STOPWORDS = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
        "into",
        "over",
        "they",
        "their",
        "its",
        "are",
        "is",
        "to",
        "of",
        "in",
        "on",
        "a",
        "an",
        "we",
        "as",
        "by",
        "or",
    }
    
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
            
            self.llm = None
    
    def generate_hero_image(
        self,
        query: str,
        report_dir: str,
        intent: str = "market",
        exec_summary: str = None,
        anchor_coverage: Optional[float] = None,
        hero_brief: Optional[Dict[str, Any]] = None,
    ) -> Optional[Tuple[str, str]]:
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

        # Note: Image generation is now always enabled for thesis-path reports
        # regardless of anchor coverage. Asset gating is handled at the agent level.
        # This check is kept for backward compatibility but should not block images.
        if (
            intent in {"theory", "thesis"}
            and getattr(STIConfig, 'REQUIRE_ANCHORS_FOR_ASSETS', False)
        ):
            if anchor_coverage is not None and anchor_coverage < getattr(STIConfig, 'ANCHOR_COVERAGE_MIN', 0.70):
                logger.debug("Anchor coverage below minimum, but images still enabled per policy.")
                # Don't return None - allow images to be generated
        
        # Validate report_dir
        report_path = Path(report_dir)
        if not report_path.exists():
            logger.error(f"❌ Report directory does not exist: {report_dir}")
            return None
        logger.debug(f"✅ Report directory exists: {report_dir}")
        
        try:
            prompt, template_id, context_snapshot = self._build_hero_prompt(
                query,
                intent,
                exec_summary=exec_summary,
                hero_brief=hero_brief,
            )
            logger.info(f"📝 Generated prompt (length: {len(prompt)}): {prompt[:100]}...")
            logger.debug(f"📝 Full prompt: {prompt}")
            prompt_used = prompt
            
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
            try:
                self._record_image_manifest(
                    report_path,
                    {
                        'type': 'hero',
                        'slot': 'hero',
                        'section': 'Hero',
                        'anchor_section': (hero_brief or {}).get("anchor_section") or "header",
                        'template': template_id,
                        'template_version': TEMPLATE_VERSION,
                        'context': context_snapshot,
                        'metric_focus': context_snapshot.get("metric_focus", []),
                        'alt': (hero_brief or {}).get("alt"),
                        'image': relative_path,
                    },
                )
            except Exception as manifest_error:
                logger.debug(f"Could not record hero image manifest: {manifest_error}")
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
        return f"{core} {self.STI_IMAGE_STYLE}"
    
    def _build_hero_prompt(
        self,
        query: str,
        intent: str,
        exec_summary: Optional[str] = None,
        hero_brief: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str, Dict[str, Any]]:
        """Build hero prompt emphasizing style + abstract placeholders."""
        logger.debug(f"🎨 Building hero prompt: query='{query}', intent='{intent}'")
        tokens = self._hero_tokens(query, exec_summary, hero_brief)
        style = self._style_profile("hero", query)
        metric_focus = (hero_brief or {}).get("metric_focus") or []
        metric_labels = self._metric_focus_labels(metric_focus)
        context_snapshot: Dict[str, Any] = {
            "tokens": tokens,
            "style": style,
            "metric_focus": metric_focus,
            "metric_labels": metric_labels,
        }
        template_id = "hero_decision_window"
        prompt = self._render_template(template_id, context_snapshot, seed=query)
        logger.debug(f"✅ Built hero prompt: {prompt[:100]}...")
        return prompt, template_id, context_snapshot
    
    def generate_section_image(
        self,
        section_name: str,
        section_content: str,
        query: str,
        intent: str,
        report_dir: str,
        anchor_coverage: Optional[float] = None,
        brief: Optional[Dict[str, Any]] = None,
    ) -> Optional[Tuple[str, str]]:
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

        # Note: Image generation now works for all reports regardless of anchor status
        # Removed anchor requirement check to ensure images are generated for every report
        
        # Validate report_dir
        report_path = Path(report_dir)
        if not report_path.exists():
            logger.error(f"❌ Report directory does not exist: {report_dir}")
            return None
        
        try:
            prompt, template_id, context_snapshot = self._build_section_prompt(
                section_name,
                section_content or "",
                query,
                intent,
                brief=brief,
            )
            logger.info(f"📝 Generated section prompt (length: {len(prompt)}): {prompt[:100]}...")
            logger.debug(f"📝 Full prompt: {prompt}")
            prompt_used = prompt
            
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
            try:
                slot_name = self._slot_name(section_name)
                anchor_section = (brief or {}).get("anchor_section")
                if not anchor_section:
                    anchor_section = "signals_and_thesis" if slot_name == "signal_map" else "mini_case_story"
                self._record_image_manifest(
                    report_path,
                    {
                        'type': 'section',
                        'section': section_name,
                        'slot': slot_name,
                        'anchor_section': anchor_section,
                        'template': template_id,
                        'template_version': TEMPLATE_VERSION,
                        'context': context_snapshot,
                        'metric_focus': context_snapshot.get("metric_focus", []),
                        'alt': (brief or {}).get("alt"),
                        'image': relative_path,
                    },
                )
            except Exception as manifest_error:
                logger.debug(f"Could not record section image manifest: {manifest_error}")
            return relative_path, attribution
            
        except Exception as e:
            import traceback
            error_type = type(e).__name__
            error_msg = str(e)
            logger.error(f"❌ Section image generation failed: {error_type}: {error_msg}")
            logger.debug(f"❌ Full traceback:\n{traceback.format_exc()}")
            return None
    
    def _extract_key_terms_from_content(self, content: str, max_terms: int = 3) -> List[str]:
        """Extract key technical terms or concepts from content for visual interpretation"""
        if not content:
            return []
        
        import re
        
        # Technical/domain keywords that suggest visual concepts
        tech_keywords = [
            'ai', 'artificial intelligence', 'machine learning', 'neural', 'algorithm',
            'drone', 'swarm', 'autonomous', 'robotic', 'sensor', 'satellite',
            'quantum', 'blockchain', 'crypto', 'semiconductor', 'chip', 'processor',
            'cloud', 'edge', '5g', 'iot', 'network', 'system', 'infrastructure',
            'cognitive', 'industrialization', 'coordination', 'framework', 'model'
        ]
        
        content_lower = content.lower()
        found_terms = []
        
        # Find matching keywords
        for keyword in tech_keywords:
            if keyword in content_lower and keyword not in found_terms:
                found_terms.append(keyword)
                if len(found_terms) >= max_terms:
                    break
        
        # If no keywords found, extract capitalized words (likely proper nouns/technologies)
        if not found_terms:
            capitalized = re.findall(r'\b[A-Z][a-z]+\b', content)
            # Filter out common words and take unique ones
            skip_words = {'The', 'This', 'That', 'These', 'Those', 'For', 'And', 'With', 'From'}
            found_terms = [w for w in capitalized if w not in skip_words][:max_terms]
        
        return found_terms
    
    def _build_section_prompt(
        self,
        section_name: str,
        section_content: str,
        query: str,
        intent: str,
        brief: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str, Dict[str, Any]]:
        """Build section prompt that leans on abstract styling and contextual placeholders."""
        logger.debug(f"🎨 Building section prompt: section='{section_name}', intent='{intent}'")
        section_label = (section_name or "section")
        section_lower = section_label.lower()
        metric_focus = (brief or {}).get("metric_focus") or []
        metric_labels = self._metric_focus_labels(metric_focus)
        if section_lower.startswith("signal"):
            tokens = self._signal_tokens(section_content, query, brief)
            style = self._style_profile("section", f"{query}-{section_label}-signal")
            lines = [
                f"Abstract structure: {tokens['structure']} representing {tokens['context']}.",
                f"Motion: {tokens['motion']} that suggests {tokens['direction']}.",
                f"Visual elements: {tokens['elements']}.",
                "Mood: analytical, calm, precise.",
                f"Lighting: {style['lighting']} with subtle reflections on a {style['environment']}.",
                f"Composition: {style['framing']} with a centered form and generous negative space.",
                f"Color: dark neutrals with {tokens['palette']} and {style['palette']} accents.",
                "Never literal dashboards, axes, or labels.",
            ]
            template_id = "signal_map_concentric"
        else:
            tokens = self._case_tokens(section_label, section_content, query, brief)
            style = self._style_profile("hero", f"{query}-{section_label}-case")
            if intent in {"thesis", "theory"}:
                tokens.setdefault("scene", "conceptual systems vignette")
                tokens.setdefault("time", "structured analysis window")
            lines = [
                f"Scene: {tokens['scene']} during {tokens['time']}.",
                f"Moment: {tokens['moment']}.",
                f"Personas: {tokens['personas']}.",
                f"Mood: {tokens['mood']}.",
                f"Lighting: {tokens['lighting']} styled as {style['lighting']}.",
                f"Props: {tokens['props']}.",
                f"Composition: {style['framing']} with clear view of {tokens['focal_point']} and minimal background distractions.",
            ]
            template_id = "case_play_activation"
        if section_lower.startswith("signal"):
            context_seed = f"{query}-{section_label}-signal"
        else:
            context_seed = f"{query}-{section_label}-case"
        if intent in {"thesis", "theory"} and not section_lower.startswith("signal"):
            tokens.setdefault("scene", "conceptual systems vignette")
            tokens.setdefault("time", "structured analysis window")
        context_snapshot: Dict[str, Any] = {
            "tokens": tokens,
            "style": style,
            "metric_focus": metric_focus,
            "metric_labels": metric_labels,
        }
        prompt = self._render_template(template_id, context_snapshot, seed=context_seed)
        logger.debug(f"✅ Built section prompt: {prompt[:100]}...")
        return prompt, template_id, context_snapshot

    def _style_profile(self, kind: str, seed: str) -> Dict[str, str]:
        variants = self.STYLE_VARIANTS.get(kind, self.STYLE_VARIANTS["section"])
        salt = secrets.randbits(64)
        rng = random.Random(salt ^ hash(seed))
        return {key: rng.choice(values) for key, values in variants.items()}

    def _flatten_text(self, value: Any) -> str:
        if not value:
            return ""
        if isinstance(value, list):
            return " ".join(str(v) for v in value if v)
        return str(value)

    def _abstract_phrase(self, text: Optional[str], fallback: str, max_words: int = 8) -> str:
        if not text:
            return fallback
        tokens = re.findall(r"[a-z0-9']+", text.lower())
        filtered = [t for t in tokens if t not in self.ABSTRACT_STOPWORDS]
        if not filtered:
            return fallback
        phrase = " ".join(filtered[:max_words]).strip()
        return phrase or fallback

    def _hero_tokens(
        self,
        query: str,
        exec_summary: Optional[str],
        hero_brief: Optional[Dict[str, Any]],
    ) -> Dict[str, str]:
        summary = exec_summary or ""
        brief = hero_brief or {}
        scene = self._flatten_text(brief.get("setting"))
        personas = self._flatten_text(brief.get("persona"))
        action = self._flatten_text(brief.get("action"))
        urgency = self._flatten_text(brief.get("urgency_symbol"))
        props = self._flatten_text(brief.get("props"))
        mood = self._flatten_text(brief.get("mood"))
        lighting = self._flatten_text(brief.get("lighting")) or "polished editorial lighting"
        tokens = {
            "scene": self._abstract_phrase(scene or summary or query, "store-studio collaboration zone"),
            "personas": self._abstract_phrase(personas or "operator team", "operator team"),
            "action": self._abstract_phrase(action or summary or query, "aligning activation details"),
            "symbolism": self._abstract_phrase(urgency or "subtle timing cue", "subtle timing cue"),
            "props": self._abstract_phrase(props or summary or query, "event toolkit"),
            "mood": self._abstract_phrase(mood or "confident", "confident"),
            "lighting": lighting,
            "focal_point": self._abstract_phrase(action or props or summary or query, "collaboration moment"),
        }
        return tokens

    def _signal_tokens(
        self,
        section_content: str,
        query: str,
        brief: Optional[Dict[str, Any]],
    ) -> Dict[str, str]:
        brief = brief or {}
        base_context = section_content or query
        structure = self._flatten_text(brief.get("structure"))
        elements = self._flatten_text(brief.get("elements"))
        motion = self._flatten_text(brief.get("motion"))
        palette = self._flatten_text(brief.get("palette"))
        direction = self._abstract_phrase(section_content, "concentrated demand waves")
        return {
            "context": self._abstract_phrase(base_context, "event dynamics"),
            "structure": self._abstract_phrase(structure or "lattice arcs", "lattice arcs"),
            "elements": self._abstract_phrase(elements or "nodes and arcs", "nodes and arcs"),
            "motion": self._abstract_phrase(motion or "radial pulses", "radial pulses"),
            "direction": direction,
            "palette": self._abstract_phrase(palette or "electric blue highlights", "electric blue highlights"),
        }

    def _case_tokens(
        self,
        section_name: str,
        section_content: str,
        query: str,
        brief: Optional[Dict[str, Any]],
    ) -> Dict[str, str]:
        brief = brief or {}
        scene = self._flatten_text(brief.get("scene"))
        moment = self._flatten_text(brief.get("moment"))
        personas = self._flatten_text(brief.get("persona"))
        mood = self._flatten_text(brief.get("mood"))
        props = self._flatten_text(brief.get("props"))
        lighting = self._flatten_text(brief.get("lighting")) or "polished editorial lighting"
        time_context = self._abstract_phrase(moment or section_content or query, "activation window")
        focal_point = self._abstract_phrase(scene or moment or section_name, "collaboration focal point")
        return {
            "scene": self._abstract_phrase(scene or section_content or section_name, section_name.lower()),
            "time": time_context,
            "moment": self._abstract_phrase(moment or section_content or query, "operators aligning the play"),
            "personas": self._abstract_phrase(personas or "operator team", "operator team"),
            "mood": self._abstract_phrase(mood or "precise", "precise"),
            "lighting": lighting,
            "props": self._abstract_phrase(props or section_content or query, "event toolkit"),
            "focal_point": focal_point,
        }

    def _slugify_query(self, query: str) -> str:
        """Convert query to filesystem-safe slug"""
        import re
        slug = re.sub(r'[^a-z0-9]+', '_', query.lower())
        result = slug[:30]
        logger.debug(f"🔤 Slugified '{query}' → '{result}'")
        return result

    @staticmethod
    def _slot_name(section_name: Optional[str]) -> str:
        if not section_name:
            return "section"
        label = section_name.strip().lower()
        if "signal" in label:
            return "signal_map"
        return re.sub(r'[^a-z0-9]+', '_', label).strip("_") or "section"

    def _metric_focus_labels(self, metric_focus: Optional[List[str]]) -> List[str]:
        labels: List[str] = []
        for metric in metric_focus or []:
            friendly = friendly_metric_name(metric)
            if friendly:
                labels.append(friendly)
        return labels

    def _render_template(
        self,
        template_id: str,
        context: Dict[str, Any],
        *,
        seed: str = "",
    ) -> str:
        tokens = context.get("tokens", {})
        style = context.get("style", {})
        metrics = context.get("metric_labels", [])
        seed_material = f"{template_id}|{seed}"
        seed_int = int(hashlib.sha256(seed_material.encode("utf-8")).hexdigest(), 16)
        rng = random.Random(seed_int)

        def _line(options: List[str], fallback: str) -> str:
            usable = [opt for opt in options if opt]
            if not usable:
                usable = [fallback]
            return rng.choice(usable)

        if template_id == "hero_decision_window":
            scene = tokens.get("scene") or "quiet operator decision table"
            personas = tokens.get("personas") or "operator team"
            action = tokens.get("action") or "reviewing options together"
            symbolism = tokens.get("symbolism") or "single highlighted note on the table"
            props = tokens.get("props") or "laptops, notebooks, printed brief pages"
            mood = tokens.get("mood") or "calm, thoughtful, precise"
            lighting = tokens.get("lighting") or "soft natural window light"
            focal = tokens.get("focal_point") or "moment of shared agreement"
            style_line = style.get("lighting", "subtle editorial daylight with gentle contrast")
            framing = style.get(
                "framing",
                "simple eye level framing, medium wide, plenty of margin around the team",
            )
            palette = style.get("palette", "soft neutrals, ink blacks, warm paper whites")
            geometry = style.get("geometry", "clean straight lines and understated furnishings")
            environment = style.get(
                "environment",
                "uncluttered strategy workspace with open negative space",
            )
            lines = [
                _line([
                    f"Scene: {scene}, a calm working session.",
                    f"Scene: {scene}.",
                ], f"Scene: {scene}, a calm working session."),
                _line([
                    f"Personas: {personas}, relaxed but focused.",
                    f"Operators: {personas} coordinate quietly at the table.",
                ], f"Personas: {personas}, relaxed but focused."),
                _line([
                    f"Action: {action}, they talk through the tradeoffs at the table.",
                    f"They commit to the favored play by {action}.",
                ], f"Action: {action}, they talk through the tradeoffs at the table."),
                f"Symbolism: {symbolism} suggesting long term thinking, not urgency.",
                f"Key objects: {props} placed casually, with visible notes and margins.",
                f"Mood: {mood}, grounded and human, not theatrical.",
                f"Lighting: {lighting} styled as {style_line}.",
                f"Composition: {framing} with generous negative space and focus on {focal}.",
                f"Palette: {palette} with {geometry} in a {environment} that feels real and usable.",
            ]
            if metrics:
                lines.append(f"Metric focus: {', '.join(metrics)}.")
            core = " ".join(lines)
            return self._sti_prompt(core)

        if template_id == "signal_map_concentric":
            context_label = tokens.get("context") or "market signal map for an operator essay"
            structure = tokens.get("structure") or "concentric rings, like an editorial diagram"
            motion = tokens.get("motion") or "slow gradients that feel like drifting attention"
            direction = tokens.get("direction") or "shifts in demand toward the center"
            elements = tokens.get("elements") or "simple nodes, arcs, and soft fields of tone"
            palette_hint = tokens.get("palette") or "muted ink blue accent"
            lighting = style.get("lighting", "soft studio glow, almost paper like")
            framing = style.get("framing", "flat editorial layout on a light background")
            palette = style.get(
                "palette",
                "soft neutrals with muted ink like accents instead of neon color",
            )
            environment = style.get(
                "environment",
                "clean architectural plinth or page surface with subtle shadow",
            )
            lines = [
                f"Abstract structure: {structure} representing {context_label}.",
                f"Motion: {motion} that suggests {direction} rather than aggressive pulses.",
                f"Visual elements: {elements}, drawn with a diagram like simplicity.",
                "Mood: analytical, calm, almost like a margin sketch from a strategy essay.",
                f"Lighting: {lighting} with subtle reflections on a {environment}.",
                f"Composition: {framing} with a centered form and generous negative space around it.",
                f"Color: {palette} with a single {palette_hint} accent for emphasis.",
                "Avoid literal dashboards, axes, UI widgets, or labels.",
            ]
            if metrics:
                lines.append(f"Metric focus: {', '.join(metrics)}.")
            core = " ".join(lines)
            return self._sti_prompt(core)

        if template_id == "case_play_activation":
            scene = tokens.get("scene") or "activation planning vignette"
            time_window = tokens.get("time") or "pilot planning window"
            moment = tokens.get("moment") or "operators quietly agree on the next step"
            personas = tokens.get("personas") or "operator team"
            mood = tokens.get("mood") or "quietly confident and reflective"
            lighting = tokens.get("lighting") or "soft editorial daylight"
            props = tokens.get("props") or "laptops, notebooks, simple event toolkit"
            focal = tokens.get("focal_point") or "shared focal point on the table"
            framing = style.get(
                "framing",
                "grounded eye level, candid framing as if from a behind the scenes interview",
            )
            lines = [
                _line([
                    f"Scene: {scene} during the {time_window}.",
                    f"Scene: {scene}.",], f"Scene: {scene} during the {time_window}."),
                f"Moment: {moment}, mid conversation rather than posed.",
                f"Personas: {personas}, engaged but relaxed.",
                f"Mood: {mood}, focused on clarity over drama.",
                f"Lighting: {lighting} styled as {style.get('lighting', 'subtle editorial glow, minimal contrast')}.",
                f"Props: {props} with visible notes, printouts, and open tabs.",
                "Expressions: natural, as if captured between sentences in a discussion.",
                f"Composition: {framing} with clear view of {focal} and a simple, unobtrusive background.",
            ]
            if metrics:
                lines.append(f"Metric focus: {', '.join(metrics)}.")
            core = " ".join(lines)
            return self._sti_prompt(core)

        # Fallback to legacy behavior if template not recognized
        tokens_flat = " ".join(str(v) for v in context.get("tokens", {}).values() if v)
        fallback = tokens_flat or "Editorial style operator visual, calm, human, thoughtful, lit like a magazine essay illustration"
        return self._sti_prompt(fallback)
