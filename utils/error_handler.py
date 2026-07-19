from flask import jsonify
import logging

logger = logging.getLogger(__name__)

class ErrorHandler:
    @staticmethod
    def format_error(message: str, status_code: int, error_code: str = 'UNKNOWN_ERROR') -> tuple:
        """Format error response consistently"""
        error_response = {
            'error': True,
            'message': message,
            'error_code': error_code
        }
        return jsonify(error_response), status_code
    
    @staticmethod
    def log_error(error_type: str, message: str, exc: Exception = None):
        """Log error with consistent format"""
        if exc:
            logger.error(f"{error_type}: {message}", exc_info=True)
        else:
            logger.error(f"{error_type}: {message}")
