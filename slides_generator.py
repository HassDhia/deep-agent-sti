"""
Google Slides Generator for STI Intelligence Reports

Generates cinematic slide decks using Google Slides API following the provided
design spec: hero slides, collage tiles, angled typography, and dynamic content.
"""

import os
import json
import logging
import hashlib
import math
import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

try:
    from google.oauth2 import service_account
    from google.oauth2.credentials import Credentials as OAuthCredentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
    GOOGLE_APIS_AVAILABLE = True
except ImportError:
    GOOGLE_APIS_AVAILABLE = False
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.warning("⚠️ Google API libraries not available - slide generation disabled")

from config import STIConfig
from slides_template_config import SlidesTemplateConfig

try:
    from qa_style import StyleQA
    QA_AVAILABLE = True
except ImportError:
    QA_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("Style QA module not available")

logger = logging.getLogger(__name__)


class SlidesGenerator:
    """
    Generates Google Slides presentations from STI intelligence reports.
    
    Follows the design spec:
    - Hero slide with background image, title, subtitle, date, logo
    - Collage slide with 4-8 images, sticker, angled big word
    - Content slides with bullets, headings, quotes
    """
    
    # Design system constants - DEPRECATED: All values now come from SlidesTemplateConfig
    # These are kept only for backward compatibility in case any code still references them
    # All new code should use SlidesTemplateConfig methods directly
    
    @property
    def FONT_FAMILY_PRIMARY(self) -> str:
        """DEPRECATED: Use SlidesTemplateConfig.get_font_family() instead"""
        return SlidesTemplateConfig.get_font_family('primary')
    
    @property
    def FONT_SIZE_HERO_TITLE(self) -> int:
        """DEPRECATED: Use SlidesTemplateConfig.get_font_size('HERO_TITLE') instead"""
        return SlidesTemplateConfig.get_font_size('HERO_TITLE')
    
    @property
    def FONT_SIZE_HERO_SUBTITLE(self) -> int:
        """DEPRECATED: Use SlidesTemplateConfig.get_font_size('HERO_SUBTITLE') instead"""
        return SlidesTemplateConfig.get_font_size('HERO_SUBTITLE')
    
    @property
    def FONT_SIZE_CONTENT_TITLE(self) -> int:
        """DEPRECATED: Use SlidesTemplateConfig.get_font_size('CONTENT_TITLE') instead"""
        return SlidesTemplateConfig.get_font_size('CONTENT_TITLE')
    
    @property
    def FONT_SIZE_BODY(self) -> int:
        """DEPRECATED: Use SlidesTemplateConfig.get_font_size('BODY') instead"""
        return SlidesTemplateConfig.get_font_size('BODY')
    
    @property
    def FONT_SIZE_META(self) -> int:
        """DEPRECATED: Use SlidesTemplateConfig.get_font_size('META') instead"""
        return SlidesTemplateConfig.get_font_size('META')
    
    @property
    def SPACING_TITLE_TO_BODY(self) -> int:
        """DEPRECATED: Use SlidesTemplateConfig.get_spacing('TITLE_TO_BODY') instead"""
        return SlidesTemplateConfig.get_spacing('TITLE_TO_BODY')
    
    @property
    def SPACING_BULLET_ABOVE(self) -> int:
        """DEPRECATED: Use SlidesTemplateConfig.get_spacing('BULLET_ABOVE') instead"""
        return SlidesTemplateConfig.get_spacing('BULLET_ABOVE')
    
    @property
    def SPACING_BULLET_BELOW(self) -> int:
        """DEPRECATED: Use SlidesTemplateConfig.get_spacing('BULLET_BELOW') instead"""
        return SlidesTemplateConfig.get_spacing('BULLET_BELOW')
    
    @property
    def SPACING_BULLET_INDENT(self) -> int:
        """DEPRECATED: Use SlidesTemplateConfig.get_spacing('BULLET_INDENT') instead"""
        return SlidesTemplateConfig.get_spacing('BULLET_INDENT')
    
    def _resolve_theme_color(self, color_name: str, use_theme: bool = None, 
                             for_shape_fill: bool = False) -> Dict[str, Any]:
        """
        Resolve theme color to API format using template config.
        
        Args:
            color_name: Color name from SlidesTemplateConfig.THEME_COLORS
            use_theme: If True, prefer theme color; if False, use RGB fallback.
                      If None, uses STIConfig.ENABLE_THEME_COLORS if available
            for_shape_fill: If True, returns color directly (for solidFill.color).
                           If False, returns wrapped in opaqueColor (for foregroundColor).
        
        Returns:
            Color dict in Google Slides API format
        """
        # Check if theme colors are enabled
        if use_theme is None:
            use_theme = getattr(STIConfig, 'ENABLE_THEME_COLORS', True)
        
        color_dict = SlidesTemplateConfig.resolve_theme_color(color_name, use_theme=use_theme)
        
        # For shape fills, we need the color directly, not wrapped in opaqueColor
        if for_shape_fill and 'opaqueColor' in color_dict:
            return color_dict['opaqueColor']
        elif for_shape_fill and 'themeColor' in color_dict:
            return color_dict
        
        # For text colors, return as-is (with opaqueColor wrapper)
        return color_dict
    
    # Spacing (in PT)
    SPACING_TITLE_TO_BODY = 16  # Space after title
    SPACING_BULLET_ABOVE = 8  # Space before bullet
    SPACING_BULLET_BELOW = 8  # Space after bullet
    SPACING_BULLET_INDENT = 20  # Bullet indentation
    
    # Layout (in EMU - 1 cm = 360,000 EMU) - DEPRECATED: Use SlidesTemplateConfig
    @property
    def MARGIN_LEFT_CONTENT(self) -> int:
        """DEPRECATED: Use SlidesTemplateConfig.get_layout_dimension('MARGIN_LEFT_CONTENT') instead"""
        return SlidesTemplateConfig.get_layout_dimension('MARGIN_LEFT_CONTENT')
    
    @property
    def MARGIN_TOP_CONTENT(self) -> int:
        """DEPRECATED: Use SlidesTemplateConfig.get_layout_dimension('MARGIN_TOP_CONTENT') instead"""
        return SlidesTemplateConfig.get_layout_dimension('MARGIN_TOP_CONTENT')
    
    @property
    def MAX_WIDTH_BODY(self) -> int:
        """DEPRECATED: Use SlidesTemplateConfig.get_layout_dimension('MAX_WIDTH_BODY') instead"""
        return SlidesTemplateConfig.get_layout_dimension('MAX_WIDTH_BODY')
    
    def __init__(self, credentials_path: Optional[str] = None, use_oauth: Optional[bool] = None):
        """
        Initialize SlidesGenerator with Google API authentication.
        
        Args:
            credentials_path: Path to service account JSON file (if using service account).
                            If None, uses GOOGLE_APPLICATION_CREDENTIALS env var or OAuth.
            use_oauth: If True, use OAuth 2.0 user authentication. If None, uses STIConfig.GOOGLE_USE_OAUTH
        """
        if not GOOGLE_APIS_AVAILABLE:
            raise ImportError(
                "Google API libraries not available. Install with: "
                "pip install google-api-python-client google-auth google-auth-httplib2 google-auth-oauthlib"
            )
        
        self.use_oauth = use_oauth if use_oauth is not None else STIConfig.GOOGLE_USE_OAUTH
        
        # Initialize Google API clients
        try:
            if self.use_oauth:
                creds = self._get_oauth_credentials()
            else:
                self.credentials_path = credentials_path or STIConfig.GOOGLE_CREDENTIALS_PATH or os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
                if not self.credentials_path:
                    raise ValueError(
                        "Service account credentials not configured. Set GOOGLE_CREDENTIALS_PATH "
                        "in config.py or set GOOGLE_USE_OAUTH=True for OAuth authentication."
                    )
                
                if not os.path.exists(self.credentials_path):
                    raise FileNotFoundError(f"Credentials file not found: {self.credentials_path}")
                
                creds = service_account.Credentials.from_service_account_file(
                    self.credentials_path,
                    scopes=[
                        'https://www.googleapis.com/auth/presentations',
                        'https://www.googleapis.com/auth/drive'
                    ]
                )
            
            self.slides_service = build('slides', 'v1', credentials=creds)
            self.drive_service = build('drive', 'v3', credentials=creds)
            logger.info(f"✅ Google API clients initialized successfully ({'OAuth' if self.use_oauth else 'Service Account'})")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Google API clients: {e}")
            raise
    
    def _get_oauth_credentials(self) -> OAuthCredentials:
        """
        Get OAuth 2.0 credentials, prompting for authorization if needed.
        
        Returns:
            OAuthCredentials object
        """
        scopes = [
            'https://www.googleapis.com/auth/presentations',
            'https://www.googleapis.com/auth/drive'
        ]
        
        token_file = STIConfig.GOOGLE_OAUTH_TOKEN_FILE
        creds = None
        
        # Load existing token if available
        if os.path.exists(token_file):
            try:
                creds = OAuthCredentials.from_authorized_user_file(token_file, scopes)
                logger.debug(f"✅ Loaded OAuth token from {token_file}")
            except Exception as e:
                logger.warning(f"⚠️ Could not load token file: {e}")
        
        # If no valid credentials, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    logger.info("✅ Refreshed OAuth token")
                except Exception as e:
                    logger.warning(f"⚠️ Token refresh failed: {e}, requesting new authorization")
                    creds = None
            
            if not creds:
                # Need to get new credentials
                client_id = STIConfig.GOOGLE_OAUTH_CLIENT_ID or os.getenv('GOOGLE_OAUTH_CLIENT_ID')
                client_secret = STIConfig.GOOGLE_OAUTH_CLIENT_SECRET or os.getenv('GOOGLE_OAUTH_CLIENT_SECRET')
                
                if not client_id or not client_secret:
                    raise ValueError(
                        "OAuth credentials not configured. Please set:\n"
                        "  1. GOOGLE_OAUTH_CLIENT_ID in config.py or GOOGLE_OAUTH_CLIENT_ID env var\n"
                        "  2. GOOGLE_OAUTH_CLIENT_SECRET in config.py or GOOGLE_OAUTH_CLIENT_SECRET env var\n"
                        "\n"
                        "To get OAuth credentials:\n"
                        "  1. Go to https://console.cloud.google.com/apis/credentials\n"
                        "  2. Create OAuth 2.0 Client ID (Desktop app)\n"
                        "  3. Add authorized redirect URI: http://localhost:8080/\n"
                        "  4. Copy Client ID and Client Secret to config.py"
                    )
                
                # Create OAuth flow
                client_config = {
                    "installed": {
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                        "redirect_uris": ["http://localhost:8080/"]
                    }
                }
                
                flow = InstalledAppFlow.from_client_config(client_config, scopes)
                # Try ports 8080-8090 if 8080 is in use
                import socket
                port = 8080
                for attempt in range(11):
                    try:
                        # Test if port is available
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                            s.bind(('localhost', port))
                        break
                    except OSError:
                        port = 8080 + attempt + 1
                        if port > 8090:
                            raise OSError("No available ports in range 8080-8090")
                
                creds = flow.run_local_server(port=port, open_browser=True)
                logger.info(f"✅ OAuth authorization completed on port {port}")
            
            # Save credentials for future use
            try:
                with open(token_file, 'w') as token:
                    token.write(creds.to_json())
                logger.info(f"💾 Saved OAuth token to {token_file}")
            except Exception as e:
                logger.warning(f"⚠️ Could not save token: {e}")
        
        return creds
    
    def generate_slides(self, report_dir: str, query: str, metadata: Dict[str, Any],
                       json_ld_artifact: Dict[str, Any], markdown_report: str) -> Optional[Dict[str, str]]:
        """
        Generate Google Slides presentation from report data.
        
        Args:
            report_dir: Path to report directory (contains images, metadata, etc.)
            query: Search query used for report
            metadata: Report metadata dictionary
            json_ld_artifact: JSON-LD structured data
            markdown_report: Full markdown report text
            
        Returns:
            Dictionary with 'slides_url' and 'pdf_path' if successful, None otherwise
        """
        if not STIConfig.ENABLE_SLIDES_GENERATION:
            logger.info("ℹ️ Slide generation disabled in config")
            return None
        
        try:
            checksum_path = Path(report_dir) / 'slides_checksum.txt'
            signature = self._compute_slides_signature(query, metadata, json_ld_artifact, markdown_report)
            if checksum_path.exists():
                try:
                    existing_signature = checksum_path.read_text().strip()
                except Exception:
                    existing_signature = None
                if existing_signature and existing_signature == signature:
                    logger.info("ℹ️ Slides unchanged since last run; skipping regeneration.")
                    slides_url_file = Path(report_dir) / 'slides_url.txt'
                    pdf_file = Path(report_dir) / 'slides_export.pdf'
                    result: Dict[str, str] = {}
                    if slides_url_file.exists():
                        result['slides_url'] = slides_url_file.read_text().strip()
                    if pdf_file.exists():
                        result['pdf_path'] = str(pdf_file)
                    if result:
                        return result
                    logger.info("ℹ️ No cached slide outputs found; regenerating deck.")
            logger.info(f"🎨 Starting slide deck generation for: {query}")
            
            # Step 1: Create presentation (from template or scratch)
            use_template = bool(STIConfig.GOOGLE_SLIDES_TEMPLATE_ID)
            
            if use_template:
                template_id = STIConfig.GOOGLE_SLIDES_TEMPLATE_ID
                presentation_id = self._copy_template(template_id, query)
                if not presentation_id:
                    return None
            else:
                # Create from scratch
                presentation_id = self._create_presentation_from_scratch(query)
                if not presentation_id:
                    return None
            
            # Step 2: Get presentation structure and object IDs
            presentation = self.slides_service.presentations().get(
                presentationId=presentation_id
            ).execute()
            
            # Store presentation for element lookup
            self._current_presentation = presentation
            
            # Discover template structure (layouts, elements, slides) if using template
            if use_template:
                self._discover_template_structure(presentation)
            
            # Debug: Log initial presentation state
            initial_slides = presentation.get('slides', [])
            logger.debug(f"📄 Initial presentation state:")
            logger.debug(f"   Presentation ID: {presentation_id}")
            logger.debug(f"   Title: {presentation.get('title', 'N/A')}")
            logger.debug(f"   Slides: {len(initial_slides)}")
            for i, slide in enumerate(initial_slides):
                slide_id = slide.get('objectId')
                elements = slide.get('pageElements', [])
                logger.debug(f"   Slide {i+1}: {slide_id} - {len(elements)} elements")
            
            # Step 3: Extract data for slides
            slide_data = self._extract_slide_data(
                report_dir, query, metadata, json_ld_artifact, markdown_report
            )
            
            # Debug: Log extracted slide data
            logger.debug(f"📊 Extracted slide data:")
            logger.debug(f"   Title: {slide_data.get('title', 'N/A')[:50]}")
            logger.debug(f"   Subtitle: {slide_data.get('subtitle', 'N/A')[:50]}")
            logger.debug(f"   Date: {slide_data.get('date', 'N/A')}")
            logger.debug(f"   Hero image: {slide_data.get('hero_image', 'N/A')}")
            logger.debug(f"   Section images: {len(slide_data.get('section_images', []))}")
            logger.debug(f"   Sections: {list(slide_data.get('sections', {}).keys())}")
            logger.debug(f"   Big word: {slide_data.get('big_word', 'N/A')}")
            
            # Step 4: Create slides if needed (when not using template)
            if not use_template:
                creation_requests = self._create_slides_if_needed(presentation, slide_data)
                if creation_requests:
                    logger.info(f"📄 Creating {len(creation_requests)} slide(s)...")
                    try:
                        create_response = self._execute_with_backoff(
                            lambda: self.slides_service.presentations().batchUpdate(
                                presentationId=presentation_id,
                                body={'requests': creation_requests}
                            ).execute(),
                            description="Create slides batchUpdate",
                        )
                        
                        # Extract created slide IDs from response
                        if 'replies' in create_response:
                            created_slide_ids = []
                            for reply in create_response['replies']:
                                if 'createSlide' in reply:
                                    slide_id = reply['createSlide'].get('objectId')
                                    if slide_id:
                                        created_slide_ids.append(slide_id)
                            logger.debug(f"Created slide IDs: {created_slide_ids}")
                        
                        # Refresh presentation to get new slide IDs
                        presentation = self.slides_service.presentations().get(
                            presentationId=presentation_id
                        ).execute()
                        # Update stored presentation for element lookup
                        self._current_presentation = presentation
                        
                        # Debug: Verify slides were created
                        slides_after = presentation.get('slides', [])
                        logger.info(f"✅ Slides created - presentation now has {len(slides_after)} slide(s)")
                        logger.debug(f"   Slide IDs after creation: {[s.get('objectId') for s in slides_after]}")
                        if len(slides_after) < len(creation_requests) + 1:  # +1 for initial blank slide
                            logger.warning(f"⚠️ Expected more slides - created {len(creation_requests)} but presentation has {len(slides_after)}")
                        
                        # Debug: Log slide creation request details
                        logger.debug(f"   Creation request details: {json.dumps(creation_requests, indent=2, default=str)[:500]}")
                    except HttpError as e:
                        logger.error(f"❌ Failed to create slides: {e}")
                        if hasattr(e, 'content'):
                            logger.error(f"Error details: {e.content}")
                        raise
            
            # Initialize state for this run (prevent bleed-through)
            self._expected_replacements = {}
            self._last_requests = None
            
            # Step 5: Build and execute batch update requests for content
            requests = self._build_batch_requests(
                presentation, slide_data, report_dir, use_template
            )
            
            if requests:
                logger.info(f"📝 Executing {len(requests)} batch update requests...")
                
                # Debug: Log request summary
                self._log_batch_requests_summary(requests)
                
                try:
                    # Store requests for reply correlation
                    self._last_requests = list(requests)
                    
                    response = self._execute_with_backoff(
                        lambda: self.slides_service.presentations().batchUpdate(
                            presentationId=presentation_id,
                            body={'requests': requests}
                        ).execute(),
                        description="Populate slides batchUpdate",
                    )
                    
                    # Debug: Log response details
                    self._log_batch_response(response, len(requests))
                    
                    # Inspect replies for token replacement success
                    self._inspect_batch_replies(response)
                    
                    # Refresh presentation to verify changes
                    presentation = self.slides_service.presentations().get(
                        presentationId=presentation_id
                    ).execute()
                    self._current_presentation = presentation
                    
                    # Validate slides after update
                    validation_result = self._validate_slides(presentation, slide_data)
                    if not validation_result['success']:
                        logger.warning(f"⚠️ Validation issues found: {validation_result.get('issues', [])}")
                        logger.info(f"   Slides URL: https://docs.google.com/presentation/d/{presentation_id}")
                        logger.info(f"   Please check the slides manually")
                    else:
                        logger.info("✅ Successfully populated slides (validation passed)")
                    
                    # Step 5.5: Run Style QA (if available)
                    if QA_AVAILABLE:
                        try:
                            qa = StyleQA(self.slides_service)
                            qa_report = qa.validate_presentation(presentation_id)
                            
                            # Save QA report to report directory
                            qa_report_path = os.path.join(report_dir, 'style_report.json')
                            with open(qa_report_path, 'w') as f:
                                json.dump(qa_report, f, indent=2)
                            
                            # Log results
                            error_count = len(qa_report.get('errors', []))
                            warning_count = len(qa_report.get('warnings', []))
                            info_count = len(qa_report.get('info', []))
                            
                            if error_count > 0:
                                logger.error(
                                    f"❌ Style QA found {error_count} error(s), "
                                    f"{warning_count} warning(s), {info_count} info item(s)"
                                )
                                logger.error("   Style QA report saved to style_report.json")
                                # Don't prevent publish for now, but log errors
                                for error in qa_report.get('errors', [])[:5]:  # Show first 5
                                    logger.error(f"   - {error.get('type')}: {error.get('message')}")
                            elif warning_count > 0:
                                logger.warning(
                                    f"⚠️ Style QA found {warning_count} warning(s), "
                                    f"{info_count} info item(s)"
                                )
                                logger.info("   Style QA report saved to style_report.json")
                            else:
                                logger.info(
                                    f"✅ Style QA passed: {info_count} info item(s)"
                                )
                        except Exception as qa_error:
                            logger.warning(f"⚠️ Style QA failed: {qa_error}")
                            # Don't block generation if QA fails
                except HttpError as e:
                    logger.error(f"❌ Batch update failed: {e}")
                    # Log detailed error info
                    if hasattr(e, 'content'):
                        logger.error(f"Error details: {e.content}")
                        try:
                            error_content = json.loads(e.content.decode('utf-8')) if isinstance(e.content, bytes) else e.content
                            if 'error' in error_content:
                                error_details = error_content['error']
                                logger.error(f"Error code: {error_details.get('code')}")
                                logger.error(f"Error message: {error_details.get('message')}")
                                if 'details' in error_details:
                                    for detail in error_details['details']:
                                        if 'fieldViolations' in detail:
                                            for violation in detail['fieldViolations']:
                                                logger.error(f"  Field: {violation.get('field')}")
                                                logger.error(f"  Issue: {violation.get('description')}")
                        except Exception as parse_err:
                            logger.debug(f"Could not parse error content: {parse_err}")
                    raise
            
            # Step 6: Export PDF
            pdf_path = self._export_pdf(presentation_id, report_dir)
            
            # Step 7: Get slides URL
            slides_url = f"https://docs.google.com/presentation/d/{presentation_id}"
            
            # Step 8: Check if we should publish (QA passed or not available)
            qa_passed = True
            if QA_AVAILABLE:
                # Check if we have QA errors from earlier validation
                qa_report_path = os.path.join(report_dir, 'style_report.json')
                if os.path.exists(qa_report_path):
                    try:
                        with open(qa_report_path, 'r') as f:
                            qa_report = json.load(f)
                        error_count = len(qa_report.get('errors', []))
                        if error_count > 0:
                            qa_passed = False
                            logger.warning(
                                f"⚠️ Style QA failed with {error_count} error(s). "
                                f"Not writing slides_url.txt (non-publishable)."
                            )
                    except Exception as e:
                        logger.debug(f"Could not read QA report: {e}")
            
            # Step 9: Save URLs to report directory (only if QA passed)
            self._save_outputs(report_dir, slides_url, pdf_path, qa_passed=qa_passed)
            try:
                checksum_path.write_text(signature)
            except Exception as checksum_error:
                logger.warning(f"⚠️ Unable to write slides checksum: {checksum_error}")
            
            logger.info(f"🎉 Slide deck generated successfully: {slides_url}")
            
            return {
                'slides_url': slides_url,
                'pdf_path': pdf_path
            }
            
        except Exception as e:
            logger.error(f"❌ Error generating slides: {e}")
            import traceback
            logger.debug(f"Traceback:\n{traceback.format_exc()}")
            return None
    
    def _copy_template(self, template_id: str, query: str) -> Optional[str]:
        """Copy the master template and return new presentation ID."""
        try:
            query_slug = self._slugify_query(query)
            timestamp = datetime.now().strftime('%Y%m%d')
            name = f"STI Deck - {query_slug} - {timestamp}"
            
            # Prepare copy request
            copy_body = {'name': name}
            
            # If folder ID is configured, set parent folder
            if STIConfig.GOOGLE_DRIVE_FOLDER_ID:
                copy_body['parents'] = [STIConfig.GOOGLE_DRIVE_FOLDER_ID]
            
            # Check if destination folder is in a Shared Drive
            drive_params = {'supportsAllDrives': True, 'fields': 'id'}
            if STIConfig.GOOGLE_DRIVE_FOLDER_ID:
                folder_info = self._get_folder_drive_info(STIConfig.GOOGLE_DRIVE_FOLDER_ID)
                if folder_info:
                    drive_params['driveId'] = folder_info['driveId']
            
            file = self.drive_service.files().copy(
                fileId=template_id,
                body=copy_body,
                **drive_params
            ).execute()
            
            presentation_id = file.get('id')
            logger.info(f"✅ Copied template to new presentation: {presentation_id}")
            return presentation_id
            
        except HttpError as e:
            logger.error(f"❌ Failed to copy template: {e}")
            return None
    
    def _get_folder_drive_info(self, folder_id: str) -> Optional[Dict[str, str]]:
        """Get drive information for a folder to determine if it's in a Shared Drive."""
        try:
            folder = self.drive_service.files().get(
                fileId=folder_id,
                fields='id, driveId, name',
                supportsAllDrives=True
            ).execute()
            
            drive_id = folder.get('driveId')
            if drive_id and drive_id != folder_id:
                logger.info(f"✅ Folder is in Shared Drive: {drive_id}")
                return {'driveId': drive_id, 'folderId': folder_id}
            else:
                logger.info(f"ℹ️ Folder is in My Drive (not Shared Drive)")
                return None
        except Exception as e:
            logger.warning(f"⚠️ Could not determine drive info: {e}")
            return None
    
    def _set_presentation_page_size(self, presentation_id: str) -> None:
        """
        Set explicit page size for the presentation (widescreen 16:9).
        
        This ensures consistent dimensions and prevents misalignment issues.
        Standard widescreen: 10in x 5.625in = 9144000 EMU x 5143500 EMU
        
        Args:
            presentation_id: Google Slides presentation ID
        """
        try:
            # Use presentations().update() for presentation-level properties, not batchUpdate()
            body = {
                'presentationProperties': {
                    'pageSize': {
                        'width': {'magnitude': 9144000, 'unit': 'EMU'},  # 10in (widescreen)
                        'height': {'magnitude': 5143500, 'unit': 'EMU'}  # 5.625in
                    }
                }
            }
            
            self.slides_service.presentations().update(
                presentationId=presentation_id,
                body=body
            ).execute()
            
            logger.debug("✅ Set presentation page size to widescreen (16:9)")
        except Exception as e:
            logger.warning(f"⚠️ Failed to set page size (may use default): {e}")
    
    def _get_slide_dimensions(self, presentation: Optional[Dict[str, Any]] = None) -> Tuple[int, int]:
        """
        Get slide dimensions from presentation.
        
        Args:
            presentation: Presentation object (uses self._current_presentation if None)
        
        Returns:
            Tuple of (width, height) in EMU
        """
        if presentation is None:
            presentation = getattr(self, '_current_presentation', None)
        
        if presentation:
            page_size = presentation.get('pageSize', {})
            width = page_size.get('width', {}).get('magnitude', 9144000)
            height = page_size.get('height', {}).get('magnitude', 5143500)
            return width, height
        
        # Default to widescreen if not available
        return 9144000, 5143500  # 10in x 5.625in
    
    def _create_presentation_from_scratch(self, query: str) -> Optional[str]:
        """Create a new Google Slides presentation from scratch."""
        try:
            query_slug = self._slugify_query(query)
            timestamp = datetime.now().strftime('%Y%m%d')
            title = f"STI Deck - {query_slug} - {timestamp}"
            
            # Service accounts cannot own files - must create in Shared Drive or transfer ownership
            # Check if folder is in a Shared Drive
            drive_params = {'supportsAllDrives': True}
            folder_info = None
            
            if STIConfig.GOOGLE_DRIVE_FOLDER_ID:
                folder_info = self._get_folder_drive_info(STIConfig.GOOGLE_DRIVE_FOLDER_ID)
            
            if not folder_info:
                # Folder is NOT in Shared Drive
                if not self.use_oauth:
                    # Service account can't own files in My Drive
                    logger.error("❌ Folder is not in Shared Drive and using service account")
                    logger.error("   Service accounts cannot own files in My Drive.")
                    logger.error("   Solutions:")
                    logger.error("   1. Set GOOGLE_USE_OAUTH=True in config.py (use your account)")
                    logger.error("   2. Use a Shared Drive instead")
                    logger.error("   3. Enable domain-wide delegation")
                    raise ValueError(
                        "Cannot create files in My Drive with service account. "
                        "Set GOOGLE_USE_OAUTH=True or use Shared Drive."
                    )
                else:
                    # OAuth user account can create files in My Drive
                    logger.info("📁 Creating in My Drive folder (using OAuth user account)")
                
                # OAuth user account can create files directly
                file_metadata = {
                    'name': title,
                    'mimeType': 'application/vnd.google-apps.presentation',
                    'parents': [STIConfig.GOOGLE_DRIVE_FOLDER_ID]
                }
                
                file = self.drive_service.files().create(
                    body=file_metadata,
                    fields='id',
                    supportsAllDrives=True
                ).execute()
                
                presentation_id = file.get('id')
                logger.info(f"✅ Created presentation in folder: {presentation_id}")
                
                # Set explicit page size (widescreen 16:9) to ensure consistent dimensions
                self._set_presentation_page_size(presentation_id)
                
                return presentation_id
            
            # Folder IS in Shared Drive - can create directly
            file_metadata = {
                'name': title,
                'mimeType': 'application/vnd.google-apps.presentation',
                'parents': [STIConfig.GOOGLE_DRIVE_FOLDER_ID]
            }
            drive_params['driveId'] = folder_info['driveId']
            logger.info(f"📁 Creating in Shared Drive: {folder_info['driveId']}")
            
            file = self.drive_service.files().create(
                body=file_metadata,
                fields='id',
                **drive_params
            ).execute()
            
            presentation_id = file.get('id')
            logger.info(f"✅ Created new presentation via Drive API: {presentation_id}")
            
            # Set explicit page size (widescreen 16:9) to ensure consistent dimensions
            self._set_presentation_page_size(presentation_id)
            
            return presentation_id
            
        except HttpError as e:
            if 'storageQuotaExceeded' in str(e) or 'storage quota' in str(e).lower():
                logger.error(f"❌ Storage quota error: Service accounts cannot own files in My Drive")
                logger.error(f"   Solution: Use a Shared Drive or enable domain-wide delegation")
            raise
        except Exception as e:
            logger.error(f"❌ Failed to create presentation: {e}")
            import traceback
            logger.debug(f"Traceback:\n{traceback.format_exc()}")
            return None
    
    def _slugify_query(self, query: str) -> str:
        """Convert query to URL-safe slug."""
        return "".join(c.lower() if c.isalnum() else "_" for c in query)[:30]

    def _compute_slides_signature(
        self,
        query: str,
        metadata: Dict[str, Any],
        json_ld_artifact: Dict[str, Any],
        markdown_report: str,
    ) -> str:
        metadata_hash = hashlib.sha256(
            json.dumps(metadata, sort_keys=True, default=str).encode('utf-8')
        ).hexdigest()
        jsonld_hash = hashlib.sha256(
            json.dumps(json_ld_artifact, sort_keys=True, default=str).encode('utf-8')
        ).hexdigest()
        report_hash = hashlib.sha256(markdown_report.encode('utf-8')).hexdigest()
        combined = f"{query}|{metadata_hash}|{jsonld_hash}|{report_hash}"
        return hashlib.sha256(combined.encode('utf-8')).hexdigest()

    def _execute_with_backoff(self, func, description: str = "API call", max_attempts: int = 5):
        for attempt in range(max_attempts):
            try:
                return func()
            except HttpError as error:
                if attempt == max_attempts - 1:
                    raise
                sleep_for = 2.0 * (2 ** attempt)
                logger.warning(
                    f"⚠️ {description} failed (attempt {attempt + 1}/{max_attempts}): {error}. "
                    f"Retrying in {sleep_for:.1f}s."
                )
                time.sleep(sleep_for)
            except Exception:
                raise
    
    def _extract_slide_data(self, report_dir: str, query: str, metadata: Dict[str, Any],
                           json_ld_artifact: Dict[str, Any], markdown_report: str) -> Dict[str, Any]:
        """Extract data needed for slide population."""
        # Extract title
        title = json_ld_artifact.get('headline', query)
        if not title or title == query:
            # Try to extract from markdown
            lines = markdown_report.split('\n')
            for line in lines:
                if line.startswith('# '):
                    title = line[2:].strip()
                    break
        
        # Extract subtitle (first sentence of executive summary)
        exec_summary = json_ld_artifact.get('abstract', '')
        subtitle = ""
        if exec_summary:
            sentences = exec_summary.split('. ')
            if sentences:
                subtitle = sentences[0].strip()
                if len(subtitle) > 150:
                    subtitle = subtitle[:147] + "..."
        
        # Extract date
        gen_timestamp = metadata.get('generation_timestamp', datetime.now().isoformat())
        try:
            dt = datetime.fromisoformat(gen_timestamp.replace('Z', '+00:00'))
            date_str = dt.strftime('%B %d, %Y')
        except:
            date_str = datetime.now().strftime('%B %d, %Y')
        
        # Find images
        images_dir = Path(report_dir) / "images"
        hero_image = None
        section_images = []
        
        if images_dir.exists():
            # Find hero image
            hero_files = list(images_dir.glob("hero_*.png"))
            if hero_files:
                hero_image = str(hero_files[0])
            
            # Find section images (up to 8)
            section_files = sorted(images_dir.glob("section_*.png"))[:8]
            section_images = [str(f) for f in section_files]
        
        # Extract key sections from markdown
        sections = self._parse_markdown_sections(markdown_report)
        
        # Extract signals
        signals = []
        if 'agent_stats' in metadata and 'signals' in metadata['agent_stats']:
            signals = metadata['agent_stats']['signals']
        else:
            # Try to parse from markdown
            signals = self._extract_signals_from_markdown(markdown_report)
        
        # Big word for collage (from query or key concept)
        big_word = query.split()[0].upper() if query else "INTELLIGENCE"
        
        return {
            'title': title,
            'subtitle': subtitle,
            'date': date_str,
            'hero_image': hero_image,
            'section_images': section_images,
            'sections': sections,
            'signals': signals,
            'big_word': big_word,
            'exec_summary': exec_summary
        }
    
    def _parse_markdown_sections(self, markdown: str) -> Dict[str, str]:
        """Parse key sections from markdown report."""
        sections = {}
        current_section = None
        current_text = []
        
        for line in markdown.split('\n'):
            if line.startswith('## '):
                if current_section:
                    sections[current_section] = '\n'.join(current_text).strip()
                current_section = line[3:].strip()
                current_text = []
            elif current_section and line.strip():
                current_text.append(line.strip())
        
        if current_section:
            sections[current_section] = '\n'.join(current_text).strip()
        
        return sections
    
    def _extract_signals_from_markdown(self, markdown: str) -> List[Dict[str, str]]:
        """Extract signal items from markdown."""
        signals = []
        in_signals_section = False
        
        for line in markdown.split('\n'):
            if '## Signals' in line or '## signals' in line:
                in_signals_section = True
                continue
            if in_signals_section:
                if line.startswith('##'):
                    break
                if line.startswith('- ') and '—' in line:
                    # Parse signal format: "date — description — strength | impact | trend"
                    signals.append({'text': line[2:].strip()})
        
        return signals[:6]  # Limit to 6 signals
    
    def _create_slides_if_needed(self, presentation: Dict[str, Any], 
                                  slide_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create slides if we don't have enough (when not using template)."""
        requests = []
        slides = presentation.get('slides', [])
        
        # Count how many slides we need
        sections = slide_data.get('sections', {})
        section_labels = SlidesTemplateConfig.SECTION_LABELS
        
        # Count section slides needed (one per section in SECTION_LABELS)
        num_section_slides = sum(1 for label in section_labels if label in sections)
        num_content_slides = len(sections) if sections else 3  # Default to 3 if no sections
        total_slides_needed = 1 + 1 + num_section_slides + num_content_slides  # Hero + Collage + Section + Content
        
        # Check if we already have enough slides
        if len(slides) >= total_slides_needed:
            logger.debug(f"✅ Already have {len(slides)} slide(s), need {total_slides_needed}. Skipping slide creation.")
            return requests
        
        # Calculate how many slides we need to create
        # First slide (index 0) already exists as blank slide - we'll use it for hero
        # We need to create: collage slide + section slides + content slides
        
        slides_to_create = total_slides_needed - len(slides)
        logger.debug(f"📄 Need {total_slides_needed} slides total, have {len(slides)}, creating {slides_to_create} more")
        
        # Create collage slide (insert at index 1, after existing slide)
        requests.append({
            'createSlide': {
                'insertionIndex': 1,
                'slideLayoutReference': {
                    'predefinedLayout': 'BLANK'
                }
            }
        })
        
        # Create section slides and content slides
        # Insert section slide before each section's content slide
        insertion_index = 2
        for section_label in section_labels:
            if section_label in sections:
                # Create section slide
                section_layout_id = None
                if hasattr(self, '_template_layout_cache') and 'layouts' in self._template_layout_cache:
                    layouts = self._template_layout_cache['layouts']
                    section_layout_id = layouts.get('section') or layouts.get('SectionSlide')
                
                if section_layout_id:
                    requests.append({
                        'createSlide': {
                            'insertionIndex': insertion_index,
                            'slideLayoutReference': {
                                'layoutId': section_layout_id
                            }
                        }
                    })
                else:
                    requests.append({
                        'createSlide': {
                            'insertionIndex': insertion_index,
                            'slideLayoutReference': {
                                'predefinedLayout': 'BLANK'
                            }
                        }
                    })
                insertion_index += 1
                
                # Create content slide for this section
                requests.append({
                    'createSlide': {
                        'insertionIndex': insertion_index,
                    'slideLayoutReference': {
                        'predefinedLayout': 'TITLE_AND_BODY'
                    }
                }
            })
                insertion_index += 1
        
        # Create any remaining content slides for sections not in SECTION_LABELS
        remaining_sections = [s for s in sections.keys() if s not in section_labels]
        for _ in remaining_sections:
            requests.append({
                'createSlide': {
                    'insertionIndex': insertion_index,
                    'slideLayoutReference': {
                        'predefinedLayout': 'TITLE_AND_BODY'
                    }
                }
            })
            insertion_index += 1
        
        logger.debug(f"📄 Creating {len(requests)} additional slide(s): 1 collage + {num_section_slides} section + {num_content_slides} content")
        return requests
    
    def _get_template_layouts(self, presentation: Dict[str, Any]) -> Dict[str, str]:
        """
        Discover available layouts from the template presentation.
        
        Returns a mapping of logical layout names to layout object IDs.
        Falls back to predefined layouts if template layouts aren't found.
        
        Args:
            presentation: Presentation object from API
            
        Returns:
            Dict mapping logical names (e.g., 'title', 'content') to layout IDs
        """
        layout_map = {}
        layouts = presentation.get('layouts', [])
        
        # Discover layouts from template
        for layout in layouts:
            layout_id = layout.get('objectId')
            layout_name = layout.get('layoutProperties', {}).get('name', '').lower()
            
            # Try to match layout names to logical types
            if 'title' in layout_name or layout_name == 'title':
                layout_map['title'] = layout_id
            elif 'content' in layout_name or 'body' in layout_name:
                layout_map['content'] = layout_id
            elif 'section' in layout_name or 'header' in layout_name:
                layout_map['section'] = layout_id
            elif 'two' in layout_name and 'column' in layout_name:
                layout_map['two_column'] = layout_id
            elif 'image' in layout_name and 'left' in layout_name:
                layout_map['image_left'] = layout_id
            elif 'image' in layout_name and 'right' in layout_name:
                layout_map['image_right'] = layout_id
        
        # Store discovered layouts for later use
        if not hasattr(self, '_template_layout_cache'):
            self._template_layout_cache = {}
        self._template_layout_cache.update(layout_map)
        
        logger.debug(f"📐 Discovered {len(layout_map)} layouts from template: {list(layout_map.keys())}")
        
        return layout_map
    
    def _get_layout_id(self, logical_name: str, use_predefined: bool = True) -> Optional[str]:
        """
        Get layout ID for a logical layout name.
        
        Args:
            logical_name: Logical name (e.g., 'title', 'content', 'section')
            use_predefined: If True, fall back to predefined layouts if template layout not found
            
        Returns:
            Layout ID or None
        """
        # Check cache first
        if hasattr(self, '_template_layout_cache') and logical_name in self._template_layout_cache:
            return self._template_layout_cache[logical_name]
        
        # Check template config mappings
        layout_mappings = SlidesTemplateConfig.LAYOUT_MAPPINGS
        layout_id = getattr(layout_mappings, logical_name, None)
        if layout_id:
            return layout_id
        
        # Fall back to predefined layouts
        if use_predefined:
            predefined_map = {
                'title': SlidesTemplateConfig.PREDEFINED_LAYOUTS['TITLE'],
                'content': SlidesTemplateConfig.PREDEFINED_LAYOUTS['CONTENT'],
                'section': SlidesTemplateConfig.PREDEFINED_LAYOUTS['SECTION'],
                'two_column': SlidesTemplateConfig.PREDEFINED_LAYOUTS['TWO_COLUMN'],
                'blank': SlidesTemplateConfig.PREDEFINED_LAYOUTS['BLANK'],
            }
            return predefined_map.get(logical_name)
        
        return None
    
    def _create_slide_from_layout(self, presentation_id: str, layout_name: str, 
                                  insertion_index: Optional[int] = None,
                                  object_id: Optional[str] = None) -> Optional[str]:
        """
        Create a new slide using a template layout.
        
        Args:
            presentation_id: Presentation ID
            layout_name: Logical layout name (e.g., 'title', 'content', 'section')
            insertion_index: Index where to insert (None = append at end)
            object_id: Optional object ID for the new slide
            
        Returns:
            Created slide object ID or None if failed
        """
        try:
            # Get layout ID (from template or predefined)
            layout_id = self._get_layout_id(layout_name)
            
            if not layout_id:
                logger.warning(f"⚠️  Layout '{layout_name}' not found, using BLANK")
                layout_id = SlidesTemplateConfig.PREDEFINED_LAYOUTS['BLANK']
            
            # Generate object ID if not provided
            if not object_id:
                import uuid
                object_id = f"slide_{layout_name}_{uuid.uuid4().hex[:8]}"
            
            # Build create slide request
            request_body = {
                'createSlide': {
                    'objectId': object_id,
                    'insertionIndex': insertion_index,
                }
            }
            
            # Use layout reference
            if layout_id in SlidesTemplateConfig.PREDEFINED_LAYOUTS.values():
                # Predefined layout
                request_body['createSlide']['slideLayoutReference'] = {
                    'predefinedLayout': layout_id
                }
            else:
                # Custom template layout
                request_body['createSlide']['slideLayoutReference'] = {
                    'layoutId': layout_id
                }
            
            # Execute batch update
            response = self.slides_service.presentations().batchUpdate(
                presentationId=presentation_id,
                body={'requests': [request_body]}
            ).execute()
            
            # Extract created slide ID from response
            if 'replies' in response and len(response['replies']) > 0:
                created_slide_id = response['replies'][0].get('createSlide', {}).get('objectId')
                if created_slide_id:
                    logger.debug(f"✅ Created slide from layout '{layout_name}': {created_slide_id}")
                    return created_slide_id
            
            logger.warning(f"⚠️  Failed to create slide from layout '{layout_name}'")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error creating slide from layout '{layout_name}': {e}")
            return None
    
    def _discover_template_structure(self, presentation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Discover complete template structure including layouts, elements, and placeholders.
        
        This method builds a comprehensive cache of the template structure for
        improved performance and reliability.
        
        Args:
            presentation: Presentation object from API
            
        Returns:
            Dictionary with 'layouts', 'elements', 'slides' structure
        """
        structure = {
            'layouts': {},
            'elements': {},
            'slides': {},
        }
        
        # Discover layouts
        structure['layouts'] = self._get_template_layouts(presentation)
        
        # Discover elements with caching
        structure['elements'] = self._find_template_elements(presentation)
        
        # Cache slide structure
        slides = presentation.get('slides', [])
        for slide in slides:
            slide_id = slide.get('objectId')
            structure['slides'][slide_id] = {
                'objectId': slide_id,
                'pageElements': slide.get('pageElements', []),
                'pageProperties': slide.get('pageProperties', {}),
            }
        
        # Store in instance cache
        if not hasattr(self, '_element_cache'):
            self._element_cache = {}
        self._element_cache['structure'] = structure
        
        logger.debug(f"📐 Discovered template structure: {len(structure['layouts'])} layouts, "
                    f"{len(structure['elements'])} elements, {len(structure['slides'])} slides")
        
        return structure
    
    def _find_template_elements(self, presentation: Dict[str, Any]) -> Dict[Tuple[str, str], str]:
        """
        Discover element IDs by alt text first, then placeholder tokens.
        
        Uses alt text (title/description) for deterministic discovery, falling back
        to text content scanning. This is more reliable than size heuristics.
        
        Returns:
            Dict mapping (slide_id, token) to objectId
        """
        # Check cache first
        if hasattr(self, '_element_cache') and 'elements' in self._element_cache:
            cached = self._element_cache.get('elements', {})
            if cached:
                logger.debug(f"📦 Using cached element map: {len(cached)} elements")
                return cached
        
        element_map = {}
        slides = presentation.get('slides', [])
        
        # Tokens to search for
        tokens = ['{{LOGO}}', '{{BIGWORD}}', '{{BULLETS}}', '{{H1}}', '{{TITLE}}', 
                  '{{SUBTITLE}}', '{{DATE}}', '{{IMG_1}}', '{{IMG_2}}', '{{IMG_3}}',
                  '{{IMG_4}}', '{{IMG_5}}', '{{IMG_6}}', '{{IMG_7}}', '{{IMG_8}}', '{{STICKER}}']
        
        # Alt text keys for special elements (set in template)
        alt_text_map = {
            'HERO_OVERLAY': 'HERO_OVERLAY',
            'BIGWORD': 'BIGWORD'  # Alternative to {{BIGWORD}} token
        }
        
        for slide in slides:
            slide_id = slide.get('objectId')
            page_elements = slide.get('pageElements', [])
            
            for element in page_elements:
                obj_id = element.get('objectId')
                
                # PRIORITY 1: Check alt text (title/description) first for deterministic IDs
                title = element.get('title', '')
                description = element.get('description', '')
                
                # Check for special alt text identifiers
                for key, alt_value in alt_text_map.items():
                    if title == alt_value or description == alt_value:
                        element_map[(slide_id, key)] = obj_id
                        logger.debug(f"Found {key} via alt text at {obj_id} on slide {slide_id}")
                
                # Also check if title matches token format
                if title in alt_text_map.values():
                    element_map[(slide_id, title)] = obj_id
                    logger.debug(f"Found {title} via alt text at {obj_id} on slide {slide_id}")
                
                # PRIORITY 2: Check shape text content for tokens
                shape = element.get('shape', {})
                if shape and shape.get('shapeType') == 'TEXT_BOX':
                    text_elements = shape.get('text', {}).get('textElements', [])
                    full_text = ''
                    for text_elem in text_elements:
                        if 'textRun' in text_elem:
                            full_text += text_elem['textRun'].get('content', '')
                    
                    # Check for tokens in text (only if not found via alt text)
                    # Prefer alt-text matches when both exist
                    for token in tokens:
                        token_key = token.strip('{}')
                        token_key_alt = token_key  # Also check without braces
                        
                        # Skip if already found via alt text (alt-text takes precedence)
                        if ((slide_id, token_key) not in element_map and 
                            (slide_id, token) not in element_map and
                            (slide_id, token_key_alt) not in element_map):
                            if token in full_text:
                                element_map[(slide_id, token)] = obj_id
                                logger.debug(f"Found {token} via text scan at {obj_id} on slide {slide_id}")
        
        # Cache the result
        if not hasattr(self, '_element_cache'):
            self._element_cache = {}
        self._element_cache['elements'] = element_map
        
        return element_map
    
    def _build_batch_requests(self, presentation: Dict[str, Any], slide_data: Dict[str, Any],
                             report_dir: str, use_template: bool = True) -> List[Dict[str, Any]]:
        """
        Build batch update requests for populating slides.
        
        Request order (critical for correct execution):
        1. Background (hero slide)
        2. Replace shapes with images (collage tiles + logo) - BEFORE text replacement
        3. Create additional images (stickers)
        4. Replace text tokens
        5. Transforms & styling
        6. Overlay update
        """
        requests = []
        
        # Get slide IDs
        slides = presentation.get('slides', [])
        if not slides:
            logger.warning("⚠️ No slides found in presentation")
            return requests
        
        # Initialize state (prevent bleed-through from previous runs)
        if not hasattr(self, '_template_elements'):
            self._template_elements = {}
        if not hasattr(self, '_expected_replacements'):
            self._expected_replacements = {}
        
        # Discover template elements before building requests (use cache if available)
        if use_template:
            # Check cache first (populated by _discover_template_structure)
            if hasattr(self, '_element_cache') and 'elements' in self._element_cache:
                self._template_elements = self._element_cache['elements']
            else:
                # Fallback to discovery if cache not available
                self._template_elements = self._find_template_elements(presentation)
        
        if not use_template:
            # When creating from scratch, we need to create text elements first
            # Apply background colors to all slides first
            for slide in slides:
                slide_id = slide.get('objectId')
                if slide == slides[0] and slide_data.get('hero_image'):
                    # Hero slide with image - background handled in _build_hero_slide_requests_from_scratch
                    pass
                else:
                    # Apply Cashmere background color
                    background_requests = self._build_slide_background_color_requests(slide_id)
                    requests.extend(background_requests)
            
            # Hero slide
            if len(slides) > 0:
                hero_slide_id = slides[0].get('objectId')
                hero_requests = self._build_hero_slide_requests_from_scratch(
                    hero_slide_id, slide_data, report_dir
                )
                requests.extend(hero_requests)
            
            # Collage slide
            if len(slides) > 1:
                collage_slide_id = slides[1].get('objectId')
                collage_requests = self._build_collage_slide_requests_from_scratch(
                    collage_slide_id, slide_data, report_dir
                )
                requests.extend(collage_requests)
            
            # Content slides
            sections = slide_data.get('sections', {})
            section_names = list(sections.keys())
            for i, slide in enumerate(slides[2:], start=2):
                if i - 2 < len(section_names):
                    content_requests = self._build_content_slide_requests_from_scratch(
                        slide.get('objectId'), slide_data, i - 2
                    )
                    requests.extend(content_requests)
        else:
            # Using template - replace placeholders with CORRECT ORDERING
            
            # Step 1: Background images (hero slide) and background colors (all slides)
            if len(slides) > 0:
                hero_slide_id = slides[0].get('objectId')
                hero_background_requests = self._build_hero_background_requests(
                    hero_slide_id, slide_data, report_dir
                )
                requests.extend(hero_background_requests)
            
            # Apply Cashmere background color to all other slides (content, collage)
            for slide in slides[1:]:  # Skip hero slide (already handled)
                slide_id = slide.get('objectId')
                background_requests = self._build_slide_background_color_requests(slide_id)
                requests.extend(background_requests)
            
            # Step 2: Replace shapes with images (BEFORE text replacement to preserve tokens)
            # Hero logo
            if len(slides) > 0:
                hero_slide_id = slides[0].get('objectId')
                logo_requests = self._build_logo_replacement_requests(
                    hero_slide_id, slide_data, report_dir
                )
                requests.extend(logo_requests)
            
            # Collage images
            if len(slides) > 1:
                collage_slide_id = slides[1].get('objectId')
                collage_image_requests = self._build_collage_image_requests(
                    collage_slide_id, slide_data, report_dir
                )
                requests.extend(collage_image_requests)
            
            # Step 3: Create additional images (stickers)
            if len(slides) > 1:
                collage_slide_id = slides[1].get('objectId')
                sticker_requests = self._build_sticker_requests(
                    collage_slide_id, slide_data, report_dir
                )
                requests.extend(sticker_requests)
            
            # Step 4: Replace text tokens
            if len(slides) > 0:
                hero_slide_id = slides[0].get('objectId')
                hero_text_requests = self._build_hero_text_requests(
                    hero_slide_id, slide_data
                )
                requests.extend(hero_text_requests)
            
            if len(slides) > 1:
                collage_slide_id = slides[1].get('objectId')
                collage_text_requests = self._build_collage_text_requests(
                    collage_slide_id, slide_data
                )
                requests.extend(collage_text_requests)
            
            # Content slides text (with section detection)
            sections = slide_data.get('sections', {})
            section_labels = SlidesTemplateConfig.SECTION_LABELS
            current_section_index = 0
            last_section_processed = None
            
            for i, slide in enumerate(slides[2:], start=2):
                slide_index = i - 2
                
                # Check if this is the start of a new section
                if current_section_index < len(section_labels):
                    section_name = section_labels[current_section_index]
                    if section_name in sections and last_section_processed != section_name:
                        # This is the first content slide of this section
                        # Check if there's a section slide before it (slide index - 1)
                        if i > 2 and len(slides) > i - 1:
                            # Check if previous slide is a section slide
                            prev_slide = slides[i - 1]
                            # If it's a section slide, process it
                            section_slide_requests = self._build_section_slide_requests(
                                prev_slide.get('objectId'), section_name, kicker=None
                            )
                            requests.extend(section_slide_requests)
                        last_section_processed = section_name
                
                # Process content slide
                content_text_requests = self._build_content_text_requests(
                    slide.get('objectId'), slide_data, slide_index
                )
                requests.extend(content_text_requests)
                
                # Move to next section if we've processed all content for current section
                # (This is a simplified heuristic - in practice, you'd track section boundaries more precisely)
            
            # Step 5: Transforms & styling
            if len(slides) > 1:
                collage_slide_id = slides[1].get('objectId')
                transform_requests = self._build_transform_requests(
                    collage_slide_id, slide_data
                )
                requests.extend(transform_requests)
            
            # Content slides bullets & styling (same loop structure)
            current_section_index = 0
            last_section_processed = None
            
            for i, slide in enumerate(slides[2:], start=2):
                slide_index = i - 2
                
                # Check if this is the start of a new section (for styling consistency)
                if current_section_index < len(section_labels):
                    section_name = section_labels[current_section_index]
                    if section_name in sections and last_section_processed != section_name:
                        last_section_processed = section_name
                
                content_styling_requests = self._build_content_styling_requests(
                    slide.get('objectId'), slide_data, slide_index
                )
                requests.extend(content_styling_requests)
            
            # Step 6: Overlay update (after text to ensure overlay stays behind)
            if len(slides) > 0:
                hero_slide_id = slides[0].get('objectId')
                hero_image_path = slide_data.get('hero_image')
                if hero_image_path and report_dir:
                    # Construct full path if relative
                    import os
                    if not os.path.isabs(hero_image_path):
                        hero_image_path = os.path.join(report_dir, hero_image_path)
                overlay_requests = self._build_overlay_requests(
                    hero_slide_id, hero_image_path=hero_image_path
                )
                requests.extend(overlay_requests)
        
        return requests
    
    def _build_hero_background_requests(self, slide_id: str, slide_data: Dict[str, Any],
                                   report_dir: str) -> List[Dict[str, Any]]:
        """Step 1: Build background image requests for hero slide."""
        requests = []
        
        if slide_data.get('hero_image'):
            hero_image_url = self._upload_image_to_drive(slide_data['hero_image'], report_dir)
            if hero_image_url:
                requests.append({
                    'updatePageProperties': {
                        'objectId': slide_id,
                        'pageProperties': {
                            'pageBackgroundFill': {
                                'stretchedPictureFill': {
                                    'contentUrl': hero_image_url
                                }
                            }
                        },
                        'fields': 'pageBackgroundFill.stretchedPictureFill.contentUrl'
                    }
                })
        else:
            # If no hero image, apply Cashmere background color
            requests.extend(self._build_slide_background_color_requests(slide_id))
        
        return requests
    
    def _build_slide_background_color_requests(self, slide_id: str) -> List[Dict[str, Any]]:
        """
        Build requests to apply Cashmere background color to a slide.
        
        Args:
            slide_id: Slide object ID
        
        Returns:
            List of updatePageProperties requests
        """
        background_color = self._resolve_theme_color('BACKGROUND', for_shape_fill=True)
        return [{
            'updatePageProperties': {
                'objectId': slide_id,
                'pageProperties': {
                    'pageBackgroundFill': {
                        'solidFill': {
                            'color': background_color
                        }
                    }
                },
                'fields': 'pageBackgroundFill.solidFill.color'
            }
        }]
    
    def _build_section_slide_requests(self, slide_id: str, title: str, 
                                     kicker: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Build requests for section divider slide.
        
        Args:
            slide_id: Slide object ID
            title: Section title
            kicker: Optional kicker text (small caps, above title)
        
        Returns:
            List of requests to create and style section slide
        """
        requests = []
        
        # Try to use template layout if available
        layout_id = None
        if hasattr(self, '_template_layout_cache') and 'layouts' in self._template_layout_cache:
            layouts = self._template_layout_cache['layouts']
            layout_id = layouts.get('section') or layouts.get('SectionSlide')
        
        # If we have a layout, use ReplaceAllText on placeholders
        if layout_id:
            # Use template layout with placeholders
            # Replace {{SECTION_TITLE}} and {{SECTION_KICKER}} if present
            section_title_token = '{{SECTION_TITLE}}'
            section_kicker_token = '{{SECTION_KICKER}}'
            
            # Apply title case if configured
            if SlidesTemplateConfig.SECTION_TITLE_CASE == 'TITLE':
                title = title.title()
            
            requests.append({
                'replaceAllText': {
                    'containsText': {'text': section_title_token},
                    'replaceText': title,
                    'pageObjectIds': [slide_id]
                }
            })
            
            if kicker:
                requests.append({
                    'replaceAllText': {
                        'containsText': {'text': section_kicker_token},
                        'replaceText': kicker,
                        'pageObjectIds': [slide_id]
                    }
                })
        else:
            # Fallback: create from scratch
            # Set background to accent color
            section_bg_color = self._resolve_theme_color(
                SlidesTemplateConfig.SECTION_BG_COLOR, for_shape_fill=True
            )
            requests.append({
                'updatePageProperties': {
                    'objectId': slide_id,
                    'pageProperties': {
                        'pageBackgroundFill': {
                            'solidFill': {
                                'color': section_bg_color
                            }
                        }
                    },
                    'fields': 'pageBackgroundFill.solidFill.color'
                }
            })
            
            # Create centered title text box
            title_box_id = f'section_title_{slide_id}'
            
            # Apply title case if configured
            if SlidesTemplateConfig.SECTION_TITLE_CASE == 'TITLE':
                title = title.title()
            
            # Get slide dimensions for centering (approximate)
            # Standard slide: 10in x 5.625in = 9144000 EMU x 5143500 EMU
            slide_width_emu = 9144000
            slide_height_emu = 5143500
            
            title_box_width = int(0.8 * slide_width_emu)  # 80% width
            title_box_height = int(0.2 * slide_height_emu)  # 20% height
            
            requests.append({
                'createShape': {
                    'objectId': title_box_id,
                    'shapeType': 'TEXT_BOX',
                    'elementProperties': {
                        'pageObjectId': slide_id,
                        'size': {
                            'width': {'magnitude': title_box_width, 'unit': 'EMU'},
                            'height': {'magnitude': title_box_height, 'unit': 'EMU'}
                        },
                        'transform': {
                            'scaleX': 1.0, 'scaleY': 1.0,
                            'translateX': int((slide_width_emu - title_box_width) / 2),  # Center horizontally
                            'translateY': int((slide_height_emu - title_box_height) / 2),  # Center vertically
                            'unit': 'EMU'
                        }
                    }
                }
            })
            
            # Insert title text
            requests.append({
                'insertText': {
                    'objectId': title_box_id,
                    'text': title,
                    'insertionIndex': 0
                }
            })
            
            # Apply title style (white text, large, bold)
            title_style = self._get_text_style('content_title')
            title_style['foregroundColor'] = self._resolve_theme_color('HERO_TEXT')  # White
            requests.append({
                'updateTextStyle': {
                    'objectId': title_box_id,
                    'style': title_style,
                    'textRange': {'type': 'ALL'},
                    'fields': 'fontSize,fontFamily,bold,foregroundColor'
                }
            })
            
            # Center align text
            requests.append({
                'updateParagraphStyle': {
                    'objectId': title_box_id,
                    'style': {'alignment': 'CENTER'},
                    'textRange': {'type': 'ALL'},
                    'fields': 'alignment'
                }
            })
        
        return requests
    
    def _build_logo_replacement_requests(self, slide_id: str, slide_data: Dict[str, Any],
                                        report_dir: str) -> List[Dict[str, Any]]:
        """Step 2: Build logo replacement requests (BEFORE text replacement)."""
        requests = []
        
        # Get logo URL from config or environment
        logo_url = getattr(STIConfig, 'GOOGLE_LOGO_URL', None) or os.getenv('GOOGLE_LOGO_URL')
        
        if logo_url:
            token = '{{LOGO}}'
            requests.append({
                'replaceAllShapesWithImage': {
                    'containsText': {'text': token},
                    'imageUrl': logo_url,
                    'imageReplaceMethod': 'CENTER_INSIDE',
                    'pageObjectIds': [slide_id]
                }
            })
            # Track expected replacement
            self._expected_replacements[token] = 1
            logger.debug(f"Logo replacement added for slide {slide_id}")
        
        return requests
    
    def _build_hero_text_requests(self, slide_id: str, slide_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Step 4: Build text replacement requests for hero slide."""
        requests = []
        
        text_replacements = {
            '{{TITLE}}': slide_data.get('title', ''),
            '{{SUBTITLE}}': slide_data.get('subtitle', ''),
            '{{DATE}}': slide_data.get('date', '')
        }
        
        for placeholder, replacement in text_replacements.items():
            if replacement:
                requests.append({
                    'replaceAllText': {
                        'containsText': {'text': placeholder},
                        'replaceText': replacement,
                        'pageObjectIds': [slide_id]  # Scope to hero slide only
                    }
                })
                # Track expected replacement (1 occurrence per token)
                self._expected_replacements[placeholder] = 1
        
        return requests
    
    def _estimate_image_luminance(self, image_path: str) -> Optional[float]:
        """
        Estimate average luminance of an image (0.0-1.0).
        
        Uses PIL/Pillow to sample center pixel or small thumbnail.
        Returns None if PIL is not available or image can't be loaded.
        
        Args:
            image_path: Path to image file
        
        Returns:
            Luminance value (0.0-1.0) or None if unavailable
        """
        try:
            from PIL import Image
        except ImportError:
            logger.debug("PIL not available, skipping luminance estimation")
            return None
        
        try:
            img = Image.open(image_path)
            # Convert to RGB if needed
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Sample center pixel or small thumbnail for speed
            width, height = img.size
            center_x, center_y = width // 2, height // 2
            
            # Sample a small region around center (5x5 pixels)
            sample_size = 5
            x1 = max(0, center_x - sample_size // 2)
            y1 = max(0, center_y - sample_size // 2)
            x2 = min(width, center_x + sample_size // 2)
            y2 = min(height, center_y + sample_size // 2)
            
            region = img.crop((x1, y1, x2, y2))
            pixels = list(region.getdata())
            
            # Calculate average luminance using standard formula
            # Luminance = 0.299*R + 0.587*G + 0.114*B (normalized to 0-1)
            total_lum = sum(0.299 * r + 0.587 * g + 0.114 * b 
                          for r, g, b in pixels) / (255.0 * len(pixels))
            
            return total_lum
        except Exception as e:
            logger.debug(f"Could not estimate luminance for {image_path}: {e}")
            return None
    
    def _build_overlay_requests(self, slide_id: str, 
                                hero_image_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Step 6: Build overlay update requests for hero slide with luminance-aware opacity.
        
        Args:
            slide_id: Slide object ID
            hero_image_path: Optional path to hero image for luminance estimation
        """
        requests = []
        
        # Find overlay rectangle ID from discovered elements
        overlay_key = (slide_id, 'HERO_OVERLAY')
        overlay_id = getattr(self, '_template_elements', {}).get(overlay_key)
        
        if overlay_id:
            # Determine opacity based on luminance
            opacity = SlidesTemplateConfig.HERO_OVERLAY_OPACITY['mid']  # Default
            
            if hero_image_path:
                luminance = self._estimate_image_luminance(hero_image_path)
                if luminance is not None:
                    if luminance > 0.75:
                        opacity = SlidesTemplateConfig.HERO_OVERLAY_OPACITY['light']
                    elif luminance < 0.45:
                        opacity = SlidesTemplateConfig.HERO_OVERLAY_OPACITY['dark']
                    else:
                        opacity = SlidesTemplateConfig.HERO_OVERLAY_OPACITY['mid']
                    logger.debug(f"Hero image luminance: {luminance:.2f}, using opacity: {opacity:.2f}")
            
            requests.append({
                'updateShapeProperties': {
                    'objectId': overlay_id,
                    'shapeProperties': {
                        'shapeBackgroundFill': {
                            'solidFill': {
                                'color': self._resolve_theme_color('OVERLAY', for_shape_fill=True),
                                'alpha': opacity
                            }
                        }
                    },
                    'fields': 'shapeBackgroundFill.solidFill.color,shapeBackgroundFill.solidFill.alpha'
                }
            })
            logger.debug(f"Overlay update added for {overlay_id} with opacity {opacity}")
        else:
            logger.debug(f"No overlay rectangle found for slide {slide_id}")
        
        return requests
    
    def _build_hero_slide_requests(self, slide_id: str, slide_data: Dict[str, Any],
                                   report_dir: str) -> List[Dict[str, Any]]:
        """Legacy method - kept for backwards compatibility."""
        # This method is deprecated but kept for any code that might call it
        requests = []
        requests.extend(self._build_hero_background_requests(slide_id, slide_data, report_dir))
        requests.extend(self._build_logo_replacement_requests(slide_id, slide_data, report_dir))
        requests.extend(self._build_hero_text_requests(slide_id, slide_data))
        hero_image_path = slide_data.get('hero_image')
        if hero_image_path and report_dir:
            import os
            if not os.path.isabs(hero_image_path):
                hero_image_path = os.path.join(report_dir, hero_image_path)
        requests.extend(self._build_overlay_requests(slide_id, hero_image_path=hero_image_path))
        return requests
    
    def _build_collage_image_requests(self, slide_id: str, slide_data: Dict[str, Any],
                                      report_dir: str) -> List[Dict[str, Any]]:
        """Step 2: Build image replacement requests for collage slide (BEFORE text replacement)."""
        requests = []
        
        section_images = slide_data.get('section_images', [])
        for i, img_path in enumerate(section_images[:8], start=1):
            try:
                image_url = self._upload_image_to_drive(img_path, report_dir)
                if image_url:
                    token = f'{{{{IMG_{i}}}}}'
                    requests.append({
                        'replaceAllShapesWithImage': {
                            'containsText': {'text': token},
                            'imageUrl': image_url,
                            'imageReplaceMethod': 'CENTER_CROP',
                            'pageObjectIds': [slide_id]  # Scope to collage slide only
                        }
                    })
                    # Track expected replacement (1 occurrence per image)
                    self._expected_replacements[token] = 1
                else:
                    # Image upload failed - create placeholder
                    logger.warning(f"Image {img_path} failed to upload, using placeholder")
                    requests.extend(self._create_image_placeholder(slide_id, f'img_{i}_placeholder', i))
            except Exception as e:
                logger.warning(f"Image {img_path} failed to load: {e}, using placeholder")
                requests.extend(self._create_image_placeholder(slide_id, f'img_{i}_placeholder', i))
        
        return requests
    
    def _build_sticker_requests(self, slide_id: str, slide_data: Dict[str, Any],
                               report_dir: str) -> List[Dict[str, Any]]:
        """Step 3: Build sticker creation requests."""
        requests = []
        
        images_dir = Path(report_dir) / "images" if report_dir else None
        if images_dir and images_dir.exists():
            sticker_files = list(images_dir.glob("sticker_*.png"))
            if sticker_files:
                try:
                    sticker_url = self._upload_image_to_drive(str(sticker_files[0]), report_dir)
                    if sticker_url:
                        sticker_id = 'collage_sticker'
                        # Create sticker image
                        requests.append({
                            'createImage': {
                                'objectId': sticker_id,
                                'url': sticker_url,
                                'elementProperties': {
                                    'pageObjectId': slide_id,
                                    'size': {
                                        'width': {'magnitude': 1300000, 'unit': 'EMU'},
                                        'height': {'magnitude': 1300000, 'unit': 'EMU'}
                                    },
                                    'transform': {
                                        'scaleX': 1.0, 'scaleY': 1.0,
                                        'translateX': 4800000, 'translateY': 2800000,
                                        'unit': 'EMU'
                                    }
                                }
                            }
                        })
                        # Bring sticker to front
                        requests.append({
                            'updatePageElementsZOrder': {
                                'operation': 'BRING_TO_FRONT',
                                'pageElementObjectIds': [sticker_id]
                            }
                        })
                        logger.debug(f"Sticker creation and Z-order added for {sticker_id}")
                    else:
                        logger.warning(f"Sticker image failed to upload, skipping")
                except Exception as e:
                    logger.warning(f"Sticker image failed to load: {e}, skipping")
        
        return requests
    
    def _calculate_collage_grid_position(self, index: int, total_images: int, 
                                        slide_width: int = 9144000, 
                                        slide_height: int = 5143500) -> Dict[str, Any]:
        """
        Calculate deterministic grid position for collage images.
        
        Uses 2x2 (4 images) or 3x2 (6 images) grid with fixed gutters.
        
        Args:
            index: Image index (1-based)
            total_images: Total number of images
            slide_width: Slide width in EMU (default: 9144000 = 10in)
            slide_height: Slide height in EMU (default: 5143500 = 5.625in)
        
        Returns:
            Dict with 'x', 'y', 'width', 'height' in EMU
        """
        gutter_pt = 12  # 12pt gutter
        gutter_emu = int(gutter_pt * 12700)  # Convert PT to EMU
        
        # Determine grid layout
        if total_images <= 4:
            cols, rows = 2, 2
        else:
            cols, rows = 3, 2
        
        # Calculate cell dimensions
        usable_width = slide_width - (2 * int(SlidesTemplateConfig.BODY_MARGIN_LEFT * slide_width))
        usable_height = slide_height - (2 * int(SlidesTemplateConfig.BODY_MARGIN_LEFT * slide_height))
        
        cell_width = (usable_width - ((cols - 1) * gutter_emu)) // cols
        cell_height = (usable_height - ((rows - 1) * gutter_emu)) // rows
        
        # Calculate position (0-based index)
        col = (index - 1) % cols
        row = (index - 1) // cols
        
        x = int(SlidesTemplateConfig.BODY_MARGIN_LEFT * slide_width) + (col * (cell_width + gutter_emu))
        y = int(SlidesTemplateConfig.BODY_MARGIN_LEFT * slide_height) + (row * (cell_height + gutter_emu))
        
        return {
            'x': x,
            'y': y,
            'width': cell_width,
            'height': cell_height
        }
    
    def _create_image_placeholder(self, slide_id: str, placeholder_id: str, index: int) -> List[Dict[str, Any]]:
        """
        Create a placeholder shape when an image fails to load.
        
        Args:
            slide_id: Slide object ID
            placeholder_id: Unique ID for the placeholder
            index: Image index (for positioning)
        
        Returns:
            List of requests to create placeholder
        """
        # Get alternate fill color from config
        alt_color_obj = SlidesTemplateConfig.ALTERNATE_IMAGE_FILL_COLOR
        if alt_color_obj and alt_color_obj.rgb_fallback:
            fill_color = {'rgbColor': alt_color_obj.rgb_fallback}
        else:
            # Fallback to light gray
            fill_color = {'rgbColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9}}
        
        # Use deterministic grid positioning
        section_images = getattr(self, '_current_section_images', [])
        total_images = len(section_images)
        grid_pos = self._calculate_collage_grid_position(index, total_images)
        
        row = (index - 1) // 4
        col = (index - 1) % 4
        
        requests = [{
            'createShape': {
                'objectId': placeholder_id,
                'shapeType': 'RECTANGLE',
                'elementProperties': {
                    'pageObjectId': slide_id,
                    'size': {
                        'width': {'magnitude': 4000000, 'unit': 'EMU'},
                        'height': {'magnitude': 3000000, 'unit': 'EMU'}
                    },
                    'transform': {
                        'scaleX': 1.0, 'scaleY': 1.0,
                        'translateX': 2000000 + (col * 4500000),
                        'translateY': 2000000 + (row * 3200000),
                        'unit': 'EMU'
                    }
                }
            }
        }, {
            'updateShapeProperties': {
                'objectId': placeholder_id,
                'shapeProperties': {
                    'shapeBackgroundFill': {
                        'solidFill': {
                            'color': fill_color
                        }
                    }
                },
                'fields': 'shapeBackgroundFill.solidFill.color'
            }
        }, {
            'insertText': {
                'objectId': placeholder_id,
                'text': 'Image not available',
                'insertionIndex': 0
            }
        }, {
            'updateTextStyle': {
                'objectId': placeholder_id,
                'style': {
                    'fontSize': {'magnitude': 12, 'unit': 'PT'},
                    'foregroundColor': self._resolve_theme_color('SUBTLE_TEXT')
                },
                'textRange': {'type': 'ALL'},
                'fields': 'fontSize,foregroundColor'
            }
        }]
        return requests
    
    def _build_collage_text_requests(self, slide_id: str, slide_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Step 4: Build text replacement requests for collage slide."""
        requests = []
        
        big_word = slide_data.get('big_word', 'INTELLIGENCE')
        token = '{{BIGWORD}}'
        requests.append({
            'replaceAllText': {
                'containsText': {'text': token},
                'replaceText': big_word,
                'pageObjectIds': [slide_id]  # Scope to collage slide only
            }
        })
        # Track expected replacement
        self._expected_replacements[token] = 1
        
        return requests
    
    @staticmethod
    def _build_center_rotation_transform(cx: float, cy: float, theta_degrees: float, 
                                        unit: str = 'PT') -> Dict[str, Any]:
        """
        Build a center-rotation transform matrix (T₂·R·T₁).
        
        Computes transform about center point (cx, cy) rather than top-left corner.
        Returns an ABSOLUTE transform matrix that can be applied once.
        
        Args:
            cx: Center X coordinate (in specified unit)
            cy: Center Y coordinate (in specified unit)
            theta_degrees: Rotation angle in degrees (negative = clockwise)
            unit: Unit for coordinates ('PT' or 'EMU')
            
        Returns:
            Transform dict ready for updatePageElementTransform
        """
        theta_rad = math.radians(theta_degrees)
        cos_theta = math.cos(theta_rad)
        sin_theta = math.sin(theta_rad)
        
        # T₂·R·T₁: translate to origin, rotate, translate back
        # For affine transform in Slides API:
        # [scaleX*cos - scaleY*sin, translateX, scaleX*sin, scaleY*cos, translateY]
        # We compute the final translation that accounts for center rotation
        
        # Final translation accounts for center rotation
        # tx = cx - cx*cos + cy*sin, ty = cy - cx*sin - cy*cos
        translate_x = cx - (cx * cos_theta) + (cy * sin_theta)
        translate_y = cy - (cx * sin_theta) - (cy * cos_theta)
        
        return {
            'scaleX': cos_theta,
            'scaleY': cos_theta,
            'shearX': -sin_theta,
            'shearY': sin_theta,
            'translateX': translate_x,
            'translateY': translate_y,
            'unit': unit
        }
    
    def _get_element_center(self, element_id: str, presentation: Dict[str, Any]) -> Optional[Tuple[float, float, str]]:
        """
        Get the center point of an element for center-rotation calculations.
        
        Returns:
            Tuple of (cx, cy, unit) or None if element not found
        """
        if not hasattr(self, '_current_presentation'):
            return None
        
        slides = self._current_presentation.get('slides', [])
        for slide in slides:
            page_elements = slide.get('pageElements', [])
            for element in page_elements:
                if element.get('objectId') == element_id:
                    transform = element.get('transform', {})
                    size = element.get('size', {})
                    
                    # Get current position (handle dict or direct value)
                    tx_obj = transform.get('translateX', {})
                    ty_obj = transform.get('translateY', {})
                    tx = tx_obj.get('magnitude', 0) if isinstance(tx_obj, dict) else 0
                    ty = ty_obj.get('magnitude', 0) if isinstance(ty_obj, dict) else 0
                    unit = tx_obj.get('unit', 'EMU') if isinstance(tx_obj, dict) else 'EMU'
                    
                    # Get size (handle dict or direct value)
                    width_obj = size.get('width', {})
                    height_obj = size.get('height', {})
                    width = width_obj.get('magnitude', 0) if isinstance(width_obj, dict) else 0
                    height = height_obj.get('magnitude', 0) if isinstance(height_obj, dict) else 0
                    
                    # Guard: if size is zero or missing, can't calculate center
                    if width == 0 or height == 0:
                        logger.debug(f"Element {element_id} has zero/missing size, skipping center calculation")
                        return None
                    
                    # Calculate center
                    cx = tx + (width / 2.0)
                    cy = ty + (height / 2.0)
                    
                    return (cx, cy, unit)
        
        return None
    
    def _build_transform_requests(self, slide_id: str, slide_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Step 5: Build transform requests for angled BIGWORD with center rotation."""
        requests = []
        
        # Find BIGWORD text box ID from discovered elements (check both token and alt text)
        bigword_id = None
        template_elements = getattr(self, '_template_elements', {})
        
        # Try token first
        bigword_key = (slide_id, '{{BIGWORD}}')
        bigword_id = template_elements.get(bigword_key)
        
        # Fall back to alt text identifier
        if not bigword_id:
            bigword_key_alt = (slide_id, 'BIGWORD')
            bigword_id = template_elements.get(bigword_key_alt)
        
        if bigword_id:
            # Get element center for proper rotation
            center = self._get_element_center(bigword_id, self._current_presentation)
            
            if center:
                cx, cy, unit = center
                # Apply ~-12 degree rotation about center
                transform = self._build_center_rotation_transform(cx, cy, -12.0, unit)
                requests.append({
                    'updatePageElementTransform': {
                        'objectId': bigword_id,
                        'applyMode': 'ABSOLUTE',  # Use ABSOLUTE for computed center rotation
                        'transform': transform
                    }
                })
                logger.debug(f"Center rotation transform added for BIGWORD at {bigword_id}")
            else:
                # Fallback to relative transform if center calculation fails
                logger.warning(f"Could not calculate center for {bigword_id}, using relative transform")
                requests.append({
                    'updatePageElementTransform': {
                        'objectId': bigword_id,
                        'applyMode': 'RELATIVE',
                        'transform': {
                            'scaleX': 0.9781,
                            'scaleY': 0.9781,
                            'shearX': -0.2079,
                            'shearY': 0.2079,
                            'translateX': 0,
                            'translateY': 0,
                            'unit': 'PT'
                        }
                    }
                })
                logger.debug(f"Fallback transform added for BIGWORD at {bigword_id}")
        else:
            logger.warning(f"BIGWORD element not found for transform on slide {slide_id}")
        
        return requests
    
    def _build_collage_slide_requests(self, slide_id: str, slide_data: Dict[str, Any],
                                     report_dir: str, presentation: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Legacy method - kept for backwards compatibility."""
        # This method is deprecated but kept for any code that might call it
        requests = []
        requests.extend(self._build_collage_image_requests(slide_id, slide_data, report_dir))
        requests.extend(self._build_sticker_requests(slide_id, slide_data, report_dir))
        requests.extend(self._build_collage_text_requests(slide_id, slide_data))
        requests.extend(self._build_transform_requests(slide_id, slide_data))
        return requests
    
    def _build_content_text_requests(self, slide_id: str, slide_data: Dict[str, Any],
                                      slide_index: int) -> List[Dict[str, Any]]:
        """Step 4: Build text replacement requests for content slides."""
        requests = []
        
        sections = slide_data.get('sections', {})
        section_names = list(sections.keys())
        
        if slide_index < len(section_names):
            section_name = section_names[slide_index]
            section_text = sections[section_name]
            
            # Replace heading
            h1_token = '{{H1}}'
            requests.append({
                'replaceAllText': {
                    'containsText': {'text': h1_token},
                    'replaceText': section_name,
                    'pageObjectIds': [slide_id]  # Scope to this slide only
                }
            })
            self._expected_replacements[h1_token] = 1
            
            # Replace bullets (first 5 lines as bullets)
            lines = [line.strip() for line in section_text.split('\n') if line.strip()][:5]
            bullets_text = '\n'.join(lines)
            
            bullets_token = '{{BULLETS}}'
            requests.append({
                'replaceAllText': {
                    'containsText': {'text': bullets_token},
                    'replaceText': bullets_text,
                    'pageObjectIds': [slide_id]  # Scope to this slide only
                }
            })
            self._expected_replacements[bullets_token] = 1
        
        return requests
    
    def _build_content_styling_requests(self, slide_id: str, slide_data: Dict[str, Any],
                                       slide_index: int) -> List[Dict[str, Any]]:
        """Step 5: Build styling requests for content slides (bullets, text style, paragraph style)."""
        requests = []
        
        sections = slide_data.get('sections', {})
        section_names = list(sections.keys())
        
        if slide_index < len(section_names):
            # Find BULLETS text box ID from discovered elements
            bullets_key = (slide_id, '{{BULLETS}}')
            bullets_id = getattr(self, '_template_elements', {}).get(bullets_key)
            
            if bullets_id:
                # Apply bullet formatting
                requests.append({
                    'createParagraphBullets': {
                        'objectId': bullets_id,
                        'textRange': {'type': 'ALL'},
                        'bulletPreset': 'BULLET_DISC_CIRCLE_SQUARE'
                    }
                })
                
                # Apply text style (charcoal text for readability)
                body_style = self._get_text_style('body')
                requests.append({
                    'updateTextStyle': {
                        'objectId': bullets_id,
                        'style': {
                            'fontFamily': body_style.get('fontFamily', self._get_font_family('body')),
                            'fontSize': body_style.get('fontSize', {'magnitude': SlidesTemplateConfig.get_font_size('BODY'), 'unit': 'PT'}),
                            'foregroundColor': body_style.get('foregroundColor', self._resolve_theme_color('PRIMARY_TEXT'))
                        },
                        'textRange': {'type': 'ALL'},
                        'fields': 'fontFamily,fontSize,foregroundColor'
                    }
                })
                
                # Note: Accent color is applied via left rule, not on text
                # This maintains readability (charcoal text on ivory background)
                
                # Apply paragraph style with line spacing and proper indents
                body_para_style = self._get_paragraph_style(
                    alignment='START',
                    space_above=SlidesTemplateConfig.get_spacing('BULLET_ABOVE'),
                    space_below=SlidesTemplateConfig.get_spacing('BULLET_BELOW'),
                    indent_start=SlidesTemplateConfig.BULLET_INDENT_PRIMARY,  # 18-24pt for primary bullets
                    for_bullets=True  # Apply line spacing and spacing mode
                )
                # Build fields list, ensuring lineSpacing and spacingMode are included
                fields = list(body_para_style.keys())
                requests.append({
                    'updateParagraphStyle': {
                        'objectId': bullets_id,
                        'style': body_para_style,
                        'textRange': {'type': 'ALL'},
                        'fields': ','.join(fields)
                    }
                })
                
                logger.debug(f"Bullet styling added for {bullets_id}")
                
                # Add left accent rule for brand signature (keeps text charcoal, accent on rule)
                rule_requests = self._build_left_accent_rule(
                    bullets_id, slide_id, bullets_id
                )
                requests.extend(rule_requests)
            else:
                logger.warning(f"BULLETS element not found for styling on slide {slide_id}")
            
        return requests
    
    def _build_left_accent_rule(self, body_box_id: str, slide_id: str, 
                                element_id_for_bounds: str) -> List[Dict[str, Any]]:
        """
        Build requests to create a left accent rule beside body text boxes.
        
        This adds a brand signature (accent color) without compromising text readability.
        Text remains charcoal; accent appears only on the decorative rule.
        
        Args:
            body_box_id: ID of the body text box
            slide_id: Slide object ID
            element_id_for_bounds: Element ID to get bounds from (typically body_box_id)
        
        Returns:
            List of requests to create the accent rule
        """
        requests = []
        
        # Get element bounds to position rule correctly
        # We'll need to fetch the presentation to get element transform/size
        # For now, calculate based on config margins
        rule_width_pt = SlidesTemplateConfig.LEFT_RULE_WIDTH
        rule_gap_pt = SlidesTemplateConfig.LEFT_RULE_GAP
        
        # Convert PT to EMU (1 PT = 12,700 EMU)
        rule_width_emu = int(rule_width_pt * 12700)
        rule_gap_emu = int(rule_gap_pt * 12700)
        
        # Rule position: X = BODY_MARGIN_LEFT - rule_width - rule_gap
        # We'll calculate this from slide dimensions
        # For now, use approximate position based on margin
        # The rule will be positioned relative to body box after creation
        
        rule_id = f'left_rule_{body_box_id}'
        
        # Get accent color for fill
        accent_color = self._resolve_theme_color('ACCENT', for_shape_fill=True)
        
        # Create rule rectangle
        # Position will be refined after we get body box bounds
        # For template mode, we'll position it near the body box
        requests.append({
            'createShape': {
                'objectId': rule_id,
                'shapeType': 'RECTANGLE',
                'elementProperties': {
                    'pageObjectId': slide_id,
                    'size': {
                        'width': {'magnitude': rule_width_emu, 'unit': 'EMU'},
                        'height': {'magnitude': 4000000, 'unit': 'EMU'}  # Approximate, will be updated
                    },
                    'transform': {
                        'scaleX': 1.0, 'scaleY': 1.0,
                        'translateX': int(SlidesTemplateConfig.get_layout_dimension('MARGIN_LEFT_CONTENT') - rule_width_emu - rule_gap_emu),
                        'translateY': SlidesTemplateConfig.get_layout_dimension('MARGIN_TOP_CONTENT') + 900000,  # Match body box Y
                        'unit': 'EMU'
                    }
                }
            }
        })
        
        # Apply shape properties separately (fill color)
        # Note: Outline removal not supported via API, shape will have default outline
        requests.append({
            'updateShapeProperties': {
                'objectId': rule_id,
                'shapeProperties': {
                    'shapeBackgroundFill': {
                        'solidFill': {
                            'color': accent_color,
                            'alpha': 1.0
                        }
                    }
                },
                'fields': 'shapeBackgroundFill.solidFill.color,shapeBackgroundFill.solidFill.alpha'
            }
        })
        
        # Send rule to back so it sits behind text
        requests.append({
            'updatePageElementsZOrder': {
                'operation': 'SEND_TO_BACK',
                'pageElementObjectIds': [rule_id]
            }
        })
        
        logger.debug(f"Left accent rule added for {body_box_id}")
        return requests
    
    def _split_bullets_for_overflow(self, bullets: List[str]) -> List[List[str]]:
        """
        Split bullets into chunks if they exceed limits.
        
        Args:
            bullets: List of bullet strings
        
        Returns:
            List of bullet lists, each respecting MAX_BULLETS and MAX_BULLET_CHARS
        """
        max_bullets = SlidesTemplateConfig.MAX_BULLETS
        max_chars = SlidesTemplateConfig.MAX_BULLET_CHARS
        
        result = []
        current_chunk = []
        
        for bullet in bullets:
            # Check if bullet exceeds character limit
            if len(bullet) > max_chars:
                # Split long bullet at sentence boundaries
                sentences = bullet.split('. ')
                current_sentence = ''
                for sentence in sentences:
                    if not sentence.strip():
                        continue
                    if not sentence.endswith('.'):
                        sentence += '.'
                    
                    # If adding this sentence would exceed limit, start new chunk
                    potential = (current_sentence + ' ' + sentence).strip()
                    if len(potential) > max_chars and current_sentence:
                        if current_sentence:
                            current_chunk.append(current_sentence)
                            current_sentence = sentence
                        else:
                            # Single sentence is too long, truncate
                            current_chunk.append(sentence[:max_chars - 3] + '...')
                            current_sentence = ''
                    else:
                        current_sentence = potential
                
                if current_sentence:
                    if len(current_chunk) >= max_bullets:
                        result.append(current_chunk)
                        current_chunk = [current_sentence]
                    else:
                        current_chunk.append(current_sentence)
            else:
                # Normal bullet - check if we need to start new chunk
                if len(current_chunk) >= max_bullets:
                    result.append(current_chunk)
                    current_chunk = [bullet]
                else:
                    current_chunk.append(bullet)
        
        # Add remaining chunk
        if current_chunk:
            result.append(current_chunk)
        
        return result if result else [[]]
    
    def _build_content_slide_requests(self, slide_id: str, slide_data: Dict[str, Any],
                                      slide_index: int) -> List[Dict[str, Any]]:
        """Legacy method - kept for backwards compatibility."""
        # This method is deprecated but kept for any code that might call it
        requests = []
        requests.extend(self._build_content_text_requests(slide_id, slide_data, slide_index))
        requests.extend(self._build_content_styling_requests(slide_id, slide_data, slide_index))
        return requests
    
    def _build_delete_placeholder_requests(self, slide_id: str, is_first_slide: bool = False) -> List[Dict[str, Any]]:
        """
        Build requests to delete or clear default Google Slides placeholder elements.
        
        When creating slides from scratch, the first slide (index 0) that comes with a new
        presentation may have placeholder text boxes like "Click to add title" and 
        "Click to add subtitle". This method creates requests to remove them.
        
        Note: Only clears placeholders for the first slide, as blank slides created via
        API (BLANK layout) don't have these placeholders.
        
        Args:
            slide_id: The slide object ID
            is_first_slide: Whether this is the first slide (index 0) that came with the presentation
            
        Returns:
            List of delete/replace requests (empty if not first slide or no placeholders)
        """
        requests = []
        
        # Only clear placeholders for the first slide (index 0), which is the default slide
        # that comes with a new presentation. Blank slides created via API don't have placeholders.
        if not is_first_slide:
            return requests
        
        # Only include the most common Google Slides default placeholders
        # These appear in the default first slide of a new presentation
        common_placeholders = [
            'Click to add title',
            'Click to add subtitle',
        ]
        
        # Use replaceAllText to replace placeholder text with empty strings
        # This effectively clears the placeholder text
        # We scope to the specific slide to avoid affecting other slides
        for placeholder_text in common_placeholders:
            requests.append({
                'replaceAllText': {
                    'containsText': {'text': placeholder_text},
                    'replaceText': '',  # Empty string to clear placeholder
                    'pageObjectIds': [slide_id]  # Scope to this slide only
                }
            })
            logger.debug(f"🗑️ Added request to clear placeholder: '{placeholder_text}'")
        
        return requests
    
    def _build_hero_slide_requests_from_scratch(self, slide_id: str, slide_data: Dict[str, Any],
                                                report_dir: str) -> List[Dict[str, Any]]:
        """Build requests for hero slide when creating from scratch."""
        requests = []
        
        # Note: We don't clear placeholder text here because:
        # 1. Blank slides created via API may not have placeholders
        # 2. Our new text boxes will cover any existing placeholders
        # 3. replaceAllText fails if text doesn't exist, causing batch failure
        
        # Get actual slide dimensions for dynamic positioning
        slide_width, slide_height = self._get_slide_dimensions()
        
        # Set background image if hero image exists
        if slide_data.get('hero_image'):
            hero_image_url = self._upload_image_to_drive(slide_data['hero_image'], report_dir)
            if hero_image_url:
                requests.append({
                    'updatePageProperties': {
                        'objectId': slide_id,
                        'pageProperties': {
                            'pageBackgroundFill': {
                                'stretchedPictureFill': {
                                    'contentUrl': hero_image_url
                                }
                            }
                        },
                        'fields': 'pageBackgroundFill.stretchedPictureFill.contentUrl'
                    }
                })
        
        # Add semi-transparent black rectangle overlay (full slide)
        requests.append({
            'createShape': {
                'objectId': 'hero_overlay',
                'shapeType': 'RECTANGLE',
                'elementProperties': {
                    'pageObjectId': slide_id,
                    'size': {
                        'width': {'magnitude': slide_width, 'unit': 'EMU'},  # Full slide width
                        'height': {'magnitude': slide_height, 'unit': 'EMU'}  # Full slide height
                    },
                    'transform': {
                        'scaleX': 1.0, 'scaleY': 1.0,
                        'translateX': 0, 'translateY': 0,
                        'unit': 'EMU'
                    }
                }
            }
        })
        # Set overlay using color palette constant
        requests.append({
            'updateShapeProperties': {
                'objectId': 'hero_overlay',
                'shapeProperties': {
                    'shapeBackgroundFill': {
                        'solidFill': {
                            'color': self._resolve_theme_color('OVERLAY', for_shape_fill=True)
                        }
                    }
                },
                'fields': 'shapeBackgroundFill'
            }
        })
        # Move overlay behind text (send to back)
        requests.append({
            'updatePageElementsZOrder': {
                'pageElementObjectIds': ['hero_overlay'],
                'operation': 'SEND_TO_BACK'
            }
        })
        
        # Initialize positioning variables for sequential layout
        # Start at 30% from top to allow for top margin
        current_y = int(slide_height * 0.30)
        vertical_gap = 600000  # 600000 EMU = ~1.7cm spacing between elements
        
        # Create title text box (large, centered, better vertical positioning)
        title = slide_data.get('title', '')
        title_box_width = 7000000  # EMU
        title_box_height = 2000000  # EMU - increased to accommodate wrapping
        title_y = current_y
        
        if title:
            # Center horizontally
            title_x = (slide_width - title_box_width) // 2
            
            requests.append({
                'createShape': {
                    'objectId': 'hero_title',
                    'shapeType': 'TEXT_BOX',
                    'elementProperties': {
                        'pageObjectId': slide_id,
                        'size': {
                            'width': {'magnitude': title_box_width, 'unit': 'EMU'},
                            'height': {'magnitude': title_box_height, 'unit': 'EMU'}
                        },
                        'transform': {
                            'scaleX': 1.0, 'scaleY': 1.0,
                            'translateX': title_x,  # Dynamically calculated center
                            'translateY': title_y,  # Sequential positioning
                            'unit': 'EMU'
                        }
                    }
                }
            })
            
            # Note: Slide titles for accessibility are handled via the title text box content
            # Google Slides API doesn't support setting pageProperties.title programmatically
            requests.append({
                'insertText': {
                    'objectId': 'hero_title',
                    'text': title,
                    'insertionIndex': 0
                }
            })
            # Apply professional typography
            hero_title_style = self._get_text_style('hero_title')
            requests.append({
                'updateTextStyle': {
                    'objectId': 'hero_title',
                    'style': hero_title_style,
                    'textRange': {'type': 'ALL'},
                    'fields': 'fontSize,fontFamily,bold,foregroundColor'
                }
            })
            # Add paragraph styling for cinematic center alignment
            requests.append({
                'updateParagraphStyle': {
                    'objectId': 'hero_title',
                    'style': {
                        'alignment': 'CENTER'  # Cinematic center alignment
                    },
                    'textRange': {'type': 'ALL'},
                    'fields': 'alignment'
                }
            })
            # Update current_y for next element (title bottom + gap)
            current_y = title_y + title_box_height + vertical_gap
        else:
            # If no title, still advance position to maintain spacing
            current_y = title_y + vertical_gap
        
        # Create subtitle text box (better vertical spacing from title)
        subtitle = slide_data.get('subtitle', '')
        subtitle_box_width = 7500000  # EMU
        subtitle_box_height = 1500000  # EMU - increased to accommodate wrapping
        subtitle_y = current_y
        
        if subtitle:
            # Center horizontally
            subtitle_x = (slide_width - subtitle_box_width) // 2
            
            requests.append({
                'createShape': {
                    'objectId': 'hero_subtitle',
                    'shapeType': 'TEXT_BOX',
                    'elementProperties': {
                        'pageObjectId': slide_id,
                        'size': {
                            'width': {'magnitude': subtitle_box_width, 'unit': 'EMU'},
                            'height': {'magnitude': subtitle_box_height, 'unit': 'EMU'}
                        },
                        'transform': {
                            'scaleX': 1.0, 'scaleY': 1.0,
                            'translateX': subtitle_x,  # Dynamically calculated center
                            'translateY': subtitle_y,  # Sequential positioning below title
                            'unit': 'EMU'
                        }
                    }
                }
            })
            requests.append({
                'insertText': {
                    'objectId': 'hero_subtitle',
                    'text': subtitle,
                    'insertionIndex': 0
                }
            })
            # Apply professional typography
            hero_subtitle_style = self._get_text_style('hero_subtitle')
            requests.append({
                'updateTextStyle': {
                    'objectId': 'hero_subtitle',
                    'style': hero_subtitle_style,
                    'textRange': {'type': 'ALL'},
                    'fields': 'fontSize,fontFamily,foregroundColor'
                }
            })
            # Add paragraph styling for center alignment
            requests.append({
                'updateParagraphStyle': {
                    'objectId': 'hero_subtitle',
                    'style': {
                        'alignment': 'CENTER'
                    },
                    'textRange': {'type': 'ALL'},
                    'fields': 'alignment'
                }
            })
            # Update current_y for potential next elements
            current_y = subtitle_y + subtitle_box_height + vertical_gap
        
        # Create date text box (bottom right)
        date_str = slide_data.get('date', '')
        if date_str:
            date_box_width = 2000000  # EMU
            date_box_height = 400000  # EMU
            # Position at bottom right with margin
            margin = 500000  # 500000 EMU margin
            date_x = slide_width - date_box_width - margin
            date_y = slide_height - date_box_height - margin
            
            requests.append({
                'createShape': {
                    'objectId': 'hero_date',
                    'shapeType': 'TEXT_BOX',
                    'elementProperties': {
                        'pageObjectId': slide_id,
                        'size': {
                            'width': {'magnitude': date_box_width, 'unit': 'EMU'},
                            'height': {'magnitude': date_box_height, 'unit': 'EMU'}
                        },
                        'transform': {
                            'scaleX': 1.0, 'scaleY': 1.0,
                            'translateX': date_x,  # Bottom right with margin
                            'translateY': date_y,  # Bottom right with margin
                            'unit': 'EMU'
                        }
                    }
                }
            })
            requests.append({
                'insertText': {
                    'objectId': 'hero_date',
                    'text': date_str,
                    'insertionIndex': 0
                }
            })
            # Style date as subtle, smaller text
            date_style = self._get_text_style('meta')
            requests.append({
                'updateTextStyle': {
                    'objectId': 'hero_date',
                    'style': date_style,
                    'textRange': {'type': 'ALL'},
                    'fields': 'fontSize,fontFamily,foregroundColor'
                }
            })
            # Right-align date in bottom corner
            requests.append({
                'updateParagraphStyle': {
                    'objectId': 'hero_date',
                    'style': {
                        'alignment': 'END'  # END = right alignment in Slides API
                    },
                    'textRange': {'type': 'ALL'},
                    'fields': 'alignment'
                }
            })
        
        return requests
    
    def _build_collage_slide_requests_from_scratch(self, slide_id: str, slide_data: Dict[str, Any],
                                                   report_dir: str) -> List[Dict[str, Any]]:
        """Build requests for collage slide when creating from scratch."""
        requests = []
        
        # Note: Blank slides created via API don't have placeholders, so we skip clearing
        # Only the first slide (index 0) has default placeholders
        
        # Create image placeholders and populate with images
        section_images = slide_data.get('section_images', [])
        if section_images:
            # Create a grid of image shapes (2x4 layout)
            for i, img_path in enumerate(section_images[:8]):
                row = i // 4
                col = i % 4
                image_url = self._upload_image_to_drive(img_path, report_dir)
                if image_url:
                    shape_id = f'collage_img_{i+1}'
                    requests.append({
                        'createImage': {
                            'objectId': shape_id,
                            'url': image_url,
                            'elementProperties': {
                                'pageObjectId': slide_id,
                                'size': {
                                    'width': {'magnitude': 4000000, 'unit': 'EMU'},
                                    'height': {'magnitude': 3000000, 'unit': 'EMU'}
                                },
                                'transform': {
                                    'scaleX': 1.0, 'scaleY': 1.0,
                                    'translateX': 2000000 + (col * 4500000),
                                    'translateY': 2000000 + (row * 3200000),
                                    'unit': 'EMU'
                                }
                            }
                            # Note: imageReplaceMethod is only valid for replaceAllShapesWithImage, not createImage
                        }
                    })
        
        # Create big word text box (oversized)
        big_word = slide_data.get('big_word', 'INTELLIGENCE')
        bigword_id = 'collage_bigword'
        requests.append({
            'createShape': {
                'objectId': bigword_id,
                'shapeType': 'TEXT_BOX',
                'elementProperties': {
                    'pageObjectId': slide_id,
                    'size': {
                        'width': {'magnitude': 5000000, 'unit': 'EMU'},  # Larger for "oversized"
                        'height': {'magnitude': 1200000, 'unit': 'EMU'}
                    },
                    'transform': {
                        'scaleX': 1.0, 'scaleY': 1.0,
                        'translateX': 19000000, 'translateY': 5000000,
                        'unit': 'EMU'
                    }
                }
            }
        })
        requests.append({
            'insertText': {
                'objectId': bigword_id,
                'text': big_word,
                'insertionIndex': 0
            }
        })
        # Apply professional typography for big word
        bigword_style = self._get_text_style('bigword')
        requests.append({
            'updateTextStyle': {
                'objectId': bigword_id,
                'style': bigword_style,
                'textRange': {'type': 'ALL'},
                'fields': 'fontSize,fontFamily,bold,foregroundColor'
            }
        })
        
        # Apply angled transform (~12 degrees rotation)
        # Rotation matrix for ~12 degrees: cos(-12°) ≈ 0.9781, sin(-12°) ≈ -0.2079
        import math
        angle_rad = math.radians(-12)  # ~12 degrees rotation (negative for clockwise)
        cos_angle = math.cos(angle_rad)
        sin_angle = math.sin(angle_rad)
        
        requests.append({
            'updatePageElementTransform': {
                'objectId': bigword_id,
                'transform': {
                    'scaleX': 0.9781,  # Use exact spec values
                    'scaleY': 0.9781,
                    'shearX': -0.2079,
                    'shearY': 0.2079,
                    'translateX': 0,
                    'translateY': 0,
                    'unit': 'PT'  # Use PT for transforms per spec
                },
                'applyMode': 'RELATIVE'  # Apply relative to current transform
            }
        })
        
        # Add sticker image if available
        images_dir = Path(report_dir) / "images" if report_dir else None
        if images_dir and images_dir.exists():
            sticker_files = list(images_dir.glob("sticker_*.png"))
            if sticker_files:
                sticker_url = self._upload_image_to_drive(str(sticker_files[0]), report_dir)
                if sticker_url:
                    requests.append({
                        'createImage': {
                            'objectId': 'collage_sticker',
                            'url': sticker_url,
                            'elementProperties': {
                                'pageObjectId': slide_id,
                                'size': {
                                    'width': {'magnitude': 1000000, 'unit': 'EMU'},
                                    'height': {'magnitude': 1000000, 'unit': 'EMU'}
                                },
                                'transform': {
                                    'scaleX': 1.0, 'scaleY': 1.0,
                                    'translateX': 23000000, 'translateY': 2000000,
                                    'unit': 'EMU'
                                }
                            }
                        }
                    })
        
        return requests
    
    def _find_slide_elements(self, slide_id: str) -> Dict[str, str]:
        """Find existing elements in a slide (title, body text boxes)."""
        elements = {'title': None, 'body': None}
        
        if not hasattr(self, '_current_presentation'):
            return elements
        
        slides = self._current_presentation.get('slides', [])
        for slide in slides:
            if slide.get('objectId') == slide_id:
                page_elements = slide.get('pageElements', [])
                # TITLE_AND_BODY layout typically has title first, then body
                text_boxes = [
                    elem for elem in page_elements
                    if elem.get('shape') and elem.get('shape', {}).get('shapeType') == 'TEXT_BOX'
                ]
                
                # Sort by Y position (top to bottom)
                text_boxes.sort(key=lambda e: e.get('transform', {}).get('translateY', 0))
                
                if len(text_boxes) >= 1:
                    elements['title'] = text_boxes[0].get('objectId')
                if len(text_boxes) >= 2:
                    elements['body'] = text_boxes[1].get('objectId')
                
                break
        
        return elements
    
    def _apply_voice_rules(self, text: str, text_type: str = "body") -> str:
        """
        Apply voice and tone rules to text.
        
        Args:
            text: Input text
            text_type: Type of text ('title', 'heading', 'body', 'bullet')
            
        Returns:
            Processed text with voice rules applied
        """
        return SlidesContentMapper.apply_voice_rules(text, text_type)
    
    def _process_bullet_points(self, bullets: List[str]) -> List[str]:
        """
        Process bullet points for consistency.
        
        Args:
            bullets: List of bullet text strings
            
        Returns:
            Processed bullets with consistent formatting
        """
        return SlidesContentMapper.process_bullet_points(bullets)
    
    def _get_font_family(self, font_type: str = 'primary') -> str:
        """
        Get font family with fallback chain support.
        
        Args:
            font_type: 'primary', 'title', 'body', or 'meta'
        
        Returns:
            Font family name (first in fallback chain)
        
        Note:
            Google Slides API will default to Arial if font is not recognized.
            We prefer Google Fonts in the fallback chain to avoid this.
        """
        # Get font from config
        font = SlidesTemplateConfig.get_font_family(font_type)
        
        # Check if it's in the fallback chain (prefer first available)
        fallbacks = SlidesTemplateConfig.FONT_FALLBACKS
        if fallbacks and font not in fallbacks:
            # Use first fallback if configured font not in chain
            font = fallbacks[0]
            logger.warning(
                f"Font '{SlidesTemplateConfig.get_font_family(font_type)}' not in fallback chain, "
                f"using '{font}'. Consider adding via Google Fonts to the template."
            )
        
        # Log warning if using non-Google Font (API will default to Arial)
        # Common Google Fonts: Montserrat, Roboto, Lato, Open Sans, etc.
        # We can't truly detect if it's a Google Font, but we can warn about common non-Google fonts
        non_google_fonts = ['Arial', 'Times New Roman', 'Courier New', 'Helvetica']
        if font in non_google_fonts:
            logger.debug(
                f"Using font '{font}'. If this is not a Google Font, the API will default to Arial. "
                f"Consider using a Google Font from the fallback chain: {fallbacks}"
            )
        
        return font
    
    def _get_text_style(self, style_type: str, bold: bool = False) -> Dict[str, Any]:
        """
        Get standardized text style for consistent typography.
        
        Args:
            style_type: One of 'hero_title', 'hero_subtitle', 'content_title', 'body', 'meta', 'bigword'
            bold: Whether text should be bold (None to use config default)
        
        Returns:
            Dict with fontSize, fontFamily, bold, and foregroundColor
        """
        # Map style type to font type
        font_type_map = {
            'hero_title': 'title',
            'hero_subtitle': 'title',
            'content_title': 'title',
            'body': 'body',
            'meta': 'meta',
            'bigword': 'title'
        }
        font_type = font_type_map.get(style_type, 'primary')
        
        # Get font sizes from config
        size_map = {
            'hero_title': SlidesTemplateConfig.get_font_size('HERO_TITLE'),
            'hero_subtitle': SlidesTemplateConfig.get_font_size('HERO_SUBTITLE'),
            'content_title': SlidesTemplateConfig.get_font_size('CONTENT_TITLE'),
            'body': SlidesTemplateConfig.get_font_size('BODY'),
            'meta': SlidesTemplateConfig.get_font_size('META'),
            'bigword': 96  # Oversized for collage
        }
        
        # Get bold from config if not specified
        if bold is None:
            if style_type == 'hero_title' or style_type == 'content_title':
                bold = SlidesTemplateConfig.TITLE_BOLD
            else:
                bold = SlidesTemplateConfig.BODY_BOLD
        
        styles = {
            'hero_title': {
                'fontSize': {'magnitude': size_map['hero_title'], 'unit': 'PT'},
                'bold': bold,
                'foregroundColor': self._resolve_theme_color('HERO_TEXT')
            },
            'hero_subtitle': {
                'fontSize': {'magnitude': size_map['hero_subtitle'], 'unit': 'PT'},
                'bold': False,
                'italic': SlidesTemplateConfig.SUBTITLE_ITALIC,
                'foregroundColor': self._resolve_theme_color('HERO_TEXT')
            },
            'content_title': {
                'fontSize': {'magnitude': size_map['content_title'], 'unit': 'PT'},
                'bold': bold,
                'foregroundColor': self._resolve_theme_color('PRIMARY_TEXT')
            },
            'body': {
                'fontSize': {'magnitude': size_map['body'], 'unit': 'PT'},
                'bold': bold,
                'foregroundColor': self._resolve_theme_color('PRIMARY_TEXT')
            },
            'meta': {
                'fontSize': {'magnitude': size_map['meta'], 'unit': 'PT'},
                'bold': False,
                'foregroundColor': self._resolve_theme_color('DATE_TEXT')
            },
            'bigword': {
                'fontSize': {'magnitude': size_map['bigword'], 'unit': 'PT'},
                'bold': True,
                'foregroundColor': self._resolve_theme_color('PRIMARY_TEXT')
            }
        }
        
        style = styles.get(style_type, styles['body']).copy()
        
        # Add font family using fallback chain
        style['fontFamily'] = self._get_font_family(font_type)
        
        return style
    
    def _get_paragraph_style(self, alignment: str = 'START', 
                            space_above: Optional[int] = None,
                            space_below: Optional[int] = None,
                            indent_start: Optional[int] = None,
                            line_spacing: Optional[int] = None,
                            spacing_mode: Optional[str] = None,
                            for_bullets: bool = False) -> Dict[str, Any]:
        """
        Get standardized paragraph style for consistent spacing.
        
        Args:
            alignment: 'START', 'CENTER', 'END', or 'JUSTIFIED'
            space_above: Space above paragraph in PT
            space_below: Space below paragraph in PT
            indent_start: Indentation start in PT
            line_spacing: Line spacing percentage (e.g., 115 for 115%)
            spacing_mode: 'COLLAPSE_LISTS' for tight bullet lists
            for_bullets: If True, apply bullet-specific spacing defaults
        
        Returns:
            Dict with alignment, spacing, and line height properties
        """
        # Use config alignment if not specified
        if alignment == 'START':
            alignment = SlidesTemplateConfig.BODY_TEXT_ALIGNMENT
        
        style = {'alignment': alignment}
        
        # Apply line spacing from config if not specified
        if line_spacing is None and SlidesTemplateConfig.LINE_SPACING:
            style['lineSpacing'] = SlidesTemplateConfig.LINE_SPACING
        
        # Apply spacing mode for bullets
        if for_bullets and spacing_mode is None:
            spacing_mode = SlidesTemplateConfig.SPACING_MODE
        if spacing_mode:
            style['spacingMode'] = spacing_mode
        
        if space_above is not None:
            style['spaceAbove'] = {'magnitude': space_above, 'unit': 'PT'}
        if space_below is not None:
            style['spaceBelow'] = {'magnitude': space_below, 'unit': 'PT'}
        if indent_start is not None:
            style['indentStart'] = {'magnitude': indent_start, 'unit': 'PT'}
        
        return style
    
    def _build_content_slide_requests_from_scratch(self, slide_id: str, slide_data: Dict[str, Any],
                                                   slide_index: int) -> List[Dict[str, Any]]:
        """Build requests for content slides when creating from scratch."""
        requests = []
        
        sections = slide_data.get('sections', {})
        section_names = list(sections.keys())
        
        if slide_index < len(section_names):
            section_name = section_names[slide_index]
            section_text = sections[section_name]
            
            # Try to find existing text boxes in TITLE_AND_BODY layout
            existing_elements = self._find_slide_elements(slide_id)
            title_box_id = existing_elements.get('title')
            body_box_id = existing_elements.get('body')
            
            # Handle title
            if title_box_id:
                # Directly insert text - insertText works on empty boxes
                # If there's placeholder text, insertText will append, so we might get duplicates
                # But insertText at index 0 should insert at the beginning
                requests.append({
                    'insertText': {
                        'objectId': title_box_id,
                        'text': section_name,
                        'insertionIndex': 0
                    }
                })
                # Apply professional typography
                title_style = self._get_text_style('content_title')
                requests.append({
                    'updateTextStyle': {
                        'objectId': title_box_id,
                        'style': title_style,
                        'textRange': {'type': 'ALL'},
                        'fields': 'fontSize,fontFamily,bold,foregroundColor'
                    }
                })
                # Add paragraph styling with improved spacing
                title_para_style = self._get_paragraph_style(
                    alignment='START',
                    space_below=self.SPACING_TITLE_TO_BODY
                )
                requests.append({
                    'updateParagraphStyle': {
                        'objectId': title_box_id,
                        'style': title_para_style,
                        'textRange': {'type': 'ALL'},
                        'fields': ','.join(title_para_style.keys())
                    }
                })
                
                # Note: Slide titles for accessibility are handled via the title text box content
                # The section_name text box serves as the accessible slide title
            else:
                # Fallback: create new title text box
                title_box_id = f'content_title_{slide_index}'
                requests.append({
                    'createShape': {
                        'objectId': title_box_id,
                        'shapeType': 'TEXT_BOX',
                        'elementProperties': {
                            'pageObjectId': slide_id,
                            'size': {
                                'width': {'magnitude': 8000000, 'unit': 'EMU'},
                                'height': {'magnitude': 1000000, 'unit': 'EMU'}
                            },
                            'transform': {
                                'scaleX': 1.0, 'scaleY': 1.0,
                                'translateX': self.MARGIN_LEFT_CONTENT, 'translateY': self.MARGIN_TOP_CONTENT,
                                'unit': 'EMU'
                            }
                        }
                    }
                })
                requests.append({
                    'insertText': {
                        'objectId': title_box_id,
                        'text': section_name,
                        'insertionIndex': 0
                    }
                })
                # Apply professional typography
                title_style = self._get_text_style('content_title')
                requests.append({
                    'updateTextStyle': {
                        'objectId': title_box_id,
                        'style': title_style,
                        'textRange': {'type': 'ALL'},
                        'fields': 'fontSize,fontFamily,bold,foregroundColor'
                    }
                })
                # Add paragraph styling with improved spacing
                title_para_style = self._get_paragraph_style(
                    alignment='START',
                    space_below=self.SPACING_TITLE_TO_BODY
                )
                requests.append({
                    'updateParagraphStyle': {
                        'objectId': title_box_id,
                        'style': title_para_style,
                        'textRange': {'type': 'ALL'},
                        'fields': ','.join(title_para_style.keys())
                    }
                })
                
                # Note: Slide titles for accessibility are handled via the title text box content
                # The section_name text box serves as the accessible slide title
            
            # Handle body text with bullets
            lines = [line.strip() for line in section_text.split('\n') if line.strip()][:5]
            bullets_text = '\n'.join(lines)  # No manual bullet characters
            
            if body_box_id:
                # Use existing body text box
                # Directly insert text - insertText works on empty boxes
                # Note: If box has placeholder text, insertText will append after it
                # But since TITLE_AND_BODY layouts typically have empty body boxes, this should work
                requests.append({
                    'insertText': {
                        'objectId': body_box_id,
                        'text': bullets_text,
                        'insertionIndex': 0
                    }
                })
                # Apply bullet formatting using createParagraphBullets
                # Need to create bullet markers for each line
                requests.append({
                    'createParagraphBullets': {
                        'objectId': body_box_id,
                        'textRange': {'type': 'ALL'},
                        'bulletPreset': 'BULLET_DISC_CIRCLE_SQUARE'
                    }
                })
                # Apply professional typography
                body_style = self._get_text_style('body')
                requests.append({
                    'updateTextStyle': {
                        'objectId': body_box_id,
                        'style': body_style,
                        'textRange': {'type': 'ALL'},
                        'fields': 'fontSize,fontFamily,foregroundColor'
                    }
                })
                # Add paragraph styling with improved spacing and line height
                body_para_style = self._get_paragraph_style(
                    alignment='START',
                    space_above=SlidesTemplateConfig.get_spacing('BULLET_ABOVE'),
                    space_below=SlidesTemplateConfig.get_spacing('BULLET_BELOW'),
                    indent_start=SlidesTemplateConfig.BULLET_INDENT_PRIMARY,
                    for_bullets=True  # Apply line spacing and spacing mode
                )
                fields = list(body_para_style.keys())
                requests.append({
                    'updateParagraphStyle': {
                        'objectId': body_box_id,
                        'style': body_para_style,
                        'textRange': {'type': 'ALL'},
                        'fields': ','.join(fields)
                    }
                })
                
                # Add left accent rule for brand signature
                rule_requests = self._build_left_accent_rule(
                    body_box_id, slide_id, body_box_id
                )
                requests.extend(rule_requests)
            else:
                # Fallback: create new body text box
                body_box_id = f'content_body_{slide_index}'
                requests.append({
                    'createShape': {
                        'objectId': body_box_id,
                        'shapeType': 'TEXT_BOX',
                        'elementProperties': {
                            'pageObjectId': slide_id,
                            'size': {
                                'width': {'magnitude': self.MAX_WIDTH_BODY, 'unit': 'EMU'},
                                'height': {'magnitude': 8000000, 'unit': 'EMU'}
                            },
                            'transform': {
                                'scaleX': 1.0, 'scaleY': 1.0,
                                'translateX': self.MARGIN_LEFT_CONTENT, 'translateY': self.MARGIN_TOP_CONTENT + 900000,  # Below title
                                'unit': 'EMU'
                            }
                        }
                    }
                })
                requests.append({
                    'insertText': {
                        'objectId': body_box_id,
                        'text': bullets_text,
                        'insertionIndex': 0
                    }
                })
                # Apply bullet formatting
                requests.append({
                    'createParagraphBullets': {
                        'objectId': body_box_id,
                        'textRange': {'type': 'ALL'},
                        'bulletPreset': 'BULLET_DISC_CIRCLE_SQUARE'
                    }
                })
                # Apply professional typography
                body_style = self._get_text_style('body')
                requests.append({
                    'updateTextStyle': {
                        'objectId': body_box_id,
                        'style': body_style,
                        'textRange': {'type': 'ALL'},
                        'fields': 'fontSize,fontFamily,foregroundColor'
                    }
                })
                # Add paragraph styling with improved spacing and line height
                body_para_style = self._get_paragraph_style(
                    alignment='START',
                    space_above=SlidesTemplateConfig.get_spacing('BULLET_ABOVE'),
                    space_below=SlidesTemplateConfig.get_spacing('BULLET_BELOW'),
                    indent_start=SlidesTemplateConfig.BULLET_INDENT_PRIMARY,
                    for_bullets=True  # Apply line spacing and spacing mode
                )
                fields = list(body_para_style.keys())
                requests.append({
                    'updateParagraphStyle': {
                        'objectId': body_box_id,
                        'style': body_para_style,
                        'textRange': {'type': 'ALL'},
                        'fields': ','.join(fields)
                    }
                })
        
        return requests
    
    def _get_image_hash(self, image_path: str) -> Optional[str]:
        """Calculate SHA-1 hash of image file for caching."""
        try:
            with open(image_path, 'rb') as f:
                file_hash = hashlib.sha1(f.read()).hexdigest()
            return file_hash
        except Exception as e:
            logger.debug(f"Could not hash image {image_path}: {e}")
            return None
    
    def _upload_image_to_drive(self, image_path: str, report_dir: str) -> Optional[str]:
        """
        Upload image to Google Drive and return public URL.
        
        Uses SHA-1 hashing to cache uploads and avoid re-uploading duplicate images.
        Validates MIME type and handles stale cache entries (404s).
        """
        # Validate file exists and check MIME type
        if not os.path.exists(image_path):
            logger.warning(f"Image file not found: {image_path}")
            return None
        
        file_ext = os.path.splitext(image_path)[1].lower()
        valid_extensions = {'.png', '.jpg', '.jpeg', '.gif'}
        if file_ext not in valid_extensions:
            logger.warning(f"Unsupported image format: {file_ext} (expected PNG/JPEG/GIF)")
            return None
        
        # Check cache first (stored in report_dir)
        cache_file = os.path.join(report_dir, '.image_cache.json')
        image_cache = {}
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    image_cache = json.load(f)
            except Exception:
                pass
        
        # Calculate hash
        file_hash = self._get_image_hash(image_path)
        if file_hash and file_hash in image_cache:
            cached_entry = image_cache[file_hash]
            cached_url = cached_entry.get('url')
            cached_mime = cached_entry.get('mimeType', 'image/png')
            file_size = cached_entry.get('fileSize')
            
            # Validate cache entry matches current file
            current_size = os.path.getsize(image_path)
            if cached_mime == 'image/png' and cached_url and (file_size is None or file_size == current_size):
                # Check if cached Drive file still exists (basic validation)
                # Note: Full 404 check would require API call; we'll handle that on failure
                logger.debug(f"✅ Using cached image URL for {os.path.basename(image_path)}")
                return cached_url
        
        # Upload new image
        
        try:
            file_metadata = {
                'name': os.path.basename(image_path),
                'mimeType': 'image/png'
            }
            
            if STIConfig.GOOGLE_DRIVE_FOLDER_ID:
                file_metadata['parents'] = [STIConfig.GOOGLE_DRIVE_FOLDER_ID]
            
            media = MediaFileUpload(image_path, mimetype='image/png', resumable=True)
            
            # Check if folder is in a Shared Drive
            drive_params = {'supportsAllDrives': True}
            if STIConfig.GOOGLE_DRIVE_FOLDER_ID:
                folder_info = self._get_folder_drive_info(STIConfig.GOOGLE_DRIVE_FOLDER_ID)
                if folder_info:
                    drive_params['driveId'] = folder_info['driveId']
            
            file = self.drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink',
                **drive_params
            ).execute()
            
            # Make file publicly viewable
            self.drive_service.permissions().create(
                fileId=file['id'],
                body={'role': 'reader', 'type': 'anyone'},
                supportsAllDrives=True
            ).execute()
            
            # Get direct image URL
            image_url = f"https://drive.google.com/uc?export=view&id={file['id']}"
            logger.info(f"✅ Uploaded image to Drive: {image_url}")
            
            # Cache the upload
            if file_hash:
                if file_hash not in image_cache:
                    image_cache[file_hash] = {}
                image_cache[file_hash]['url'] = image_url
                image_cache[file_hash]['drive_id'] = file['id']
                image_cache[file_hash]['path'] = image_path
                image_cache[file_hash]['mimeType'] = 'image/png'  # Track MIME type
                image_cache[file_hash]['fileSize'] = os.path.getsize(image_path)
                
                # Save cache
                try:
                    with open(cache_file, 'w') as f:
                        json.dump(image_cache, f, indent=2)
                    logger.debug(f"💾 Cached image: {os.path.basename(image_path)}")
                except Exception as cache_err:
                    logger.debug(f"Could not save image cache: {cache_err}")
            
            return image_url
            
        except HttpError as e:
            # If cached URL returned 404, clear cache entry and try again
            if e.resp.status == 404 and file_hash and file_hash in image_cache:
                logger.debug(f"⚠️ Cached Drive file returned 404, clearing cache entry")
                del image_cache[file_hash]
                try:
                    with open(cache_file, 'w') as f:
                        json.dump(image_cache, f, indent=2)
                except Exception:
                    pass
            logger.warning(f"⚠️ Failed to upload image to Drive: {e}")
            return None
        except Exception as e:
            logger.warning(f"⚠️ Failed to upload image to Drive: {e}")
            # Fallback: return None (will skip image insertion)
            return None
    
    def _export_pdf(self, presentation_id: str, report_dir: str) -> Optional[str]:
        """Export presentation as PDF and save to report directory."""
        try:
            request = self.drive_service.files().export_media(
                fileId=presentation_id,
                mimeType='application/pdf'
            )
            # Note: export_media doesn't support supportsAllDrives parameter
            # But we can ensure access via permissions
            
            pdf_path = os.path.join(report_dir, 'slides_export.pdf')
            with open(pdf_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        logger.debug(f"Download progress: {int(status.progress() * 100)}%")
            
            file_size = os.path.getsize(pdf_path)
            logger.info(f"✅ Exported PDF: {pdf_path} ({file_size / 1024 / 1024:.2f} MB)")
            
            # Check 10MB limit
            if file_size > 10 * 1024 * 1024:
                logger.warning(f"⚠️ PDF export exceeds 10MB limit: {file_size / 1024 / 1024:.2f} MB")
            
            return pdf_path
            
        except Exception as e:
            logger.error(f"❌ Failed to export PDF: {e}")
            return None
    
    def _save_outputs(self, report_dir: str, slides_url: str, pdf_path: Optional[str], 
                     qa_passed: bool = True):
        """
        Save slide URLs and update metadata.
        
        Args:
            report_dir: Report directory path
            slides_url: Google Slides URL
            pdf_path: Path to exported PDF
            qa_passed: If False, don't write slides_url.txt (non-publishable)
        """
        try:
            # Save slides URL only if QA passed
            if qa_passed:
                url_file = os.path.join(report_dir, 'slides_url.txt')
                with open(url_file, 'w') as f:
                    f.write(slides_url)
                logger.info(f"💾 Saved slides URL: {url_file}")
            else:
                logger.warning(
                    f"⚠️ Skipping slides_url.txt (QA failed - non-publishable). "
                    f"Slides available at: {slides_url}"
                )
            
            # Update metadata.json
            metadata_file = os.path.join(report_dir, 'metadata.json')
            if os.path.exists(metadata_file):
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                
                metadata['slides'] = {
                    'generated': True,
                    'slides_url': slides_url,
                    'pdf_path': pdf_path,
                    'generation_timestamp': datetime.now().isoformat()
                }
                
                with open(metadata_file, 'w') as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)
                logger.info(f"💾 Updated metadata with slides info")
            
        except Exception as e:
            logger.error(f"❌ Error saving slide outputs: {e}")
    
    def _log_batch_requests_summary(self, requests: List[Dict[str, Any]]):
        """Log a summary of batch update requests for debugging."""
        request_types = {}
        for req in requests:
            req_type = list(req.keys())[0] if req else 'unknown'
            request_types[req_type] = request_types.get(req_type, 0) + 1
        
        logger.debug(f"📋 Batch requests summary:")
        for req_type, count in sorted(request_types.items()):
            logger.debug(f"   {req_type}: {count}")
        
        # Log detailed info for key operations
        for i, req in enumerate(requests[:10]):  # Log first 10 in detail
            req_type = list(req.keys())[0] if req else 'unknown'
            if req_type in ['createShape', 'insertText', 'createImage', 'replaceAllText']:
                logger.debug(f"   Request {i+1}: {req_type} - {json.dumps(req.get(req_type, {}), indent=6, default=str)[:200]}")
    
    def _log_batch_response(self, response: Dict[str, Any], expected_count: int):
        """Log batch update response details for debugging."""
        replies = response.get('replies', [])
        logger.debug(f"📥 Batch response: {len(replies)} replies (expected {expected_count})")
        
        created_elements = []
        for i, reply in enumerate(replies):
            if 'createImage' in reply:
                obj_id = reply['createImage'].get('objectId')
                created_elements.append(('createImage', obj_id))
                logger.debug(f"   Reply {i+1}: Created image with ID: {obj_id}")
            elif 'createShape' in reply:
                obj_id = reply['createShape'].get('objectId')
                created_elements.append(('createShape', obj_id))
                logger.debug(f"   Reply {i+1}: Created shape with ID: {obj_id}")
            elif 'insertText' in reply:
                result = reply.get('insertText', {})
                logger.debug(f"   Reply {i+1}: Inserted text - result: {result}")
                if not result:
                    logger.warning(f"   Reply {i+1}: insertText returned empty result")
            elif 'replaceAllText' in reply:
                occurrences_changed = reply['replaceAllText'].get('occurrencesChanged', 0)
                logger.debug(f"   Reply {i+1}: Replaced text - {occurrences_changed} occurrences changed")
            elif 'updateTextStyle' in reply:
                logger.debug(f"   Reply {i+1}: Updated text style")
            elif 'createParagraphBullets' in reply:
                logger.debug(f"   Reply {i+1}: Created paragraph bullets")
            elif 'updatePageElementTransform' in reply:
                logger.debug(f"   Reply {i+1}: Updated element transform")
            else:
                reply_keys = list(reply.keys())
                if reply_keys:
                    logger.debug(f"   Reply {i+1}: {reply_keys[0]}")
        
        if len(replies) < expected_count:
            logger.warning(f"⚠️ Expected {expected_count} replies but got {len(replies)}")
    
    def _inspect_batch_replies(self, response: Dict[str, Any]):
        """
        Inspect batch update replies and assert token replacement counts.
        
        Correlates requests to replies by order to validate expected occurrencesChanged
        per token. Catches missing placeholders early.
        """
        replies = response.get('replies', [])
        expected = getattr(self, '_expected_replacements', {})
        last_requests = getattr(self, '_last_requests', [])
        
        mismatches = []
        total_replacements = 0
        
        # Correlate requests to replies by order
        for req, rep in zip(last_requests or [], replies):
            if 'replaceAllText' in req:
                token = req['replaceAllText'].get('containsText', {}).get('text', '')
                got = rep.get('replaceAllText', {}).get('occurrencesChanged', 0)
                exp = expected.get(token)
                
                total_replacements += got
                
                if exp is not None and got != exp:
                    mismatches.append(
                        f"Token '{token}': expected {exp}, got {got}"
                    )
                elif got == 0 and exp is None:
                    # Unexpected zero-match (might be valid, just log)
                    logger.debug(f"Token '{token}': 0 occurrences (not tracked)")
            
            elif 'replaceAllShapesWithImage' in req:
                token = req['replaceAllShapesWithImage'].get('containsText', {}).get('text', '')
                got = rep.get('replaceAllShapesWithImage', {}).get('occurrencesChanged', 0)
                exp = expected.get(token)
                
                total_replacements += got
                
                if exp is not None and got != exp:
                    mismatches.append(
                        f"Image token '{token}': expected {exp}, got {got}"
                    )
                elif got == 0 and exp is None:
                    logger.debug(f"Image token '{token}': 0 occurrences (not tracked)")
        
        if mismatches:
            logger.warning(f"⚠️ Found {len(mismatches)} token replacement mismatch(es):")
            for mismatch in mismatches:
                logger.warning(f"   - {mismatch}")
            logger.warning(f"   This may indicate missing tokens in template")
        else:
            logger.debug(f"✅ All tracked token replacements matched expected counts")
        
        # Log summary
        logger.debug(f"✅ Total replacements: {total_replacements} (tracked {len(expected)} token(s))")
    
    def _validate_slides(self, presentation: Dict[str, Any], slide_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate that slides were created and populated correctly.
        
        Returns:
            Dict with 'success' (bool) and 'issues' (list of strings)
        """
        issues = []
        slides = presentation.get('slides', [])
        
        if not slides:
            issues.append("No slides found in presentation")
            return {'success': False, 'issues': issues}
        
        logger.info(f"🔍 Validating {len(slides)} slide(s)...")
        
        # Validate each slide
        for slide_idx, slide in enumerate(slides):
            slide_id = slide.get('objectId')
            page_elements = slide.get('pageElements', [])
            
            logger.debug(f"   Slide {slide_idx + 1} ({slide_id}): {len(page_elements)} elements")
            
            # Check for text content
            has_text = False
            text_content = []
            
            for elem in page_elements:
                elem_type = elem.get('shape') and 'TEXT_BOX' or (elem.get('image') and 'IMAGE' or 'OTHER')
                
                # Check for text in shapes
                if elem.get('shape') and elem['shape'].get('shapeType') == 'TEXT_BOX':
                    shape = elem['shape']
                    text_elements = shape.get('text', {}).get('textElements', [])
                    full_text = ''
                    for text_elem in text_elements:
                        if 'textRun' in text_elem:
                            full_text += text_elem['textRun'].get('content', '')
                    
                    # Log ALL text found (for debugging)
                    elem_id = elem.get('objectId', 'unknown')
                    logger.debug(f"      Text box {elem_id}: '{full_text[:100]}'")
                    
                    # Filter out placeholder text
                    placeholder_texts = [
                        'Click to add title',
                        'Click to add subtitle', 
                        'Click to add notes',
                        'Click to edit Master title style'
                    ]
                    text = full_text.strip()
                    if text and not any(ph.lower() in text.lower() for ph in placeholder_texts):
                        has_text = True
                        text_content.append(text[:50])
                        logger.debug(f"      ✓ Valid text: {text[:50]}...")
                    elif text:
                        logger.debug(f"      ✗ Placeholder text (filtered): {text[:50]}...")
                    else:
                        logger.debug(f"      ○ Text box is empty")
                
                # Check for images
                if elem.get('image'):
                    image_url = elem['image'].get('contentUrl', '')
                    source_url = elem['image'].get('sourceUrl', '')
                    logger.debug(f"      Found image: {source_url or image_url[:50]}...")
            
            # Hero slide (first slide) should have title, subtitle, date
            if slide_idx == 0:
                expected_texts = [
                    slide_data.get('title', ''),
                    slide_data.get('subtitle', ''),
                    slide_data.get('date', '')
                ]
                expected_texts = [t for t in expected_texts if t]
                
                if not has_text and expected_texts:
                    issues.append(f"Slide 1 (hero): Expected text but found none")
                elif expected_texts:
                    found_any = any(any(exp.lower() in txt.lower() for txt in text_content) for exp in expected_texts if exp)
                    if not found_any:
                        issues.append(f"Slide 1 (hero): Expected text like '{expected_texts[0][:30]}...' but found: {text_content[:3]}")
            
            # Content slides should have heading and bullets
            elif slide_idx >= 2:
                if not has_text:
                    issues.append(f"Slide {slide_idx + 1} (content): No text content found")
                elif len(text_content) < 1:
                    issues.append(f"Slide {slide_idx + 1} (content): Very little text content")
            
            # Log element summary
            element_types = {}
            for elem in page_elements:
                if elem.get('shape'):
                    shape_type = elem['shape'].get('shapeType', 'UNKNOWN')
                    element_types[shape_type] = element_types.get(shape_type, 0) + 1
                elif elem.get('image'):
                    element_types['IMAGE'] = element_types.get('IMAGE', 0) + 1
                else:
                    element_types['OTHER'] = element_types.get('OTHER', 0) + 1
            
            logger.debug(f"      Element types: {element_types}")
        
        # Overall validation
        if issues:
            logger.warning(f"⚠️ Validation found {len(issues)} issue(s):")
            for issue in issues:
                logger.warning(f"   - {issue}")
            return {'success': False, 'issues': issues}
        else:
            logger.info(f"✅ Validation passed: All slides have expected content")
            return {'success': True, 'issues': []}

