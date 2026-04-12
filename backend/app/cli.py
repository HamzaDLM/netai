import argparse
import asyncio
import sys

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from app.tools.syslog_tool import syslog_qa_engine

console = Console()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Syslog LLM CLI")
    return parser.parse_args()


async def run_cli() -> None:
    console.print(
        Panel(
            "Ask questions about ingested syslogs. Type [bold]q[/bold] to quit.",
            title="Syslog LLM",
            border_style="cyan",
        )
    )

    while True:
        question = Prompt.ask("Question").strip()
        if question.lower() in {"q", "quit", "exit"}:
            break

        console.print(Panel(question, title="Question", border_style="blue"))

        try:
            result = await asyncio.to_thread(
                syslog_qa_engine.ask,
                question=question,
                top_k=None,
            )
            console.print(Panel(result.answer, title="Answer", border_style="green"))
        except Exception as exc:
            console.print(Panel(str(exc), title="Error", border_style="red"))


def main() -> None:
    try:
        _ = parse_args()
        asyncio.run(run_cli())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
