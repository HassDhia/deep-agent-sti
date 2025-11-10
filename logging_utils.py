"""
Logging Utilities for STI Intelligence System

Provides centralized logging configuration, file handlers, and terminal output capture
for comprehensive debugging and audit trails.
"""

import logging
import sys
import traceback
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple


def setup_run_logging(report_dir: str, query: str) -> Tuple[logging.Logger, str]:
    """
    Set up comprehensive file-based logging for a report generation run.
    Configures ROOT logger so all child loggers inherit the file handler.
    
    Args:
        report_dir: Directory where the report will be saved
        query: Search query for context
        
    Returns:
        Tuple of (run_logger instance, log_file_path)
    """
    # Create timestamped log file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_filename = f"run_log_{timestamp}.log"
    log_file_path = str(Path(report_dir) / log_filename)
    
    # Ensure report directory exists
    Path(report_dir).mkdir(parents=True, exist_ok=True)
    
    # Get ROOT logger (not a named logger) - this ensures all child loggers inherit handlers
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture all levels
    
    # Clear existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    # File handler with detailed format
    file_handler = logging.FileHandler(log_file_path, mode='w', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
    
    # Console handler (preserves existing behavior)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)  # Console shows INFO and above
    console_formatter = logging.Formatter('%(message)s')  # Simpler format for console
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # Ensure propagation is enabled (default, but explicit is better)
    # Child loggers will propagate to root logger, which has our handlers
    root_logger.propagate = True
    
    # Create a named logger for run-specific logging
    run_logger = logging.getLogger('sti_run')
    run_logger.setLevel(logging.DEBUG)
    # Don't add handlers to run_logger - it will propagate to root logger
    
    # Log initial context
    run_logger.info("=" * 70)
    run_logger.info(f"STI Intelligence System - Run Log")
    run_logger.info(f"Query: {query}")
    run_logger.info(f"Report Directory: {report_dir}")
    run_logger.info(f"Log File: {log_filename}")
    run_logger.info(f"Started: {datetime.now().isoformat()}")
    run_logger.info("=" * 70)
    
    return run_logger, log_file_path


@contextmanager
def capture_terminal_output(log_file_path: str):
    """
    Context manager that captures stdout/stderr and writes to both console and log file.
    
    Args:
        log_file_path: Path to the log file
        
    Usage:
        with capture_terminal_output(log_path):
            print("This will be logged")
    """
    log_file = open(log_file_path, 'a', encoding='utf-8')
    
    class TeeOutput:
        """Tee output to both console and file"""
        def __init__(self, *files):
            self.files = files
        
        def write(self, text):
            for f in self.files:
                f.write(text)
                f.flush()
        
        def flush(self):
            for f in self.files:
                f.flush()
    
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    
    try:
        # Redirect stdout and stderr to both console and file
        sys.stdout = TeeOutput(original_stdout, log_file)
        sys.stderr = TeeOutput(original_stderr, log_file)
        yield
    finally:
        # Restore original stdout/stderr
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        log_file.close()


def log_exception(logger: logging.Logger, exc: Exception, context: str = "", 
                  query: Optional[str] = None, **kwargs) -> None:
    """
    Log a full exception with traceback and context information.
    
    Args:
        logger: Logger instance to use
        exc: Exception that was raised
        context: Additional context string
        query: Query string for context
        **kwargs: Additional context key-value pairs
    """
    error_msg = f"Exception occurred: {type(exc).__name__}: {str(exc)}"
    if context:
        error_msg = f"{context} - {error_msg}"
    
    logger.error(error_msg)
    
    # Log full traceback
    tb_str = traceback.format_exc()
    logger.error(f"Traceback:\n{tb_str}")
    
    # Log context information
    if query:
        logger.error(f"Query: {query}")
    
    if kwargs:
        logger.error(f"Context: {kwargs}")
    
    # Log exception details
    logger.error(f"Exception Type: {type(exc).__name__}")
    logger.error(f"Exception Message: {str(exc)}")


def get_error_info(exc: Exception, context: Dict[str, any] = None) -> Dict[str, any]:
    """
    Extract structured error information from an exception.
    
    Args:
        exc: Exception that was raised
        context: Additional context dictionary
        
    Returns:
        Dictionary with error information
    """
    return {
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "traceback": traceback.format_exc(),
        "timestamp": datetime.now().isoformat(),
        "context": context or {}
    }

