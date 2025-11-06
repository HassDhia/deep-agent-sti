#!/usr/bin/env python3
"""
Template Validation Script for Google Slides

This script validates that your Google Slides template has all required placeholders.
Run this after creating your template to ensure it's ready for use.
"""

import os
import sys

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    print("❌ Google API libraries not installed")
    sys.exit(1)

from config import STIConfig

# Required placeholders by slide type
REQUIRED_PLACEHOLDERS = {
    'hero': ['{{TITLE}}', '{{SUBTITLE}}', '{{DATE}}'],
    'collage': ['{{IMG_1}}', '{{IMG_2}}', '{{IMG_3}}', '{{IMG_4}}', 
                '{{IMG_5}}', '{{IMG_6}}', '{{IMG_7}}', '{{IMG_8}}', '{{BIGWORD}}'],
    'content': ['{{H1}}', '{{BULLETS}}']
}

OPTIONAL_PLACEHOLDERS = ['{{LOGO}}', '{{STICKER}}', '{{QUOTE}}']

def validate_template(template_id: str):
    """Validate that template has all required placeholders"""
    print(f"🔍 Validating template: {template_id}")
    print("=" * 70)
    
    # Load credentials
    creds_path = STIConfig.GOOGLE_CREDENTIALS_PATH or os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    if not creds_path or not os.path.exists(creds_path):
        print("❌ Credentials file not found")
        return False
    
    try:
        creds = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes=['https://www.googleapis.com/auth/presentations.readonly']
        )
        slides_service = build('slides', 'v1', credentials=creds)
        
        # Get presentation
        presentation = slides_service.presentations().get(
            presentationId=template_id
        ).execute()
        
        slides = presentation.get('slides', [])
        print(f"✅ Found {len(slides)} slide(s) in template")
        
        if len(slides) < 2:
            print("⚠️  Warning: Template should have at least 2 slides (hero + collage)")
        
        # Extract all text from presentation
        all_text = ""
        found_placeholders = set()
        
        for i, slide in enumerate(slides, 1):
            print(f"\n📄 Slide {i}:")
            
            # Check page elements for text
            page_elements = slide.get('pageElements', [])
            slide_text = ""
            
            for element in page_elements:
                # Check shape text
                shape = element.get('shape', {})
                if shape:
                    text_elements = shape.get('text', {}).get('textElements', [])
                    for text_elem in text_elements:
                        if 'textRun' in text_elem:
                            text = text_elem['textRun'].get('content', '')
                            slide_text += text
                            all_text += text
                
                # Check table text
                table = element.get('table', {})
                if table:
                    rows = table.get('tableRows', [])
                    for row in rows:
                        cells = row.get('tableCells', [])
                        for cell in cells:
                            cell_text = cell.get('text', {}).get('textElements', [])
                            for text_elem in cell_text:
                                if 'textRun' in text_elem:
                                    text = text_elem['textRun'].get('content', '')
                                    slide_text += text
                                    all_text += text
            
            # Find placeholders in this slide
            for placeholder in REQUIRED_PLACEHOLDERS.get('hero', []) + \
                             REQUIRED_PLACEHOLDERS.get('collage', []) + \
                             REQUIRED_PLACEHOLDERS.get('content', []) + \
                             OPTIONAL_PLACEHOLDERS:
                if placeholder in slide_text:
                    found_placeholders.add(placeholder)
                    if i == 1:  # Hero slide
                        if placeholder in REQUIRED_PLACEHOLDERS.get('hero', []) or placeholder == '{{LOGO}}':
                            print(f"   ✅ {placeholder}")
                    elif i == 2:  # Collage slide
                        if placeholder in REQUIRED_PLACEHOLDERS.get('collage', []) or placeholder == '{{STICKER}}':
                            print(f"   ✅ {placeholder}")
                    else:  # Content slides
                        if placeholder in REQUIRED_PLACEHOLDERS.get('content', []):
                            print(f"   ✅ {placeholder}")
        
        # Validate required placeholders
        print("\n" + "=" * 70)
        print("📋 Validation Summary:")
        print("=" * 70)
        
        all_required = []
        for category in REQUIRED_PLACEHOLDERS.values():
            all_required.extend(category)
        
        missing = []
        for placeholder in all_required:
            if placeholder not in found_placeholders:
                missing.append(placeholder)
            else:
                print(f"✅ {placeholder}")
        
        if missing:
            print(f"\n❌ Missing {len(missing)} required placeholder(s):")
            for placeholder in missing:
                print(f"   - {placeholder}")
        
        # Check optional
        found_optional = [p for p in OPTIONAL_PLACEHOLDERS if p in found_placeholders]
        if found_optional:
            print(f"\nℹ️  Found {len(found_optional)} optional placeholder(s):")
            for placeholder in found_optional:
                print(f"   ✅ {placeholder}")
        
        print("\n" + "=" * 70)
        if not missing:
            print("🎉 Template is VALID and ready to use!")
            print("=" * 70)
            
            # Provide next steps
            print("\n📝 Next steps:")
            print("1. Share template with service account:")
            print("   sti-slides-generator@my-drive-392615.iam.gserviceaccount.com")
            print("2. Update config.py:")
            print(f"   ENABLE_SLIDES_GENERATION = True")
            print(f"   GOOGLE_SLIDES_TEMPLATE_ID = \"{template_id}\"")
            return True
        else:
            print("⚠️  Template has missing placeholders - please add them")
            print("=" * 70)
            return False
            
    except HttpError as e:
        if e.resp.status == 404:
            print(f"❌ Template not found. Check template ID: {template_id}")
        elif e.resp.status == 403:
            print(f"❌ Permission denied. Make sure template is shared with:")
            print("   sti-slides-generator@my-drive-392615.iam.gserviceaccount.com")
        else:
            print(f"❌ API Error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(f"\nTraceback:\n{traceback.format_exc()}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        template_id = STIConfig.GOOGLE_SLIDES_TEMPLATE_ID
        if not template_id:
            print("Usage: python3 validate_slides_template.py <template_id>")
            print("   OR set GOOGLE_SLIDES_TEMPLATE_ID in config.py")
            sys.exit(1)
    else:
        template_id = sys.argv[1]
    
    success = validate_template(template_id)
    sys.exit(0 if success else 1)

