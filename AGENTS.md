# OpenFitKit development

OpenFitKit is a small, reusable starter for general fitness and healthier lifestyle
apps. Preserve its general fitness focus: movement, strength, aerobic fitness,
mobility, everyday fueling, sleep, recovery, and sustainable habits. The shared
coaching contract is in `src/openfitkit/prompts.py`.

The shipped live adapter uses OpenRouter and one selected model per coaching turn.
Keep provider credentials on the server. The UI starts with fitness focus cards;
choosing a card prepares an editable request and must not send it automatically.
Preserve the validated focus and fitness scope through conversational follow-ups.

Keep the starter easy to understand. Favor a small working example and clear
extension points over copying a full application. Domain-specific programming,
multi-coach workflows, document retrieval, authentication, and public deployment
are extensions a developer can choose to build separately.

Use the existing checkout. No additional worktree is needed. Install with
`uv sync --locked`, verify with `uv run pytest`, and build with `uv build`.
Use a temporary `OPENFITKIT_DATA_DIR` for smoke tests. The default provider is an
offline demonstration, never evidence of live model access. Tests use injected
providers or HTTP mocks; do not make paid API calls automatically.

Keep API keys, personal profiles, conversations, and local databases out of Git.
Credentials come from the server environment and must never appear in public
settings, errors, browser assets, or logs. Preserve TLS verification and do not
retry paid generation automatically. Keep the default server on loopback.

The SQLite example stores one person's data. Document changes to context selection
or reset semantics. New chats must not attach other conversations automatically.
