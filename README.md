# OpenFitKit

A small, open-source starter for developers building **general fitness and healthier lifestyle apps**. Clone it, run a working example, then add your own coaching approach, features, and visual identity.

The foundation covers everyday movement, strength, aerobic fitness, mobility, fueling habits, sleep, and recovery. It is inspired by the lessons from gamesCoach, with an independent codebase and a much smaller starting point.

## Run the starter

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
git clone https://github.com/codecompadre/OpenFitKit.git
cd OpenFitKit
uv sync --locked
uv run openfitkit
```

Open `http://localhost:8766` if the browser does not open automatically. Keep the terminal running; Ctrl+C stops the server. On Ubuntu/WSL, you can use your Windows browser. `--no-browser` prints the address without opening it; `--port 8767` changes the local port.

**The default provider is an offline demo.** It returns a fixed, labeled example and makes no API requests, even when other AI keys exist in your environment. It does not interpret your message or personalize its sample.

## What you get

- A guided fitness home: choose movement, strength, fueling, recovery, or habits, then describe the next step you need.
- Editable requests, conversational follow-ups, saved guidance, and a profile editor.
- One OpenRouter connection and one selected model. Each generated live reply makes one model request.
- A permanent fitness and healthy habits scope, with focused coaching instructions you can adapt.
- Small validated domain models and a local SQLite storage example.
- Explicit conversation context, a fresh-start control, and confirmed history/profile resets.
- Offline tests, a dependency lockfile, a buildable Python package, and GitHub CI configuration.

This is a local, single-user starter. Features such as habit tracking, workout logging, dashboards, file retrieval, multiple coaches, accounts, and public hosting are extension work. The original gamesCoach competition workflow and PDF system are not bundled.

## Make it your app

Start with these files:

| Change | Where |
| --- | --- |
| Coaching style and fitness focus | [`prompts.py`](src/openfitkit/prompts.py) |
| User profile and request fields | [`models.py`](src/openfitkit/models.py) |
| AI connection or your own coaching implementation | [`providers.py`](src/openfitkit/providers.py) |
| Context selection and coaching flow | [`service.py`](src/openfitkit/service.py) |
| Branding, layout, and interactions | [`static/`](src/openfitkit/static/) |
| Persistence | [`storage.py`](src/openfitkit/storage.py) |
| HTTP endpoints | [`app.py`](src/openfitkit/app.py) |

The [customization guide](docs/CUSTOMIZE.md) walks through adding a profile field, changing the provider, and extending the UI. A [small custom-provider example](examples/custom_provider.py) demonstrates the seam without introducing a plugin framework.

To build an independent project, clone into your own folder, change the Git remote to your repository, and update the package metadata and branding. The MIT license permits modification and redistribution with its notice retained.

## Optional live coaching

**OpenRouter is the only included live connection.** Choose a model available to your OpenRouter account and use an OpenRouter API key. There is no dual-coach discussion or separate OpenAI/Gemini key setup. OpenFitKit sends one generation request per accepted coaching turn and does not retry paid requests automatically. OpenRouter handles upstream routing according to its service and your account settings.

```bash
cp .env.example .env
# Edit .env locally: set OPENFITKIT_PROVIDER=openrouter,
# OPENFITKIT_MODEL to your chosen publisher/model ID, and OPENROUTER_API_KEY.
uv run --env-file .env openfitkit
```

`uv --env-file` explicitly loads that local file; the application does not load `.env` itself. You can export the same variables from your shell or configure them through your environment instead.

| Variable | Default / meaning |
| --- | --- |
| `OPENFITKIT_PROVIDER` | `demo`; choose `openrouter` for live requests |
| `OPENFITKIT_MODEL` | Required for live mode; exact OpenRouter `publisher/model` ID, including any supported alias |
| `OPENROUTER_API_KEY` | Required for live mode; read by Python, never exposed to the browser |
| `OPENFITKIT_DATA_DIR` | Private app directory outside the checkout |
| `OPENFITKIT_PORT` | `8766` |

Choose and check your model at [OpenRouter's model catalog](https://openrouter.ai/models). Live requests send your profile, selected fitness focus, and current conversation context to OpenRouter; usage is billed through your OpenRouter balance. Web subscriptions and existing credits with other providers are separate. Tests use mocks, so passing tests do not establish live account access or model availability.

For existing installations, `OPENFITKIT_API_KEY` remains a fallback only when you explicitly choose `openrouter`; `OPENROUTER_API_KEY` takes precedence. Use an OpenRouter key for either variable. The former `openai` provider is rejected with migration instructions rather than silently changing where your data goes. Saved conversations from another provider or model remain readable; start fresh to use a different connection.

The coach stays within fitness and healthier daily habits. A small local guard redirects clearly unrelated tasks before an API call, and the shared coaching prompt handles broader scope decisions and requests for clarification. These controls reduce scope drift; they are not a guarantee of model behavior or a substitute for reviewing generated advice.

## Context and local data

A new conversation starts with your **current saved profile and no previous conversations**. A follow-up uses up to six recent complete exchanges from that thread, within a 24,000-character history budget, plus your latest message and profile. The page tells you when earlier messages were omitted from a request. The full conversation remains saved.

There is no inferred cross-chat memory, model training, or background summarization. Edit the profile to change the lasting context supplied on future requests. Input is limited to 8,000 characters; longer pasted text stays in the composer and is blocked from sending until shortened. Enter sends; Shift+Enter adds a line.

Use **Your data** for memory controls, and **Saved guidance** to reopen a session:

| Action | Effect |
| --- | --- |
| Start fresh | Keep saved data; start without another thread's messages |
| Clear conversations | Delete all conversation records and keep the profile |
| Clear all local data | Delete conversation records and reset the profile |

Deletion requires typing `RESET`. These controls clear app records; they do not remove provider-side records, backups, or API key configuration. A failed storage write returns the generated answer with a copy warning and blocks further sends in that unsaved thread.

Data is stored as unencrypted SQLite in `OPENFITKIT_DATA_DIR`, or `$XDG_DATA_HOME/openfitkit`, or `~/.local/share/openfitkit`. New app directories and database files use private permissions where supported. `.env` and SQLite files are ignored by Git. Put personal data outside the checkout and review staged files before committing.

The server binds to loopback and checks local origins and a per-process request token. Before making a public or multi-user product, design authentication, per-user data isolation, deployment security, data retention, migrations, and operating procedures for that product. This example does not supply those production capabilities.

## Develop and contribute

```bash
uv sync --locked
uv run pytest
uv build
```

Tests use temporary storage and simulated providers, with no API keys or paid requests required. CI is configured for Python 3.11 and 3.13. See [CONTRIBUTING.md](CONTRIBUTING.md) for the contribution workflow and [AGENTS.md](AGENTS.md) for coding-agent guidance.

Keep reusable foundations small. App-specific features can be built in your own project; improvements to the starter should include focused tests and clear extension points. Coaching should remain within general fitness and healthy lifestyle support, with honest capability descriptions and appropriate boundaries around medical issues.

## License

[MIT](LICENSE) · Copyright 2026 Daniel Suarez.
