import snowflake.connector
from snowflake.connector import DictCursor
import os
import logging
from typing import List, Dict, Any, Optional
import time

logger = logging.getLogger(__name__)

class SnowflakeDB:
    def __init__(self):
        self.config = {
            'user': os.getenv('SNOWFLAKE_USER'),
            'password': os.getenv('SNOWFLAKE_PASSWORD'),
            'account': os.getenv('SNOWFLAKE_ACCOUNT'),
            'warehouse': os.getenv('SNOWFLAKE_WAREHOUSE', 'COMPUTE_WH'),
            'database': os.getenv('SNOWFLAKE_DATABASE', 'CENSUS_DATA'),
            'schema': os.getenv('SNOWFLAKE_SCHEMA', 'PUBLIC'),
        }
        
        # Validate required config
        required_keys = ['user', 'password', 'account']
        missing = [k for k in required_keys if not self.config[k]]
        if missing:
            raise ValueError(f"Missing Snowflake configuration: {', '.join(missing)}")
        
        self.connection = None
        self._connect()
    
    def _connect(self):
        """Establish connection to Snowflake"""
        try:
            self.connection = snowflake.connector.connect(**self.config)
            logger.info("Connected to Snowflake successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Snowflake: {str(e)}")
            raise
    
    def execute_query(self, query: str, timeout: int = 60) -> Optional[List[Dict[str, Any]]]:
        """
        Execute SQL query with timeout.
        Returns list of dictionaries or None if query fails.
        """
        cursor = None
        try:
            if not self.connection:
                self._connect()
            
            cursor = self.connection.cursor(DictCursor)
            
            # Set query timeout
            start_time = time.time()
            
            logger.info(f"Executing query: {query[:100]}...")
            cursor.execute(query)
            
            # Fetch results
            results = cursor.fetchall()
            
            elapsed = time.time() - start_time
            logger.info(f"Query completed in {elapsed:.2f} seconds. Results: {len(results)} rows")
            
            # Check if query exceeded timeout
            if elapsed > 60:
                logger.warning(f"Query took {elapsed:.2f} seconds (exceeded 60s threshold)")
            
            return results
            
        except snowflake.connector.errors.DatabaseError as e:
            logger.error(f"Database error executing query: {str(e)}")
            return None
        except snowflake.connector.errors.ProgrammingError as e:
            logger.error(f"Query syntax error: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error executing query: {str(e)}", exc_info=True)
            return None
        finally:
            if cursor:
                try:
                    cursor.close()
                except:
                    pass
    
    def test_connection(self) -> bool:
        """Test if database connection is working"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True
        except Exception as e:
            logger.error(f"Connection test failed: {str(e)}")
            return False
    
    def close(self):
        """Close database connection"""
        try:
            if self.connection:
                self.connection.close()
                logger.info("Closed Snowflake connection")
        except Exception as e:
            logger.error(f"Error closing connection: {str(e)}")
    
    def __del__(self):
        """Cleanup when object is destroyed"""
        self.close()
