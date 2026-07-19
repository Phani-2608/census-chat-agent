import anthropic
import os
import logging
from typing import List, Dict, Any
import json
from services.database import SnowflakeDB
from services.query_generator import QueryGenerator

logger = logging.getLogger(__name__)

class ChatService:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        self.db = SnowflakeDB()
        self.query_gen = QueryGenerator()
        self.model = "claude-sonnet-5"
        
    def process_message(self, user_message: str, conversation_history: List[Dict]) -> Dict[str, Any]:
        """
        Process user message and generate response.
        Uses multi-turn conversation for context awareness.
        """
        try:
            # Build context with recent conversation
            messages = self._build_messages(user_message, conversation_history)
            
            # Step 1: Determine if query is answerable with available data
            is_answerable = self._check_answerability(user_message)
            if not is_answerable:
                return {
                    'response': self._generate_unanswerable_response(user_message),
                    'query_executed': False
                }
            
            # Step 2: Generate SQL query
            sql_query = self.query_gen.generate_query(user_message, conversation_history)
            
            if not sql_query or sql_query.lower().startswith('error'):
                return {
                    'response': "I wasn't able to construct a valid query for that question. "
                               "Could you try rephrasing or ask something more specific about "
                               "the US Census population data?",
                    'query_executed': False
                }
            
            # Step 3: Execute query
            logger.info(f"Executing query: {sql_query[:100]}...")
            query_result = self.db.execute_query(sql_query)
            
            if query_result is None or (isinstance(query_result, list) and len(query_result) == 0):
                return {
                    'response': "The query returned no results. This might mean:\n"
                               "- The specific data you're asking about doesn't exist in our dataset\n"
                               "- Try asking about different regions, demographics, or time periods",
                    'query_executed': True
                }
            
            # Step 4: Generate natural language response
            response_text = self._generate_response(
                user_message, 
                query_result, 
                messages
            )
            
            return {
                'response': response_text,
                'query_executed': True
            }
            
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}", exc_info=True)
            return {
                'response': "I encountered an error while processing your question. "
                           "Please try again or rephrase your question.",
                'query_executed': False,
                'error': str(e)
            }
    
    def _build_messages(self, current_message: str, history: List[Dict]) -> List[Dict]:
        """Build message list for Claude API call"""
        messages = []
        
        # Add relevant recent history (last 4 turns)
        for msg in history[-8:]:
            messages.append({
                'role': msg['role'],
                'content': msg['content']
            })
        
        # Add current message
        messages.append({
            'role': 'user',
            'content': current_message
        })
        
        return messages
    
    def _check_answerability(self, user_message: str) -> bool:
        """
        Check if the question is potentially answerable with census data.
        Uses Claude to evaluate the question.
        """
        try:
            system_prompt = """You are a data analyst evaluating whether a question can be answered 
            using US Census population data. 

            Respond with ONLY "yes" or "no". 
            
            Say "yes" if the question is about:
            - US population statistics
            - Demographics (age, gender, race, ethnicity)
            - Geographic distributions (states, counties, cities)
            - Census data, population counts, percentages
            
            Say "no" if asking about:
            - Non-US data
            - Non-demographic topics (politics, sports, entertainment)
            - Future predictions or current events
            - Personal information or specific individuals"""
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=10,
                system=system_prompt,
                messages=[{'role': 'user', 'content': user_message}]
            )
            
            answer = next(b.text for b in response.content if b.type == "text").strip().lower()
            return answer.startswith('yes')
            
        except Exception as e:
            logger.error(f"Error checking answerability: {str(e)}")
            # Default to true to let query execution determine if answerable
            return True
    
    def _generate_response(self, user_message: str, query_result: List[Dict], 
                          messages: List[Dict]) -> str:
        """
        Generate natural language response from query results.
        """
        try:
            # Format query results for readability
            results_str = self._format_results(query_result)
            
            system_prompt = """You are a helpful US Census data analyst. 
            
            Provide clear, concise answers based on the data provided.
            - Be specific with numbers and percentages
            - Add context when helpful (e.g., "This represents X% of the total")
            - If data is limited or has caveats, mention them
            - Keep responses under 150 words when possible"""
            
            # Build context for response generation
            response_messages = messages.copy()
            response_messages.append({
                'role': 'user',
                'content': f"Based on this census data: {results_str}\n\nAnswer the original question."
            })
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                system=system_prompt,
                messages=response_messages
            )
            
            return next(b.text for b in response.content if b.type == "text")
            
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            return f"I retrieved data but had trouble formatting the response: {str(query_result)}"
    
    def _format_results(self, results: List[Dict]) -> str:
        """Format query results into readable string"""
        if not results:
            return "No data found"
        
        if len(results) > 10:
            # Truncate large results
            results = results[:10]
            truncated = True
        else:
            truncated = False
        
        formatted = json.dumps(results, indent=2)
        if truncated:
            formatted += "\n... (results truncated)"
        
        return formatted
    
    def _generate_unanswerable_response(self, user_message: str) -> str:
        """Generate a response for unanswerable questions"""
        return ("I'm specifically designed to answer questions about US Census population data. "
               "Your question doesn't seem related to US demographics. "
               "Could you ask about something like:\n"
               "- Population by state or county\n"
               "- Demographic breakdowns by age, gender, or race\n"
               "- Census statistics and trends")
