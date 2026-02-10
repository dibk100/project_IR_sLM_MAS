import logging
import sys
from pathlib import Path

def setup_logging(name: str, log_file: Path = None, level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    # File handler
    if log_file:
        fh = logging.FileHandler(log_file)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        
    return logger

def count_diff_lines(diff_content: str) -> tuple[int, int, int]:
    """
    Returns (added, removed, files_changed)
    """
    added = 0
    removed = 0
    files_changed = 0
    
    lines = diff_content.splitlines()
    for line in lines:
        if line.startswith("+++ "):
            files_changed += 1
        elif line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
            
    return added, removed, files_changed

def check_docker():
    """Checks if docker is available and running."""
    import shutil
    import subprocess
    
    if not shutil.which("docker"):
        return False
    
    try:
        subprocess.run(["docker", "info"], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False
