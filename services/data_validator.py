import logging
import re
from typing import List

logger = logging.getLogger(__name__)

class DataValidator:
    def __init__(self):
        # Keywords that indicate census/demographic topics
        self.census_keywords = {
            'population', 'demographic', 'census', 'state', 'county', 'city',
            'age', 'gender', 'race', 'ethnicity', 'income', 'education',
            'household', 'housing', 'urban', 'rural', 'region', 'district',
            'residents', 'inhabitants', 'statistics', 'data', 'percent',
            'percentage', 'count', 'total', 'breakdown', 'distribution',
            'median', 'average', 'us', 'united states', 'america'
        }
        
        # Keywords that indicate off-topic content
        self.off_topic_keywords = {
            'stock', 'bitcoin', 'weather', 'movie', 'game', 'recipe',
            'joke', 'poem', 'story', 'sports', 'score', 'music',
            'celebrity', 'politics', 'election', 'covid', 'covid-19',
            'vaccine', 'medical', 'diagnosis', 'treatment', 'doctor',
            'legal', 'law', 'court', 'crime', 'terrorism', 'bomb',
            'kill', 'hack', 'malware', 'exploit'
        }
        
        # Completely block these patterns
        self.blocked_patterns = [
            r'DROP\s+TABLE',
            r'DELETE\s+FROM',
            r'UPDATE\s+',
            r'INSERT\s+INTO',
            r'exec\s*\(',
            r'execute\s*\(',
            r'script',
            r'<script',
        ]
    
    def is_on_topic(self, message: str, has_context: bool = False) -> bool:
        """
        Check if message is on-topic for census data.
        Returns True if likely about census/demographics, False otherwise.

        has_context: True if this message is part of an ongoing conversation
        that already has prior turns. Short follow-ups like "What about Texas?"
        don't contain census keywords on their own, but are clearly on-topic
        if they're continuing an existing census conversation.
        """
        try:
            if self._has_blocked_patterns(message):
                logger.warning(f"Blocked pattern detected in message")
                return False
            
            message_lower = message.lower()
            
            census_matches = self._count_keyword_matches(message_lower, self.census_keywords)
            off_topic_matches = self._count_keyword_matches(message_lower, self.off_topic_keywords)
            
            if off_topic_matches >= 2:
                logger.info(f"Off-topic message detected (matches: {off_topic_matches})")
                return False
            
            if census_matches >= 1:
                return True
            
            if any(pattern in message_lower for pattern in [
                'how many', 'what is the population', 'how many people',
                'percentage of', 'demographics of', 'census data for',
                'population in', 'people in', 'residents in'
            ]):
                return True

            is_followup_phrasing = any(message_lower.startswith(p) for p in [
                'what about', 'and what about', 'how about', 'and ',
                'what if', 'and for', 'what of'
            ])
            if has_context and is_followup_phrasing and off_topic_matches == 0:
                return True

            if has_context and off_topic_matches == 0 and len(message.split()) <= 6:
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error validating topic: {str(e)}")
            return True  # When in doubt, let the model decide
    
    def validate_input_length(self, message: str, max_length: int = 500) -> tuple[bool, str]:
        """Validate message length"""
        if len(message) > max_length:
            return False, f"Message exceeds maximum length of {max_length} characters"
        return True, ""
    
    def validate_input_format(self, message: str) -> tuple[bool, str]:
        """Validate basic input format"""
        if not message or not message.strip():
            return False, "Message cannot be empty"
        
        if not any(c.isalnum() for c in message):
            return False, "Message must contain at least some text"
        
        return True, ""
    
    def _has_blocked_patterns(self, message: str) -> bool:
        """Check for dangerous patterns"""
        message_upper = message.upper()
        for pattern in self.blocked_patterns:
            if re.search(pattern, message_upper, re.IGNORECASE):
                return True
        return False
    
    def _count_keyword_matches(self, message: str, keywords: set) -> int:
        """Count how many keywords appear in message"""
        count = 0
        for keyword in keywords:
            if keyword in message:
                count += 1
        return count
    
    def sanitize_output(self, text: str) -> str:
        """Remove potentially harmful content from output"""
        # Remove any HTML/script tags if present
        text = re.sub(r'<[^>]+>', '', text)
        return text.strip()
