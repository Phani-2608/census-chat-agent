# Development Reflection: US Census Chat Agent

## Development Process & Key Architectural Decisions

### Initial Build

I started with a standard layered architecture: a Flask backend, a `ChatService` for
conversation logic, a `QueryGenerator` for translating natural language into SQL, a
`DataValidator` for input/topic checking, and a `SnowflakeDB` connector for executing
queries. The initial version used a simplified, assumed schema (clean tables like
`DEMOGRAPHICS` with columns like `total_population`) so I could get the full
request/response pipeline working end-to-end before touching real data.

This was a deliberate choice: build the "skeleton" first with a schema I controlled,
verify the architecture (multi-turn context, off-topic filtering, error handling) works
in isolation, and only then plug in the real, messier data source. In hindsight this was
the right call, because the real data turned out to be significantly more complex than
the assumed schema, and I would have been debugging the architecture and the data at the
same time otherwise.

### Connecting to Real Data: The Actual Schema Was Very Different

Once I got the Snowflake Marketplace data added to my account (the "SafeGraph US Open
Census Data" listing), I discovered the real structure was nothing like what I'd assumed:

- Data lives at the **Census Block Group** level (a small geography, smaller than a zip
  code), not clean state-level rows.
- Population numbers are in columns with cryptic official Census Bureau codes like
  `B01001e1` (Total population estimate) - there's no column literally called
  "population."
- To answer "population of California," you have to join through a separate
  `2020_METADATA_CBG_FIPS_CODES` table that maps 2-letter state abbreviations to numeric
  FIPS codes, then filter block groups whose ID starts with that number and sum.

I found this by running a series of diagnostic queries directly in a Snowflake worksheet
(`SHOW DATABASES`, `SHOW SCHEMAS IN DATABASE`, `SHOW TABLES IN SCHEMA`, `DESCRIBE TABLE`),
rather than guessing. This mirrors the assignment's own tip about needing "comprehensive
mapping... particularly the metadata and join tables" - that turned out to be the crux of
the whole assignment, not just a nice-to-have.

I rewrote the schema context fed to Claude for query generation to reflect this real
structure, including an explicit worked example of the state-population join pattern,
since that's the single most common question type.

### Why LLM-Generated SQL Instead of Hand-Coded Rules

I stuck with my original decision to have Claude generate SQL directly, now that I'd
seen how gnarly the real schema was - hand-coded rules would have required writing
custom logic for every phrasing of every question. Giving Claude the real schema plus a
worked join pattern let it generalize to variations I didn't explicitly test for (e.g.
it correctly handled "pop of florida" - sloppy phrasing - without any special-casing).

### Graceful Degradation: A Real Design Flaw I Found and Fixed

While debugging a Snowflake connection issue, I discovered the app had a serious
resilience problem: if Snowflake was unreachable for *any* reason at startup, the whole
Flask app refused to start at all - not just the features that need the database, but
literally every request, including the health check. I confirmed this against the
assignment's explicit tip ("Implement error handling that explains why something failed
rather than letting the app crash or hang") and redesigned it: the app now always starts,
lazily retries the connection on each request if it's not ready, and returns a clear
"having trouble connecting to the data source" message with a 503 status instead of
crashing. I verified this with an actual test (mocking a failed Snowflake connection and
confirming `/health` still returns 200 while `/api/chat` returns a clean 503 instead of
an unhandled exception).

## Real Bugs Found and Fixed (with root causes)

This is the part of the process I think is most worth documenting in detail, since each
one only surfaces with real data and a real deployment - none of these would show up in
a quick demo with fake data run once on a laptop.

1. **Missing Marketplace data.** The "US Open Census Data" listing had to actually be
   added to my Snowflake account from the Marketplace - it wasn't there by default. Fix:
   walked through Marketplace search and "Get" flow.

2. **Assumed schema didn't match reality.** As above - fixed by reverse-engineering the
   real schema with diagnostic SQL and rewriting the query-generation prompt.

3. **Case-sensitive column identifiers.** Snowflake auto-uppercases unquoted
   identifiers. The real columns use mixed case (`B01001e1`), so an unquoted reference
   silently became `B01001E1` and failed with "invalid identifier." Fix: instructed the
   query-generation prompt to always double-quote these column names.

4. **Outdated hardcoded model name.** The Claude model string I'd started with had been
   retired, returning a 404. Fix: updated to the current model.

5. **Response parsing broke on "thinking" blocks.** Newer Claude models can return a
   thinking block before the text block, and the code assumed `response.content[0]` was
   always the text. Fix: search the content list for the first block with `type ==
   "text"` instead of assuming position.

6. **Stray commentary breaking SQL syntax.** Despite instructions, the model sometimes
   added a sentence of explanation before or after the SQL (e.g. "Based on this
   query..."), and the code sent the whole blob to Snowflake, causing syntax errors.
   Fix: strip everything before the first `SELECT` and everything after the first blank
   line, plus a stronger explicit instruction not to add commentary. This was a
   high-leverage fix - it silently improved reliability across many different question
   types at once, not just the one I was debugging when I found it.

7. **Multi-turn follow-ups misclassified as off-topic.** "What about New York?" doesn't
   contain any census keywords on its own, so the topic filter rejected it even mid-
   conversation. Fix: the filter now considers whether there's prior conversation
   context, and treats short follow-up phrasing ("what about...", "and...") as on-topic
   only when there's real prior context to justify it - verified this doesn't
   accidentally let random off-topic messages through in a fresh conversation.

8. **Local vs. deployed behavior differed - `__main__` guard never runs under
   gunicorn.** The service-initialization code was inside `if __name__ ==
   '__main__':`, which works when you run `python app.py` directly but is never
   executed when a production server like gunicorn *imports* the module instead of
   running it directly. This meant the deployed app had `chat_service = None` for
   every single request. Fix: moved initialization to module level. This is exactly the
   kind of "deployment truth" gap the assignment's tips called out, and it's a genuinely
   common real-world gotcha.

9. **Trailing whitespace corrupted an environment variable.** A stray tab character
   appended to `SNOWFLAKE_USER` when it was set via a shell loop caused authentication
   to fail, even though the visible value looked correct. Found by comparing column
   alignment in `railway variable list` output. Fix: re-set the variable directly.

10. **Account lockout from repeated failed logins during debugging**, compounded by the
    fact that gunicorn was spawning 4 worker processes that each independently tried to
    connect at startup - meaning every deploy attempt made 4 login attempts instead of
    1. Fix: reduced to a single worker (appropriate for this app's scale anyway) and
    waited for Snowflake's lockout to clear.

## What I Would Improve With More Time

1. **Broader data coverage.** The app currently only "knows" about the core population
   table (`2020_CBG_B01`). Questions about income, race, education, or housing correctly
   fail with an honest "I can't answer that" rather than hallucinating, but they should
   work. I'd extend the schema context to include the other `2020_CBG_*` tables and use
   the `2020_METADATA_CBG_FIELD_DESCRIPTIONS` table to let Claude look up unfamiliar
   column codes dynamically instead of needing every table hardcoded into the prompt.

2. **Ambiguous same-named counties/places across states.** I fixed the "Springfield"
   case (city/town names aren't supported at all, and the app now says so clearly), but
   there are also counties with the same name in different states (e.g. multiple
   "Washington County"s) that could still produce a wrong or arbitrary answer if the
   state isn't specified. I'd add a disambiguation step that asks a clarifying question
   when a county name matches multiple states.

3. **Connection handling.** The Snowflake connection is currently a single global
   object shared across a request cycle. Under real concurrent load this isn't safe. I'd
   move to a proper connection pool.

4. **Persistent session storage.** Conversation history is stored in Flask's cookie-
   based session, which is fine for this evaluation but won't survive an app restart or
   scale across multiple server instances. I'd move this to Redis.

5. **Caching.** Repeated identical questions (e.g. multiple reviewers asking "population
   of California") currently re-run the full LLM + Snowflake round trip every time. A
   simple cache keyed on the generated SQL would cut cost and latency.

6. **Rate limiting**, since the app is now public and nothing currently stops repeated
   automated requests from running up the Anthropic API bill.

## Edge Cases / Failure Modes Identified But Not Fully Addressed

- City/town names are explicitly unsupported and the app says so - but it doesn't try
  to guess a likely state even when context might make it obvious (e.g. if the user
  already said "in Illinois" a message earlier).
- Non-population census categories (income, race, housing) fail gracefully but aren't
  implemented.
- Prompt injection defenses are keyword-based and not exhaustive - a sufficiently
  creative adversarial prompt could likely bypass the topic filter. I did not have time
  to test this rigorously.
- No caching or rate limiting, as noted above - the public URL currently has no
  protection against being hammered with requests.
- Very long conversations are truncated to the last 20 messages in session storage, but
  I didn't test what happens right at that boundary during an active multi-turn
  exchange.

## Testing Approach

### What I Tested

The included unit tests (`tests/test_validators.py`) cover the input validation layer -
on-topic/off-topic classification, length limits, and blocked-pattern detection. This was
the highest-value place to start because it's the first line of defense and the easiest
to test without external dependencies.

Beyond the formal test suite, I did extensive **manual, scenario-based testing** against
the live app and live data, including:
- State, county, and national-level population lookups, including sloppy phrasing
  ("pop of florida")
- Multi-turn follow-ups ("what about New York?")
- Off-topic rejection, both in a fresh conversation and mid-conversation
- Fictional/nonexistent places ("Wakanda")
- Unsupported categories (income, race)
- Ambiguous city names (Springfield)
- A simulated Snowflake outage, to verify graceful degradation actually works rather
  than just assuming it does

I'd consider this manual pass closer to informal integration/acceptance testing than
unit testing, and it's genuinely what caught most of the real bugs listed above - the
unit tests, by contrast, all still pass and never would have caught any of them, since
they don't touch the LLM or database integration at all.

### What I Would Add

1. **Integration tests with a mocked Snowflake connection and mocked Claude responses**,
   specifically covering the failure modes I found manually today: a response with
   stray commentary around the SQL, a response using unquoted mixed-case columns, a
   `ThinkingBlock`-first response, and a failed DB connection at startup.
2. **A regression test for the multi-turn context bug** - assert that a short follow-up
   is accepted when prior context exists and rejected when it doesn't.
3. **A test that starts the app with a deliberately broken DB config** and asserts
   `/health` still returns 200 while `/api/chat` returns 503, to lock in the graceful
   degradation behavior going forward.
4. **Load/concurrency tests**, since I only ever tested with a single user (myself) and
   the connection-pooling gap noted above is a real risk under concurrent load.

## Summary

The most significant part of this project wasn't the initial build - it was the gap
between "works with an assumed schema on my laptop" and "works with the real Marketplace
data, deployed publicly, for a user who isn't me." Every bug listed above only appeared
once I moved past a clean, controlled first pass and into the real environment: the real
Snowflake schema, a real cloud deploy, a real account lockout, and real edge-case
questions. I think that gap - and having a concrete, methodical process for closing it
(read the actual logs, form a specific hypothesis, verify the fix before handing it off,
retest) - is the most representative part of this submission.
