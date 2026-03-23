import argparse
import asyncio
import sys

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from app.workflows.log_qa import LogQAWorkflow

console = Console()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Syslog LLM CLI")
    return parser.parse_args()


async def run_cli() -> None:
    workflow = LogQAWorkflow()

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
            result = await workflow.ask(question=question)
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
