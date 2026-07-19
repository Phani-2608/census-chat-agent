"""
Regression tests for the multi-turn context bug found during manual
testing on 2026-07-18: "What about New York?" was incorrectly rejected
as off-topic because it contains no census keywords on its own, even
though it was clearly a follow-up to a prior census question.
"""
import unittest
from services.data_validator import DataValidator


class TestContextAwareTopicFilter(unittest.TestCase):
    def setUp(self):
        self.validator = DataValidator()

    def test_pop_abbreviation_accepted_as_first_message(self):
        """Regression test for a real bug found via incognito testing:
        'pop of florida' as the very FIRST message in a fresh conversation
        (no context to lean on) was rejected as off-topic, since the
        filter only recognized the full word 'population', not the
        common abbreviation 'pop'. Fixed by adding 'pop' as a whole-word
        synonym with word-boundary matching."""
        self.assertTrue(
            self.validator.is_on_topic("pop of florida", has_context=False)
        )
        self.assertTrue(
            self.validator.is_on_topic("pop of texas", has_context=False)
        )

    def test_pop_abbreviation_does_not_false_positive(self):
        """Word-boundary matching must not let 'pop' match inside
        unrelated words like 'popular' - this is what makes it safe to
        add 'pop' as a short keyword in the first place."""
        self.assertFalse(
            self.validator.is_on_topic("what's popular in movies", has_context=False)
        )

    def test_followup_accepted_with_prior_context(self):
        """The exact bug found in manual testing: a short follow-up
        question should be accepted when there's an ongoing census
        conversation, even without explicit census keywords."""
        self.assertTrue(
            self.validator.is_on_topic("What about New York?", has_context=True)
        )

    def test_followup_rejected_without_prior_context(self):
        """The same phrasing should NOT get a free pass in a fresh
        conversation with no prior context to justify it - otherwise
        the fix would just make the filter permissive for everyone."""
        self.assertFalse(
            self.validator.is_on_topic("What about New York?", has_context=False)
        )

    def test_off_topic_still_rejected_even_with_context(self):
        """Having prior context shouldn't create a loophole that lets
        genuinely off-topic messages through."""
        self.assertFalse(
            self.validator.is_on_topic("tell me a joke", has_context=True)
        )
        self.assertFalse(
            self.validator.is_on_topic("what's the weather like today", has_context=True)
        )

    def test_explicit_census_question_accepted_regardless_of_context(self):
        self.assertTrue(
            self.validator.is_on_topic("What is the population of Texas?", has_context=False)
        )
        self.assertTrue(
            self.validator.is_on_topic("What is the population of Texas?", has_context=True)
        )

    def test_various_followup_phrasings_with_context(self):
        followups = [
            "and Texas?",
            "how about California",
            "what about the male population",
        ]
        for message in followups:
            with self.subTest(message=message):
                self.assertTrue(self.validator.is_on_topic(message, has_context=True))


if __name__ == '__main__':
    unittest.main()
