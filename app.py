from flask import Flask, request, jsonify, session, render_template
from flask_cors import CORS
import os
import json
from datetime import datetime
from dotenv import load_dotenv
import logging

from services.chat_service import ChatService
from services.data_validator import DataValidator
from utils.error_handler import ErrorHandler

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-prod')
CORS(app)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize services
chat_service = None
data_validator = None
error_handler = ErrorHandler()

def init_services():
    """Initialize external service connections (Snowflake, Claude).
    Does NOT raise on failure - the app should still start and respond
    to users even if a dependency is temporarily unavailable, per the
    graceful degradation requirement. Failed init is retried lazily on
    the next request via ensure_services_ready()."""
    global chat_service, data_validator
    try:
        chat_service = ChatService()
        data_validator = DataValidator()
        logger.info("Services initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize services: {str(e)}")
        chat_service = None
        data_validator = None


def ensure_services_ready() -> bool:
    """Check if services are initialized; retry once if not.
    Returns True if ready, False if still unavailable."""
    global chat_service, data_validator
    if chat_service is not None and data_validator is not None:
        return True
    logger.info("Services not ready, attempting to reconnect...")
    init_services()
    return chat_service is not None and data_validator is not None

@app.before_request
def before_request():
    if 'conversation_history' not in session:
        session['conversation_history'] = []

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat()
    }), 200

@app.route('/api/chat', methods=['POST'])
def chat():
    """
    Main chat endpoint. Accepts a user message and returns an agent response.
    Preserves conversation context across turns.
    """
    try:
        if not ensure_services_ready():
            return error_handler.format_error(
                "I'm having trouble connecting to the census data source right now. "
                "This is usually temporary - please try again in a few minutes.",
                503,
                'SERVICE_UNAVAILABLE'
            )

        data = request.get_json()
        
        if not data or 'message' not in data:
            return error_handler.format_error(
                'Missing message field',
                400,
                'INVALID_INPUT'
            )
        
        user_message = data.get('message', '').strip()
        
        if not user_message:
            return error_handler.format_error(
                'Message cannot be empty',
                400,
                'EMPTY_MESSAGE'
            )
        
        if len(user_message) > 500:
            return error_handler.format_error(
                'Message exceeds maximum length of 500 characters',
                400,
                'MESSAGE_TOO_LONG'
            )
        
        # Get conversation history from session
        conversation_history = session.get('conversation_history', [])

        has_context = len(conversation_history) > 0
        if not data_validator.is_on_topic(user_message, has_context=has_context):
            return jsonify({
                'response': "I'm designed to answer questions about US Census population data. "
                           "Could you ask something related to US demographics, population statistics, "
                           "or census information?",
                'is_off_topic': True,
                'conversation_turn': len(conversation_history) + 1
            }), 200
        
        # Call chat service
        response_data = chat_service.process_message(
            user_message,
            conversation_history
        )
        
        # Update session history
        conversation_history.append({
            'role': 'user',
            'content': user_message,
            'timestamp': datetime.utcnow().isoformat()
        })
        conversation_history.append({
            'role': 'assistant',
            'content': response_data['response'],
            'timestamp': datetime.utcnow().isoformat()
        })
        
        # Keep last 10 turns to manage session size
        session['conversation_history'] = conversation_history[-20:]
        session.modified = True
        
        return jsonify({
            'response': response_data['response'],
            'query_executed': response_data.get('query_executed', False),
            'is_off_topic': False,
            'conversation_turn': len(conversation_history) // 2
        }), 200
        
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}", exc_info=True)
        return error_handler.format_error(
            'An error occurred while processing your message',
            500,
            'INTERNAL_ERROR'
        )

@app.route('/api/reset', methods=['POST'])
def reset_conversation():
    """Clear conversation history"""
    try:
        session['conversation_history'] = []
        session.modified = True
        return jsonify({
            'status': 'success',
            'message': 'Conversation history cleared'
        }), 200
    except Exception as e:
        logger.error(f"Error resetting conversation: {str(e)}")
        return error_handler.format_error(
            'Failed to reset conversation',
            500,
            'RESET_ERROR'
        )

@app.route('/api/history', methods=['GET'])
def get_history():
    """Get current conversation history"""
    try:
        history = session.get('conversation_history', [])
        return jsonify({
            'history': history,
            'turn_count': len([h for h in history if h['role'] == 'user'])
        }), 200
    except Exception as e:
        logger.error(f"Error fetching history: {str(e)}")
        return error_handler.format_error(
            'Failed to retrieve conversation history',
            500,
            'HISTORY_ERROR'
        )

@app.errorhandler(404)
def not_found(error):
    return error_handler.format_error(
        'Endpoint not found',
        404,
        'NOT_FOUND'
    )

@app.errorhandler(500)
def internal_error(error):
    return error_handler.format_error(
        'Internal server error',
        500,
        'INTERNAL_ERROR'
    )

# Initialize services at module import time. This must happen here (not
# only inside the __main__ block below) because production servers like
# gunicorn import this module rather than executing it directly, so any
# __main__-only code never runs under gunicorn - this caused chat_service
# and data_validator to stay None in the deployed environment.
init_services()

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
