"""A runnable offline example of replacing the provider without changing the service."""

from dataclasses import replace

import uvicorn

from openfitkit.app import create_app
from openfitkit.providers import DemoProvider
from openfitkit.settings import Settings


class HabitExample(DemoProvider):
    model = "habit-example"

    def generate(self, *, instructions: str, messages: list[dict[str, str]]) -> str:
        return (
            "Custom provider example — fixed offline text, not personalized guidance.\n\n"
            "Your app could help a user choose one manageable activity, record how it felt, "
            "and review consistency at the end of the week.\n\n"
            "Replace this function with your own coaching implementation."
        )


if __name__ == "__main__":
    settings = Settings.from_env()
    # This example explicitly stays offline even if live environment variables exist.
    settings = replace(settings, provider="demo", model="", api_key="")
    print(f"OpenFitKit custom offline example: http://127.0.0.1:{settings.port}")
    uvicorn.run(create_app(settings, provider=HabitExample()), host="127.0.0.1", port=settings.port, access_log=False)
