"""
Tests for QueryGenerator, specifically regression tests for real bugs
found during manual testing and deployment on 2026-07-18/19:

- Claude sometimes adds a sentence of commentary before or after the SQL
  despite being told not to, which broke SQL execution.
- Newer Claude models can return a 'thinking' content block before the
  text block, which broke code that assumed content[0] was always text.
"""
import unittest
import re


def clean_query(query: str) -> str:
    """Mirrors QueryGenerator._clean_query - duplicated here so this test
    has no dependency on the anthropic/snowflake packages being installed."""
    query = re.sub(r'```sql\n?', '', query)
    query = re.sub(r'```\n?', '', query)

    match = re.search(r'\bSELECT\b', query, re.IGNORECASE)
    if match:
        query = query[match.start():]

    if '\n\n' in query:
        query = query.split('\n\n')[0]

    return query.strip()


class FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class FakeThinkingBlock:
    def __init__(self, text="internal reasoning"):
        self.type = "thinking"
        self.text = text


def extract_text(content_blocks):
    """Mirrors the fix for the ThinkingBlock bug - find the first text
    block instead of assuming content[0] is always text."""
    return next(b.text for b in content_blocks if b.type == "text")


class TestQueryCleaning(unittest.TestCase):
    """Regression tests for the 'stray commentary breaks SQL' bug found
    when testing the multi-turn follow-up 'what's the male population
    there?' - Claude appended a trailing sentence and the raw blob was
    sent straight to Snowflake, causing a syntax error."""

    def test_strips_trailing_commentary(self):
        raw = (
            'SELECT SUM(b."B01001e1") AS total_population\n'
            'FROM "DB"."PUBLIC"."2020_CBG_B01" b\n'
            "WHERE LEFT(b.CENSUS_BLOCK_GROUP, 2) = '48'\n"
            "\n"
            "Based on this query, we can determine the total population."
        )
        cleaned = clean_query(raw)
        self.assertNotIn("Based on", cleaned)
        self.assertTrue(cleaned.startswith("SELECT"))
        self.assertTrue(cleaned.rstrip().endswith("'48'"))

    def test_strips_leading_commentary(self):
        raw = (
            "Here's a demographic overview of Texas:\n\n"
            'SELECT SUM(b."B01001e1") AS total_population\n'
            'FROM "DB"."PUBLIC"."2020_CBG_B01" b'
        )
        cleaned = clean_query(raw)
        self.assertTrue(cleaned.startswith("SELECT"))
        self.assertNotIn("Here's", cleaned)

    def test_strips_markdown_fences(self):
        raw = '```sql\nSELECT 1 AS test\n```'
        cleaned = clean_query(raw)
        self.assertEqual(cleaned, "SELECT 1 AS test")

    def test_clean_query_with_no_commentary_is_unchanged(self):
        raw = 'SELECT SUM(b."B01001e1") AS total_population\nFROM "DB"."PUBLIC"."T" b'
        cleaned = clean_query(raw)
        self.assertEqual(cleaned, raw)


class TestThinkingBlockResponseParsing(unittest.TestCase):
    """Regression test for the bug where newer Claude models returned a
    ThinkingBlock as content[0], and response.content[0].text raised
    'ThinkingBlock object has no attribute text'."""

    def test_extracts_text_when_text_is_first_block(self):
        blocks = [FakeTextBlock("SELECT 1")]
        self.assertEqual(extract_text(blocks), "SELECT 1")

    def test_extracts_text_when_thinking_block_comes_first(self):
        blocks = [FakeThinkingBlock(), FakeTextBlock("SELECT 1")]
        self.assertEqual(extract_text(blocks), "SELECT 1")

    def test_extracts_text_with_multiple_thinking_blocks(self):
        blocks = [FakeThinkingBlock(), FakeThinkingBlock(), FakeTextBlock("SELECT 2")]
        self.assertEqual(extract_text(blocks), "SELECT 2")


if __name__ == '__main__':
    unittest.main()
