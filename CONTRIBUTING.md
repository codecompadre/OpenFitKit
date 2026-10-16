# Contributing to OpenFitKit

OpenFitKit should remain a small foundation that other developers can understand,
clone, and adapt to general fitness and healthier lifestyle projects.

## Local workflow

1. Fork or clone the repository and create a branch for your change.
2. Install Python 3.11+ and uv, then run `uv sync --locked`.
3. Run `uv run openfitkit --no-browser` to try the offline starter.
4. Add focused tests for changed behavior, using temporary storage and fake providers.
5. Run `uv run pytest` and `uv build` before opening a pull request.

Explain the problem, the resulting behavior, and how you verified it. Describe any
changes to stored data or context selection. Keep general fitness and healthy
lifestyle boundaries intact, with honest descriptions of AI capabilities.

## Scope

Favor reusable primitives, small fixes, accessibility, documentation, and examples.
Keep app-specific programs, competition logic, large dashboards, and specialized
integrations in an extension or downstream project when they would make the
starter harder to follow. Discuss broad architectural changes in an issue first.

## Credentials and personal data

Use simulated providers in tests. Never commit API keys, personal profiles,
conversation databases, or real training records. `.env`, SQLite, and private data
directories are ignored, but review the files you stage. Report security issues
without posting credentials or private user data in a public issue.

## License

Contributions are distributed under the repository's MIT license. Retain existing
copyright notices when adapting the starter for your own project.
