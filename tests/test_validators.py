import unittest
from services.data_validator import DataValidator

class TestDataValidator(unittest.TestCase):
    def setUp(self):
        self.validator = DataValidator()
    
    def test_census_on_topic(self):
        """Test that census questions are marked as on-topic"""
        test_cases = [
            "What is the population of California?",
            "How many people live in New York?",
            "Show me demographic breakdown by age",
            "What percentage of people are Hispanic?",
            "Census data for Texas",
        ]
        
        for message in test_cases:
            with self.subTest(message=message):
                self.assertTrue(
                    self.validator.is_on_topic(message),
                    f"Should be on-topic: {message}"
                )
    
    def test_off_topic_detection(self):
        """Test that off-topic questions are detected"""
        test_cases = [
            "Tell me a joke",
            "What's the weather today?",
            "Who won the game yesterday?",
            "Can you help me with Bitcoin?",
            "What's your favorite movie?",
        ]
        
        for message in test_cases:
            with self.subTest(message=message):
                self.assertFalse(
                    self.validator.is_on_topic(message),
                    f"Should be off-topic: {message}"
                )
    
    def test_input_length_validation(self):
        """Test input length validation"""
        short_message = "What is the population?"
        long_message = "x" * 600
        
        is_valid, msg = self.validator.validate_input_length(short_message)
        self.assertTrue(is_valid)
        
        is_valid, msg = self.validator.validate_input_length(long_message)
        self.assertFalse(is_valid)
    
    def test_input_format_validation(self):
        """Test input format validation"""
        valid_message = "What is the population?"
        empty_message = ""
        only_spaces = "   "
        
        is_valid, msg = self.validator.validate_input_format(valid_message)
        self.assertTrue(is_valid)
        
        is_valid, msg = self.validator.validate_input_format(empty_message)
        self.assertFalse(is_valid)
        
        is_valid, msg = self.validator.validate_input_format(only_spaces)
        self.assertFalse(is_valid)
    
    def test_blocked_patterns(self):
        """Test that dangerous patterns are blocked"""
        dangerous_messages = [
            "'; DROP TABLE users; --",
            "DELETE FROM census_data",
            "INSERT INTO users VALUES (1, 'hacker')",
            "<script>alert('xss')</script>",
        ]
        
        for message in dangerous_messages:
            with self.subTest(message=message):
                self.assertFalse(
                    self.validator.is_on_topic(message),
                    f"Should block: {message}"
                )
    
    def test_sanitize_output(self):
        """Test output sanitization"""
        text_with_html = "Some text <script>alert('xss')</script> more text"
        sanitized = self.validator.sanitize_output(text_with_html)
        self.assertNotIn('<script>', sanitized)
        self.assertNotIn('</script>', sanitized)

if __name__ == '__main__':
    unittest.main()
