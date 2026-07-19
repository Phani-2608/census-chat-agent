# US Census Chat Agent

A production-quality chat agent that answers natural language questions about US population data, backed by live Census Bureau data on Snowflake and Claude for query generation.

**Live demo:** https://census-chat-agent-production-532b.up.railway.app
No login required, no credentials needed.

---

## Quick Start (Evaluating This Submission)

Just open the live demo link above and start asking questions. Some good ones to try:

- "What is the population of California?"
- "How many people live in Texas?"
- "What about New York?" (tests multi-turn context)
- "What's the population of Washington County?" (tests ambiguous-location handling)
- "What's the population of Springfield?" (tests unsupported city-level handling)
- "Tell me a joke" (tests off-topic guardrails)

No setup required to evaluate the running app. To run it locally instead, see [Local Setup](#local-setup) below.

---

## Architecture

```
┌─────────────────────────────────────┐
│  Frontend (HTML/CSS/JS)              │
│  Chat UI, session-based history      │
└────────────┬──────────────────────────┘
             │
┌────────────▼──────────────────────────┐
│  Flask Backend (app.py)                │
│  /api/chat  /api/reset  /api/history   │
│  /health                               │
└────────────┬──────────────────────────┘
             │
┌────────────▼──────────────────────────┐
│  ChatService                           │
│  - Multi-turn conversation             │
│  - Answerability pre-check             │
│  - Response synthesis                  │
└──────┬──────────────────┬──────────────┘
       │                  │
┌──────▼─────────┐  ┌─────▼──────────────┐
│ QueryGenerator  │  │ DataValidator      │
│ NL -> SQL via   │  │ Context-aware      │
│ Claude, schema- │  │ topic filtering,   │
│ aware, handles  │  │ input sanitization │
│ ambiguity       │  │                    │
└──────┬──────────┘  └────────────────────┘
       │
┌──────▼──────────────────────────────────┐
│ SnowflakeDB                              │
│ Connection mgmt, timeout tracking,       │
│ lazy reconnect on failure                │
└──────┬────────────────────────────────────┘
       │
US_OPEN_CENSUS_DATA__NEIGHBORHOOD_INSIGHTS__FREE_DATASET
(SafeGraph Open Census Data, via Snowflake Marketplace)
```

## The Real Data Schema

This is the part that took the most real investigation, and it's worth documenting
explicitly because the actual schema is very different from what a quick glance at
"US Census data" might suggest.

**Database:** `US_OPEN_CENSUS_DATA__NEIGHBORHOOD_INSIGHTS__FREE_DATASET`, schema `PUBLIC`

**Key tables actually used:**

- **`2020_CBG_B01`** - population data at the Census Block Group level (a small
  geography, smaller than a zip code). Columns use official Census Bureau codes like
  `"B01001e1"` (total population estimate) - note the **mixed case**, which matters:
  Snowflake auto-uppercases unquoted identifiers, so every reference to these columns
  must be double-quoted or it silently breaks.
- **`2020_METADATA_CBG_FIPS_CODES`** - maps 2-letter state abbreviations (`STATE`) and
  numeric codes (`STATE_FIPS`, `COUNTY_FIPS`) to real county names. This is the join
  table that makes "population of California" answerable at all, since the population
  table itself only has a 12-digit `CENSUS_BLOCK_GROUP` code, not a state name.
- **`2020_METADATA_CBG_FIELD_DESCRIPTIONS`** - translates cryptic column codes (like
  `B01001e1`) into human descriptions (`Sex By Age`, `Total population`, `Estimate`).

To answer "population of California," the generated SQL converts the state name to its
2-letter abbreviation, looks up the numeric FIPS prefix, then sums population across
every block group whose ID starts with that prefix. This join pattern is given to
Claude explicitly in the schema context (see `services/query_generator.py`) rather than
being hardcoded as a fixed query template, so it generalizes to counties and other
phrasings without needing a rule for every variant.

I only wired up the core population table (`2020_CBG_B01`). The dataset also has
income, race, education, and housing tables (`2020_CBG_B19`, `2020_CBG_B02`, etc.) that
follow the same pattern but aren't connected yet - see [Known Limitations](#known-limitations).

## Key Design Decisions

### LLM-generated SQL instead of hand-coded rules
Given how irregular the real schema turned out to be (cryptic Census Bureau column
codes, a required join through a metadata table just to resolve a state name), hand-
coded query templates would have required a new rule for every phrasing. Giving Claude
the real schema plus one worked example lets it generalize - it correctly handles sloppy
phrasing ("pop of florida") and follow-ups without any special-casing for those specific
inputs.

### Context-aware topic filtering
The off-topic guardrail doesn't just look at keywords in the current message - it also
considers whether there's an existing census conversation in progress. This was a
deliberate fix after finding that a short, valid follow-up like "What about New York?"
was being rejected as off-topic, since it doesn't contain any census keywords on its
own. The filter now allows short follow-up phrasing ("what about...", "and...") *only*
when there's real prior context to justify it, verified with tests that a fresh
conversation still rejects the exact same phrasing.

### Graceful degradation over fail-fast crashes
Early in deployment, I found the app would refuse to start entirely if Snowflake was
unreachable for any reason (a locked account, a network blip), taking down every
endpoint including the health check - not just the features that need the database.
I redesigned this: the app always starts, lazily retries the database connection on each
request if it's not ready, and returns a clear 503 with a specific message instead of an
unhandled crash. This is covered by an actual test that simulates a failed Snowflake
connection and asserts `/health` still returns 200 while `/api/chat` returns a clean 503.

### Sentinel-based ambiguity handling
Rather than hardcoding a canned message for every ambiguous case, the query generator
can respond with structured sentinels the backend recognizes:
- `ERROR_UNANSWERABLE` - the question isn't about census data at all
- `ERROR_CITY_NOT_SUPPORTED` - the question asks about a city/town, which this dataset
  doesn't have (it only supports state/county geography)
- `CLARIFY: <question>` - the question is genuinely ambiguous (e.g. "Washington County"
  exists in a dozen+ states), and Claude writes the actual clarifying question itself,
  naming real candidate states, rather than a generic "please be more specific."

### Single gunicorn worker in production
Initially deployed with 4 workers, which meant every deploy triggered 4 simultaneous
Snowflake login attempts at startup - this measurably contributed to hitting Snowflake's
account lockout threshold while debugging. Reduced to 1 worker, which is also more
appropriate for this app's actual scale.

## Multi-turn Conversation

Conversation history is stored in the Flask session (cookie-based), capped at the last
20 messages to bound token usage. Each turn is passed to Claude as prior context for
both the answerability check and the SQL generation step, so follow-ups like "what
about the male population there?" correctly resolve to the previously-discussed state.

## Guardrails

- **Off-topic rejection**, context-aware (see above)
- **Input validation** - length limits, empty-message handling, blocked-pattern
  detection for SQL-injection-style strings
- **Query validation** - generated SQL must start with `SELECT` and cannot contain
  `DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, or `TRUNCATE`
- **Output sanitization** - strips any HTML/script tags from responses

## Known Limitations

Documented honestly rather than hidden, per the assignment's emphasis on
self-awareness:

- **Only population data is wired up.** Income, race, education, and housing questions
  correctly fail with a clear "I can't answer that" rather than hallucinating, but
  aren't implemented. The schema-context pattern used for population could be extended
  to these tables with more time.
- **City/town names aren't resolvable at all** (the dataset only has state/county
  geography) - the app explains this clearly rather than guessing, but doesn't attempt
  to infer a likely state from conversation context.
- **Ambiguous county names** (e.g. "Washington County") now trigger a clarifying
  question naming real candidate states, but this relies on Claude's general knowledge
  of US geography rather than a verified lookup against the actual FIPS table - it's
  usually right but isn't guaranteed to name every state that actually has that county
  in this specific dataset.
- **Session storage is cookie-based**, not persistent - conversation history is lost on
  app restart and won't scale across multiple server instances. Redis would be the
  production fix.
- **No rate limiting** on the public endpoint yet.
- **Prompt injection defenses are keyword-based**, not exhaustive.

See `REFLECTION.md` for the full list of bugs found and fixed during development, and
what I'd prioritize next with more time.

## Testing

21 automated tests across 4 files (`tests/`), covering:

- Input validation (length, format, blocked patterns, on/off-topic classification)
- **Regression test for the multi-turn context bug** - asserts a follow-up is accepted
  with prior context and rejected without it
- **Regression test for graceful degradation** - simulates a failed Snowflake
  connection and asserts the app still starts and responds cleanly

Run with:
```bash
python3 -m pytest tests/ -v
```

Beyond the automated suite, I did extensive manual/scenario testing against the live
app and live data - state/county/national lookups, sloppy phrasing, multi-turn
follow-ups, fictional places, unsupported categories, ambiguous locations, and an actual
simulated database outage. This is where most of the real bugs were found; see
`REFLECTION.md` for the full list and what I'd add to the automated suite with more
time.

## Local Setup

```bash
git clone <this-repo>
cd census-chat-agent
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# fill in .env with your Snowflake + Anthropic credentials
python3 app.py
# open http://localhost:5000
```

### Environment Variables

```
SNOWFLAKE_USER=
SNOWFLAKE_PASSWORD=
SNOWFLAKE_ACCOUNT=
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
SNOWFLAKE_DATABASE=US_OPEN_CENSUS_DATA__NEIGHBORHOOD_INSIGHTS__FREE_DATASET
SNOWFLAKE_SCHEMA=PUBLIC
ANTHROPIC_API_KEY=
FLASK_SECRET_KEY=
```

Note: the Snowflake database name above is the exact name the "US Open Census Data &
Neighborhood Insights - Free Dataset" listing lands as once added from Marketplace -
this took some digging to find, since it's not obvious from the listing name alone
(see `REFLECTION.md` for how it was found).

## Deployment

Deployed on Railway (switched from an initial Heroku attempt, which now requires
credit card verification even for free-tier apps). `Procfile` runs a single gunicorn
worker:

```
web: gunicorn -w 1 -b 0.0.0.0:$PORT app:app
```

One deployment-specific bug worth calling out: service initialization originally lived
inside `if __name__ == '__main__':`, which works fine with `python3 app.py` locally but
never executes under gunicorn (which imports the module rather than running it
directly) - this meant the deployed app had `None` for every service on every request
until it was moved to module level. See `REFLECTION.md` for the full debugging story.

## File Structure

```
census-chat-agent/
├── app.py                    # Flask entrypoint, routes, graceful degradation
├── Procfile                  # Railway/Heroku start command
├── requirements.txt
├── .env.example
├── services/
│   ├── chat_service.py       # Conversation orchestration, answerability check
│   ├── query_generator.py    # NL -> SQL via Claude, real schema context
│   ├── database.py           # Snowflake connection + query execution
│   └── data_validator.py     # Context-aware topic filtering, input validation
├── utils/
│   └── error_handler.py
├── templates/
│   └── index.html            # Chat UI
├── tests/
│   ├── test_validators.py
│   ├── test_query_generator.py
│   ├── test_context_aware_topic_filter.py
│   └── test_graceful_degradation.py
└── REFLECTION.md             # Full development process, bugs found, tradeoffs
```

## What I'd Do With More Time

See `REFLECTION.md` for the complete list. Top priorities: extend schema coverage to
income/race/housing tables, add a connection pool instead of a single global Snowflake
connection, move session storage to Redis, and add rate limiting to the now-public
endpoint.
