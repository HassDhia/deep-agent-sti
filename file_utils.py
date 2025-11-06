"""
File Utilities for STI Intelligence System

Provides automatic nested file saving functionality for all intelligence reports
with organized directory structure and comprehensive metadata tracking.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class STIFileManager:
    """
    Manages automatic file saving for STI Intelligence System reports
    with nested directory structure and comprehensive metadata.
    """
    
    def __init__(self, base_output_dir: str = "sti_reports"):
        self.base_output_dir = base_output_dir
        self.ensure_output_directory()
    
    def ensure_output_directory(self):
        """Ensure the base output directory exists"""
        Path(self.base_output_dir).mkdir(exist_ok=True)
        logger.info(f"Output directory ensured: {self.base_output_dir}")
    
    def create_report_directory(self, agent_type: str, query: str, days_back: int = 7) -> str:
        """
        Create a timestamped directory for a specific report
        
        Args:
            agent_type: Type of agent (simple, enhanced, multi-agent)
            query: Search query
            days_back: Number of days back for search
            
        Returns:
            Path to the created directory
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        query_slug = self._slugify_query(query)
        
        dir_name = f"sti_{agent_type}_output_{timestamp}_{query_slug}"
        report_dir = os.path.join(self.base_output_dir, dir_name)
        
        os.makedirs(report_dir, exist_ok=True)
        logger.info(f"Created report directory: {report_dir}")
        
        return report_dir
    
    def _slugify_query(self, query: str) -> str:
        """Convert query to filesystem-safe slug"""
        return "".join(c.lower() if c.isalnum() else "_" for c in query)[:20]
    
    def save_enhanced_report(self, query: str, markdown_report: str, 
                           json_ld_artifact: Dict[str, Any], 
                           days_back: int = 7, 
                           agent_stats: Optional[Dict[str, Any]] = None,
                           generate_html: bool = True) -> str:
        """
        Save enhanced agent report with full nested structure
        
        Args:
            query: Search query
            markdown_report: Generated markdown report
            json_ld_artifact: JSON-LD structured data
            days_back: Number of days back for search
            agent_stats: Optional agent statistics
            generate_html: Whether to generate HTML version
            
        Returns:
            Path to the created report directory
        """
        report_dir = self.create_report_directory("enhanced", query, days_back)
        
        # Save markdown report
        markdown_file = os.path.join(report_dir, 'intelligence_report.md')
        with open(markdown_file, 'w', encoding='utf-8') as f:
            f.write(markdown_report)
        logger.info(f"💾 Saved markdown report: {markdown_file}")
        
        # Save JSON-LD artifact
        jsonld_file = os.path.join(report_dir, 'intelligence_report.jsonld')
        with open(jsonld_file, 'w', encoding='utf-8') as f:
            json.dump(json_ld_artifact, f, indent=2, ensure_ascii=False)
        logger.info(f"💾 Saved JSON-LD artifact: {jsonld_file}")
        
        # Extract and save executive summary
        exec_summary = json_ld_artifact.get('abstract', 'Executive summary not available')
        summary_file = os.path.join(report_dir, 'executive_summary.txt')
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(exec_summary)
        logger.info(f"💾 Saved executive summary: {summary_file}")
        
        # Extract and save sources/parts data (fallback to agent_stats if provided)
        sources_data = []
        if 'hasPart' in json_ld_artifact:
            for i, part in enumerate(json_ld_artifact['hasPart'], 1):
                sources_data.append({
                    'id': i,
                    'headline': part.get('headline', ''),
                    'confidence': part.get('confidence', 0),
                    'citations': part.get('citation', [])
                })
        elif agent_stats and isinstance(agent_stats.get('sources_data'), list):
            sources_data = agent_stats['sources_data']
        
        sources_file = os.path.join(report_dir, 'sources.json')
        with open(sources_file, 'w', encoding='utf-8') as f:
            json.dump(sources_data, f, indent=2, ensure_ascii=False)
        logger.info(f"💾 Saved sources data: {sources_file}")
        
        # Create comprehensive metadata
        metadata = {
            'generation_timestamp': datetime.now().isoformat(),
            'query': query,
            'days_back': days_back,
            'report_stats': {
                'character_count': len(markdown_report),
                'word_count': len(markdown_report.split()),
                'jsonld_size': len(json.dumps(json_ld_artifact))
            },
            'confidence_score': json_ld_artifact.get('aggregateRating', {}).get('ratingValue', 'N/A'),
            'sources_count': agent_stats.get('validated_sources_count', len(sources_data)),  # NEW
            'system_info': {
                'agent_type': 'Enhanced STI Agent',
                'version': '1.0.0',
                'model': 'gpt-5-mini-2025-08-07',
                'date_filtering': 'Strict 7-day window enforced'
            }
        }
        
        # Add agent statistics if provided
        if agent_stats:
            metadata['agent_stats'] = agent_stats
        
        metadata_file = os.path.join(report_dir, 'metadata.json')
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        logger.info(f"💾 Saved metadata: {metadata_file}")
        
        # Generate HTML version if requested
        if generate_html:
            try:
                from html_converter_agent import HTMLConverterAgent
                converter = HTMLConverterAgent()
                html_report = converter.convert(markdown_report, json_ld_artifact, metadata, report_dir=report_dir)
                
                html_file = os.path.join(report_dir, 'intelligence_report.html')
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(html_report)
                logger.info(f"💾 Saved HTML report: {html_file}")
                
            except Exception as e:
                logger.error(f"Error generating HTML report: {str(e)}")
                logger.info("Continuing without HTML generation...")
        
        # Generate Google Slides presentation if enabled
        try:
            from config import STIConfig
            if STIConfig.ENABLE_SLIDES_GENERATION:
                from slides_generator import SlidesGenerator
                
                # Get credentials path from config or env (only needed for service account)
                creds_path = STIConfig.GOOGLE_CREDENTIALS_PATH
                if not creds_path:
                    creds_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
                
                # Use OAuth by default (can be overridden in config)
                use_oauth = getattr(STIConfig, 'GOOGLE_USE_OAUTH', True)
                generator = SlidesGenerator(credentials_path=creds_path, use_oauth=use_oauth)
                slides_result = generator.generate_slides(
                    report_dir=report_dir,
                    query=query,
                    metadata=metadata,
                    json_ld_artifact=json_ld_artifact,
                    markdown_report=markdown_report
                )
                if slides_result:
                    logger.info(f"✅ Slide deck generated: {slides_result.get('slides_url', 'N/A')}")
            else:
                logger.debug("Slide generation disabled in config")
        except ImportError as e:
            logger.debug(f"Slide generation not available: {e}")
        except Exception as e:
            logger.error(f"Error generating slides: {str(e)}")
            logger.info("Continuing without slide generation...")
        
        # Print summary
        self._print_save_summary(report_dir, metadata)
        
        return report_dir
    
    def save_social_media_content(self, report_dir: str, social_content: Dict[str, Any]) -> None:
        """
        Save social media content to report directory
        
        Args:
            report_dir: Path to the report directory
            social_content: Dictionary containing long_form, twitter_thread, linkedin_post
        """
        try:
            # Save long-form post
            long_form_file = os.path.join(report_dir, 'social_media_post.md')
            with open(long_form_file, 'w', encoding='utf-8') as f:
                f.write(social_content.get('long_form', ''))
            logger.info(f"💾 Saved social media post: {long_form_file}")
            
            # Save Twitter thread
            twitter_thread = social_content.get('twitter_thread', [])
            twitter_file = os.path.join(report_dir, 'social_media_thread.txt')
            with open(twitter_file, 'w', encoding='utf-8') as f:
                for i, tweet in enumerate(twitter_thread, 1):
                    f.write(f"{i}/{len(twitter_thread)} {tweet}\n")
            logger.info(f"💾 Saved Twitter thread: {twitter_file}")
            
            # Save LinkedIn post
            linkedin_file = os.path.join(report_dir, 'social_media_linkedin.txt')
            with open(linkedin_file, 'w', encoding='utf-8') as f:
                f.write(social_content.get('linkedin_post', ''))
            logger.info(f"💾 Saved LinkedIn post: {linkedin_file}")
            
            # Update metadata to include social media content info
            metadata_file = os.path.join(report_dir, 'metadata.json')
            if os.path.exists(metadata_file):
                try:
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                    
                    # Add social media content metadata
                    metadata['social_media_content'] = {
                        'generated': True,
                        'formats': ['long_form', 'twitter_thread', 'linkedin_post'],
                        'metadata': social_content.get('metadata', {}),
                        'generation_timestamp': social_content.get('metadata', {}).get('generation_timestamp', '')
                    }
                    
                    with open(metadata_file, 'w', encoding='utf-8') as f:
                        json.dump(metadata, f, indent=2, ensure_ascii=False)
                    logger.info(f"💾 Updated metadata with social media content info")
                    
                except Exception as e:
                    logger.error(f"Error updating metadata: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error saving social media content: {str(e)}")
    
    def save_simple_report(self, query: str, markdown_report: str, 
                          days_back: int = 7,
                          agent_stats: Optional[Dict[str, Any]] = None) -> str:
        """
        Save simple agent report with nested structure
        
        Args:
            query: Search query
            markdown_report: Generated markdown report
            days_back: Number of days back for search
            agent_stats: Optional agent statistics (including date filter stats)
            
        Returns:
            Path to the created report directory
        """
        report_dir = self.create_report_directory("simple", query, days_back)
        
        # Save markdown report
        markdown_file = os.path.join(report_dir, 'simple_report.md')
        with open(markdown_file, 'w', encoding='utf-8') as f:
            f.write(markdown_report)
        logger.info(f"💾 Saved markdown report: {markdown_file}")
        
        # Create metadata
        metadata = {
            'generation_timestamp': datetime.now().isoformat(),
            'query': query,
            'days_back': days_back,
            'report_stats': {
                'character_count': len(markdown_report),
                'word_count': len(markdown_report.split())
            },
            'system_info': {
                'agent_type': 'Simple STI Agent',
                'version': '1.0.0',
                'model': 'gpt-5-mini-2025-08-07',
                'date_filtering': 'Strict 7-day window enforced'
            }
        }
        
        # Add agent statistics if provided
        if agent_stats:
            metadata['agent_stats'] = agent_stats
        
        metadata_file = os.path.join(report_dir, 'metadata.json')
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        logger.info(f"💾 Saved metadata: {metadata_file}")
        
        # Print summary
        self._print_save_summary(report_dir, metadata)
        
        return report_dir
    
    def _print_save_summary(self, report_dir: str, metadata: Dict[str, Any]):
        """Print a summary of saved files"""
        print(f"\n{'='*70}")
        print(f"🎉 REPORT SAVED SUCCESSFULLY!")
        print(f"{'='*70}")
        print(f"📁 Output Directory: {report_dir}")
        print(f"📄 Files Generated:")
        
        # List files in directory
        files = os.listdir(report_dir)
        for file in sorted(files):
            file_path = os.path.join(report_dir, file)
            if os.path.isfile(file_path):
                size = os.path.getsize(file_path)
                print(f"  • {file} ({size:,} bytes)")
        
        # Show key statistics
        stats = metadata.get('report_stats', {})
        print(f"\n📊 Report Statistics:")
        print(f"  • Word Count: {stats.get('word_count', 'N/A')}")
        print(f"  • Character Count: {stats.get('character_count', 'N/A')}")
        print(f"  • Confidence: {metadata.get('confidence_score', 'N/A')}")
        print(f"  • Sources: {metadata.get('sources_count', 'N/A')}")
        
        # Show date filtering stats if available
        agent_stats = metadata.get('agent_stats', {})
        if 'date_filter_stats' in agent_stats:
            filter_stats = agent_stats['date_filter_stats']
            print(f"  • Date Filter Success Rate: {filter_stats.get('success_rate', 0):.1%}")
        
        print(f"\n🚀 Ready for analysis and distribution!")
    
    def get_latest_report(self, agent_type: str = None) -> Optional[str]:
        """
        Get the path to the most recently created report
        
        Args:
            agent_type: Filter by agent type (simple, enhanced) or None for any
            
        Returns:
            Path to latest report directory or None if none found
        """
        if not os.path.exists(self.base_output_dir):
            return None
        
        # Get all report directories
        all_dirs = []
        for item in os.listdir(self.base_output_dir):
            item_path = os.path.join(self.base_output_dir, item)
            if os.path.isdir(item_path) and item.startswith('sti_'):
                if agent_type is None or f"_{agent_type}_" in item:
                    all_dirs.append(item_path)
        
        if not all_dirs:
            return None
        
        # Sort by modification time and return most recent
        latest_dir = max(all_dirs, key=os.path.getmtime)
        return latest_dir
    
    def list_reports(self, agent_type: str = None) -> List[str]:
        """
        List all available reports
        
        Args:
            agent_type: Filter by agent type (simple, enhanced) or None for any
            
        Returns:
            List of report directory paths
        """
        if not os.path.exists(self.base_output_dir):
            return []
        
        reports = []
        for item in os.listdir(self.base_output_dir):
            item_path = os.path.join(self.base_output_dir, item)
            if os.path.isdir(item_path) and item.startswith('sti_'):
                if agent_type is None or f"_{agent_type}_" in item:
                    reports.append(item_path)
        
        # Sort by modification time (newest first)
        reports.sort(key=os.path.getmtime, reverse=True)
        return reports


# Global file manager instance
file_manager = STIFileManager()


def save_enhanced_report_auto(query: str, markdown_report: str, 
                             json_ld_artifact: Dict[str, Any], 
                             days_back: int = 7, 
                             agent_stats: Optional[Dict[str, Any]] = None,
                             generate_html: bool = True) -> str:
    """
    Convenience function to automatically save enhanced agent report
    
    Returns:
        Path to the created report directory
    """
    return file_manager.save_enhanced_report(
        query, markdown_report, json_ld_artifact, days_back, agent_stats, generate_html
    )


def save_simple_report_auto(query: str, markdown_report: str, 
                           days_back: int = 7,
                           agent_stats: Optional[Dict[str, Any]] = None) -> str:
    """
    Convenience function to automatically save simple agent report
    
    Returns:
        Path to the created report directory
    """
    return file_manager.save_simple_report(
        query, markdown_report, days_back, agent_stats
    )


def get_latest_report(agent_type: str = None) -> Optional[str]:
    """
    Convenience function to get the latest report
    
    Returns:
        Path to latest report directory or None
    """
    return file_manager.get_latest_report(agent_type)


def list_all_reports(agent_type: str = None) -> List[str]:
    """
    Convenience function to list all reports
    
    Returns:
        List of report directory paths
    """
    return file_manager.list_reports(agent_type)
