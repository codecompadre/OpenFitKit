# Build your own app

OpenFitKit gives you a working path from browser input to a coaching response and local storage. Extend one boundary at a time; keep demo mode available while you build.

## 1. Give your coach a purpose

Edit `src/openfitkit/prompts.py`. For example, a walking and strength companion might emphasize consistent movement, simple sessions, and gradual progression. A recovery-focused app might emphasize sleep routines, manageable activity, and habit reflection.

Keep the general fitness and healthy lifestyle focus, the distinction between coaching and medical treatment, and honest claims about available tools. `FOCUS_GUIDANCE` adds trusted guidance for movement, strength, fueling, recovery, and habits. `ChatRequest.focus` validates the selection; the profile and conversation cannot replace this contract. `scope.py` conservatively redirects some clearly unrelated requests before a paid call and normalizes the model's refusal marker. It deliberately allows ambiguous follow-ups to reach the coach for clarification. A prompt and a small local guard do not validate generated advice; review behavior using representative user scenarios before offering a live app to others.

## 2. Extend the profile

Suppose your app needs a preferred activity. Add this field to `Profile` in `models.py`:

```python
preferred_activity: str = Field(default="", max_length=200)
```

Then add a matching control inside the profile form in `static/index.html`:

```html
<label>Preferred activity<input name="preferred_activity" maxlength="200"></label>
```

The client reads the form by field name. Profile serialization, JSON storage, and the coaching context already use the model, so the new value travels through the same path. Add a test showing that it saves, reloads, and reaches your provider. An additive default allows older profiles to load; renaming or removing saved fields requires a data migration plan.

## 3. Replace the AI connection

The provider seam is intentionally small:

```python
class MyProvider:
    name = "my-provider"
    model = "my-model"

    def generate(self, *, instructions: str, messages: list[dict[str, str]]) -> str:
        # Call your SDK, model, or coaching service and return the final text.
        ...
```

The service builds context and stores the completed exchange. The included `OpenRouterProvider` sends one request to OpenRouter using the selected model, with no automatic retry. Configure it through `OPENFITKIT_PROVIDER=openrouter`, `OPENFITKIT_MODEL=publisher/model`, and `OPENROUTER_API_KEY`. Direct OpenAI routing is no longer included; separate OpenAI/Gemini keys are unnecessary for this adapter. The offline demonstration remains the default.

Your own provider translates that request to your chosen API. Keep keys on the server, preserve TLS verification, convert provider failures into safe `ProviderError` messages, and decide explicitly how usage and retries work.

You can add a provider choice in `settings.py` and `build_provider()`, or inject a provider into `create_app(settings, provider=...)`. The [custom-provider example](../examples/custom_provider.py) uses injection and stays offline:

```bash
uv run python examples/custom_provider.py
```

Its sample messages demonstrate an extension point; they are not personalized coaching. Live adapters should identify their real provider and model so old chats cannot silently switch to a different backend.

## 4. Add your visual identity

The UI consists of three files, with no JavaScript build step:

- `static/index.html`: structure, fields, and visible labels.
- `static/styles.css`: colors, typography, spacing, and responsive layout.
- `static/app.js`: API calls and browser state.

Replies render as plain text with preserved line breaks. If you add Markdown, use a maintained renderer with HTML disabled and safe link handling. Keep untrusted user/model text out of `innerHTML`. When replacing this UI with a framework, keep the HTTP contract or adjust `app.py` alongside it.

The initial design starts with five fitness focus cards and an editable request, then supports conversational refinements. Choosing a card prepares the request without sending it. Requests include a validated `focus`; older API clients can omit it for general fitness guidance. Saved guidance, the profile, and confirmed data resets remain available from the header. Rename the starter, change the layout, and add the workflows your users need.

## 5. Build a feature through the boundaries

A habit log is a useful first extension:

1. Define a validated habit-entry model.
2. Add storage methods and a table, with an explicit migration.
3. Add HTTP endpoints that use those methods.
4. Build a UI to create and review entries.
5. Decide whether habit entries enter coaching context, and give the user control over that choice.
6. Include the new data in reset behavior and tests.

Use the same pattern for workout logs, walking goals, recovery check-ins, or other general fitness features. Avoid placing unrelated app logic inside the provider adapter.

## 6. Control context deliberately

`service.py` contains `recent_context()`, `MAX_HISTORY_EXCHANGES`, and `MAX_HISTORY_CHARS`. It selects recent complete exchanges; it never rewrites the saved history. Current profile fields are supplied separately on every request.

Increase or lower these limits to fit the context window, privacy needs, and usage budget of your chosen model. If you add retrieval, summaries, or cross-conversation memory, make the supplied sources visible and preserve a reliable reset path. Do not describe stored context as training the underlying model.

## 7. Evolve persistence and delivery

`storage.py` is a local, single-user SQLite example. You can replace it with a repository backed by your own datastore while retaining the service boundary. Public hosting needs authentication, user ownership checks, isolation, migrations, and deployment configuration appropriate to that application.

Start each smoke test with a temporary `OPENFITKIT_DATA_DIR` so sample interactions do not enter personal history. Run `uv run pytest` and `uv build` after changing an extension point.
