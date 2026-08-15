# AI provider configuration

JobRadar can score job/profile fit without a paid model. The production default
is `deterministic`: it is reproducible, fast, requires no API key, and provides
a reliable fallback when a remote provider is unavailable.

AI scores are advisory. They compare user-supplied skills, experience,
locations, and salary preferences with job data; they do not make hiring
decisions and must not infer protected traits.

## Quick setup

Set one primary provider and a comma-separated fallback order:

```dotenv
AI_PROVIDER=deterministic
AI_MODEL=jobradar-deterministic-v1
AI_FALLBACK_PROVIDERS=deterministic
AI_TOKEN_BUDGET=700
AI_REQUEST_TIMEOUT_SECONDS=20
AI_MAX_RETRIES=2
```

Only configure the key for a provider you actually enable. Provider keys are
server-only Render/GitHub secrets and must never use a `NEXT_PUBLIC_` prefix.

## Providers

| Provider | `AI_PROVIDER` | Required setting | Repository default model |
| --- | --- | --- | --- |
| Local rules | `deterministic` | none | `jobradar-deterministic-v1` |
| OpenAI | `openai` | `OPENAI_API_KEY` | `gpt-4o-mini` |
| DeepSeek | `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| OpenRouter | `openrouter` | `OPENROUTER_API_KEY` | `openai/gpt-4o-mini` |
| Gemini | `gemini` | `GEMINI_API_KEY` | `gemini-2.0-flash` |
| Local Ollama | `ollama` | `OLLAMA_BASE_URL` | `llama3.2:3b` |

Model names above are code defaults, not availability or pricing guarantees.
Provider catalogues change; set `AI_MODEL` to a currently enabled model in your
account and verify its price and data-retention terms before production use.

### OpenAI

```dotenv
AI_PROVIDER=openai
AI_MODEL=gpt-4o-mini
AI_FALLBACK_PROVIDERS=gemini,deterministic
OPENAI_API_KEY=
```

The adapter uses the provider's JSON chat-completions response. Create a
restricted project key and apply a provider-side monthly budget.

### DeepSeek

```dotenv
AI_PROVIDER=deepseek
AI_MODEL=deepseek-chat
AI_FALLBACK_PROVIDERS=deterministic
DEEPSEEK_API_KEY=
```

### OpenRouter

```dotenv
AI_PROVIDER=openrouter
AI_MODEL=openai/gpt-4o-mini
AI_FALLBACK_PROVIDERS=deterministic
OPENROUTER_API_KEY=
```

OpenRouter routes to third-party model operators. Review the selected model's
operator, data policy, limits, and availability rather than treating the router
as a single privacy boundary.

### Gemini

```dotenv
AI_PROVIDER=gemini
AI_MODEL=gemini-2.0-flash
AI_FALLBACK_PROVIDERS=deterministic
GEMINI_API_KEY=
```

### Ollama

```dotenv
AI_PROVIDER=ollama
AI_MODEL=llama3.2:3b
AI_FALLBACK_PROVIDERS=deterministic
OLLAMA_BASE_URL=http://ollama:11434
```

Ollama is useful for the legacy self-hosted topology. It is not reachable from
Render unless you operate a public, authenticated Ollama service; exposing an
unprotected local Ollama port is unsafe.

## Cost and latency controls

The application applies several controls before a remote response is persisted:

- canonical inputs are hashed with the provider and model version;
- `job_scores` has a unique cache key, so identical work is reused;
- concurrent batch scoring is bounded rather than unbounded;
- input text and list sizes are constrained;
- `AI_TOKEN_BUDGET` caps output tokens;
- the request timeout is bounded to 60 seconds;
- transient 429/5xx/network failures use exponential backoff;
- provider output must satisfy a strict score schema;
- fallback ends at the free deterministic provider.

Recommended free-tier settings:

```dotenv
AI_PROVIDER=deterministic
AI_FALLBACK_PROVIDERS=deterministic
AI_TOKEN_BUDGET=700
AI_REQUEST_TIMEOUT_SECONDS=15
AI_MAX_RETRIES=1
```

When enabling a paid provider, start with a daily scoring limit of 20 per user,
set a hard provider-side spend cap, and inspect token usage before increasing it.
The scheduled pipeline intentionally uses deterministic scoring and bounds its
user/job candidate sets, top recommendations per user, and minimum persisted
score through the `DAILY_RECOMMENDATION_*` settings.

## Fallback behavior

`AI_FALLBACK_PROVIDERS` is evaluated left to right. Duplicate names are
ignored, and `deterministic` is always the final safety net. A provider is
skipped or retried when credentials are missing, the request fails, the service
rate-limits, or returned JSON violates the expected schema.

Example:

```dotenv
AI_PROVIDER=openai
AI_MODEL=gpt-4o-mini
AI_FALLBACK_PROVIDERS=gemini,deterministic
AI_MAX_RETRIES=2
```

This attempts OpenAI, then Gemini, then local deterministic scoring. Production
startup rejects the configuration if an explicitly enabled remote provider does
not have its matching API key.

## Privacy guidance

- CV files and encrypted CV text are private candidate data.
- Send only the minimum fields needed to score a match.
- Never include passwords, tokens, contact lists, or raw Storage credentials in
  a prompt.
- Treat job descriptions as untrusted data; the system prompt explicitly
  prevents job text from becoming instructions.
- Confirm that the chosen provider and region satisfy your retention and
  residency requirements.
- Rotate a provider key immediately if it appears in logs, browser bundles, or a
  commit.

## Verification

With the API running, create a profile and call the job score endpoint twice.
The second successful response should report a cache hit and should not create a
second `job_scores` row for the same input hash. Check structured API logs for
provider/fallback failures without logging the key or full CV content.
