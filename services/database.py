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

        Keeps one persistent Snowflake connection alive for the app's
        lifetime rather than reconnecting per-request. That connection
        can go stale after the app has been running a while (session
        timeout, idle disconnect). This detects that, reconnects once,
        and retries the query before giving up - the user should never
        see a stale-connection failure as a false 'no data found'.
        """
        return self._execute_with_retry(query, timeout, allow_retry=True)

    def _execute_with_retry(self, query: str, timeout: int, allow_retry: bool) -> Optional[List[Dict[str, Any]]]:
        cursor = None
        try:
            if not self.connection:
                self._connect()

            cursor = self.connection.cursor(DictCursor)

            start_time = time.time()

            logger.info(f"Executing query: {query[:100]}...")
            cursor.execute(query)

            results = cursor.fetchall()

            elapsed = time.time() - start_time
            logger.info(f"Query completed in {elapsed:.2f} seconds. Results: {len(results)} rows")

            if elapsed > 60:
                logger.warning(f"Query took {elapsed:.2f} seconds (exceeded 60s threshold)")

            return results

        except (snowflake.connector.errors.DatabaseError,
                snowflake.connector.errors.OperationalError) as e:
            if allow_retry:
                logger.warning(
                    f"Query failed, likely a stale connection ({str(e)[:150]}). "
                    f"Reconnecting and retrying once..."
                )
                if cursor:
                    try:
                        cursor.close()
                    except Exception:
                        pass
                try:
                    self._connect()
                    return self._execute_with_retry(query, timeout, allow_retry=False)
                except Exception as reconnect_error:
                    logger.error(f"Reconnect attempt also failed: {str(reconnect_error)}")
                    return None
            logger.error(f"Database error executing query (after retry): {str(e)}")
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
                except Exception:
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
