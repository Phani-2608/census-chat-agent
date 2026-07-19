import anthropic
import os
import logging
from typing import List, Dict
import re

logger = logging.getLogger(__name__)

class QueryGenerator:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        self.model = "claude-sonnet-5"
        
    def generate_query(self, user_message: str, conversation_history: List[Dict]) -> str:
        """
        Generate SQL query from natural language question.
        Includes schema context for accurate query generation.
        """
        try:
            # Get schema information
            schema_context = self._get_schema_context()
            
            # Build conversation context
            context_str = self._build_context_string(conversation_history)
            
            system_prompt = f"""You are a SQL expert for Snowflake. Generate SQL queries to answer census questions.

SCHEMA INFORMATION:
{schema_context}

IMPORTANT RULES:
1. Use the CENSUS_DATA schema
2. Only use columns that exist in the tables shown above
3. Return valid Snowflake SQL syntax
4. For aggregations, use GROUP BY properly
5. Always LIMIT results to 50 rows maximum
6. Use clear, efficient queries
7. Handle NULL values appropriately
8. If the question cannot be answered with available data, respond with exactly: ERROR_UNANSWERABLE
9. This dataset ONLY supports geography at the STATE and COUNTY level (via
   the FIPS codes table). It does NOT contain city, town, or place names
   (e.g. "Springfield", "Portland" are NOT resolvable - those names could
   match many different counties/states and there is no city-level lookup
   table available). If the question asks about a city or town rather than
   a full state or county name, respond with exactly: ERROR_CITY_NOT_SUPPORTED
10. If the question names a county WITHOUT specifying which state, and that
    county name commonly exists in multiple US states (e.g. "Washington
    County", "Franklin County", "Jefferson County" all exist in a dozen+
    states each), do NOT guess which one. Instead respond with exactly:
    CLARIFY: <a natural, specific question asking which state, ideally
    naming 2-4 of the actual states where that county exists>
    Example: CLARIFY: There are several Washington Counties in the US -
    did you mean the one in Oregon, Pennsylvania, Maryland, or another
    state?
11. Respond with ONLY the raw SQL query and nothing else - no explanation,
    no commentary, no markdown formatting, before or after the query.
    Your entire response must be valid SQL that can be executed as-is.

CONTEXT FROM PREVIOUS MESSAGES:
{context_str if context_str else "This is the first message in the conversation."}

When generating queries:
- Consider what the user is actually asking for
- Use JOINs if data is in multiple tables
- Use WHERE clauses to filter for specific regions or demographics
- Use ORDER BY to show most relevant results first
- Include GROUP BY when aggregating data"""
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=800,
                system=system_prompt,
                messages=[{'role': 'user', 'content': user_message}]
            )
            
            query = next(b.text for b in response.content if b.type == "text").strip()
            
            # Clean up query (remove markdown code blocks if present)
            query = self._clean_query(query)

            if query in ('ERROR_UNANSWERABLE', 'ERROR_CITY_NOT_SUPPORTED') or query.startswith('CLARIFY:'):
                return query
            
            # Validate query syntax
            if self._is_valid_query(query):
                logger.info(f"Generated query: {query[:150]}...")
                return query
            else:
                logger.warning(f"Invalid query generated: {query[:100]}")
                return None
                
        except Exception as e:
            logger.error(f"Error generating query: {str(e)}")
            return None
    
    def _get_schema_context(self) -> str:
        """
        Return schema context for Claude to use.
        Based on the actual SafeGraph US Open Census Data structure in Snowflake.
        """
        schema = '''
DATABASE: "US_OPEN_CENSUS_DATA__NEIGHBORHOOD_INSIGHTS__FREE_DATASET"
SCHEMA: "PUBLIC"

TABLE: "US_OPEN_CENSUS_DATA__NEIGHBORHOOD_INSIGHTS__FREE_DATASET"."PUBLIC"."2020_CBG_B01"
(This is the core population/age/sex table, at Census Block Group level)
- CENSUS_BLOCK_GROUP: VARCHAR - 12-digit geographic ID. 
    Characters 1-2 = state FIPS code, characters 3-5 = county FIPS code.
- "B01001e1": FLOAT - TOTAL POPULATION estimate for that block group (use this for population questions)
- "B01001e2": FLOAT - Male population estimate
- "B01001e26": FLOAT - Female population estimate
- Other B01001eN columns break down population by age brackets

TABLE: "US_OPEN_CENSUS_DATA__NEIGHBORHOOD_INSIGHTS__FREE_DATASET"."PUBLIC"."2020_METADATA_CBG_FIPS_CODES"
(Maps state/county codes to real names)
- STATE: VARCHAR - two-letter state abbreviation (e.g. 'CA', 'NY', 'TX')
- STATE_FIPS: VARCHAR - 2-digit numeric state code (e.g. '06' for California)
- COUNTY_FIPS: VARCHAR - 3-digit numeric county code
- COUNTY: VARCHAR - county name

TABLE: "US_OPEN_CENSUS_DATA__NEIGHBORHOOD_INSIGHTS__FREE_DATASET"."PUBLIC"."2020_METADATA_CBG_FIELD_DESCRIPTIONS"
(Explains what each cryptic column code means)
- TABLE_ID: VARCHAR - column code like 'B01001e1'
- TABLE_TITLE: VARCHAR - human description e.g. 'Sex By Age'
- FIELD_LEVEL_1/2/3: VARCHAR - detailed breakdown description

CRITICAL: Column names like B01001e1 use MIXED CASE (lowercase letters).
Snowflake automatically UPPERCASES unquoted identifiers, which breaks these queries.
You MUST wrap every column name from the 2020_CBG_* tables in double quotes
to preserve exact case, for example: b."B01001e1"  (NOT b.B01001e1)
Table and database names should also stay double-quoted as shown below.

CRITICAL QUERY PATTERN for "population of [STATE]" questions:
Always convert the full state name to its 2-letter USPS abbreviation yourself
(e.g. California -> CA, Texas -> TX, New York -> NY), then use this pattern:

SELECT SUM(b."B01001e1") AS total_population
FROM "US_OPEN_CENSUS_DATA__NEIGHBORHOOD_INSIGHTS__FREE_DATASET"."PUBLIC"."2020_CBG_B01" b
WHERE LEFT(b.CENSUS_BLOCK_GROUP, 2) = (
    SELECT DISTINCT STATE_FIPS
    FROM "US_OPEN_CENSUS_DATA__NEIGHBORHOOD_INSIGHTS__FREE_DATASET"."PUBLIC"."2020_METADATA_CBG_FIPS_CODES"
    WHERE STATE = \'CA\'
    LIMIT 1
);

For county-level or other demographic questions, join in the same way but
filter on county FIPS as well, or use other 2020_CBG_* tables as needed.
'''
        return schema


    def _build_context_string(self, history: List[Dict]) -> str:
        """Build context from conversation history"""
        if not history:
            return ""
        
        context_parts = []
        for msg in history[-4:]:  # Last 2 turns
            role = "User" if msg['role'] == 'user' else "Assistant"
            content = msg['content']
            context_parts.append(f"{role}: {content}")
        
        return "\n".join(context_parts)
    
    def _clean_query(self, query: str) -> str:
        """Clean generated query by removing markdown, stray explanatory
        text, and extra whitespace."""
        query = re.sub(r'```sql\n?', '', query)
        query = re.sub(r'```\n?', '', query)

        match = re.search(r'\bSELECT\b', query, re.IGNORECASE)
        if match:
            query = query[match.start():]

        if '\n\n' in query:
            query = query.split('\n\n')[0]

        query = query.strip()
        return query
    
    def _is_valid_query(self, query: str) -> bool:
        """Basic validation of SQL query"""
        if not query:
            return False
        
        # Check for obviously invalid patterns
        if query.lower().startswith('error'):
            return False
        
        # Should contain SELECT
        if not query.upper().startswith('SELECT'):
            return False
        
        # Should not have DROP, DELETE, UPDATE, INSERT (security)
        dangerous = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'TRUNCATE']
        for keyword in dangerous:
            if keyword in query.upper():
                logger.warning(f"Dangerous keyword detected: {keyword}")
                return False
        
        return True
