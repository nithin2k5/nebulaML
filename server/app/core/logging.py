import logging
import sys
from logging.handlers import RotatingFileHandler
import os

# Create logs directory if it doesn't exist
LOGS_DIR = "logs"
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

def setup_logger(name: str) -> logging.Logger:
    """
    Sets up a structured logger for the application.
    Writes to both console (stdout) and a rotating uncolored log file.
    """
    logger = logging.getLogger(name)
    
    # Only configure if haven't done so already for this logger instance
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        logger.propagate = False

        # Format for logs
        log_format = "%(asctime)s - [%(levelname)s] - %(name)s - %(message)s"
        formatter = logging.Formatter(log_format, datefmt="%Y-%m-%d %H:%M:%S")

        # 1. Console Handler (stdout)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # 2. File Handler (Rotating log files, max 5MB, keep 3 backups)
        file_handler = RotatingFileHandler(
            f"{LOGS_DIR}/app.log", 
            maxBytes=5_000_000, 
            backupCount=3,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

# Create a default logger instance to be imported
logger = setup_logger("nebula")
