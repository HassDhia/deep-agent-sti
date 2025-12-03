#!/usr/bin/env python3
"""
Test script to run the slides generator on an existing report
"""

import json
import logging
import os
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from slides_generator import SlidesGenerator
from config import STIConfig

def main():
    # Use the latest report (energy arbitrage)
    report_dir = "sti_reports/sti_enhanced_output_20251103_153910_the_energy_arbitrage"
    
    if not os.path.exists(report_dir):
        print(f"❌ Report directory not found: {report_dir}")
        sys.exit(1)
    
    # Load metadata and report files
    metadata_file = os.path.join(report_dir, "metadata.json")
    markdown_file = os.path.join(report_dir, "intelligence_report.md")
    jsonld_file = os.path.join(report_dir, "intelligence_report.jsonld")
    
    if not all(os.path.exists(f) for f in [metadata_file, markdown_file, jsonld_file]):
        print(f"❌ Required files not found in {report_dir}")
        sys.exit(1)
    
    # Load data
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)
    
    with open(markdown_file, 'r') as f:
        markdown_report = f.read()
    
    with open(jsonld_file, 'r') as f:
        json_ld_artifact = json.load(f)
    
    query = metadata.get('query', 'Test Query')
    
    print("=" * 70)
    print("🧪 Testing Slides Generator")
    print("=" * 70)
    print(f"📁 Report Directory: {report_dir}")
    print(f"🔍 Query: {query}")
    print(f"📊 Template ID: {STIConfig.GOOGLE_SLIDES_TEMPLATE_ID or '(creating from scratch)'}")
    print(f"🔐 Auth: {'OAuth' if STIConfig.GOOGLE_USE_OAUTH else 'Service Account'}")
    print("=" * 70)
    
    # Check if images exist
    images_dir = Path(report_dir) / "images"
    if images_dir.exists():
        images = list(images_dir.glob("*.png"))
        print(f"📸 Found {len(images)} image(s)")
        for img in images[:5]:  # Show first 5
            print(f"   - {img.name}")
    else:
        print("⚠️  No images directory found")
    
    print("\n🚀 Initializing Slides Generator...")
    
    try:
        # Initialize generator
        creds_path = STIConfig.GOOGLE_CREDENTIALS_PATH or os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        use_oauth = getattr(STIConfig, 'GOOGLE_USE_OAUTH', True)
        
        generator = SlidesGenerator(credentials_path=creds_path, use_oauth=use_oauth)
        
        print("✅ Generator initialized successfully")
        print("\n🎨 Generating slides...")
        
        # Generate slides
        result = generator.generate_slides(
            report_dir=report_dir,
            query=query,
            metadata=metadata,
            json_ld_artifact=json_ld_artifact,
            markdown_report=markdown_report
        )
        
        if result:
            print("\n" + "=" * 70)
            print("✅ SUCCESS!")
            print("=" * 70)
            print(f"📄 Slides URL: {result.get('slides_url', 'N/A')}")
            print(f"📥 PDF Path: {result.get('pdf_path', 'N/A')}")
            print("=" * 70)
            print("\n🔗 Open the slides URL to view the generated presentation")
        else:
            print("\n❌ Slide generation failed (returned None)")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        print("\nTraceback:")
        print(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()
