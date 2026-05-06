import shutil
import textwrap
from itertools import chain
from typing import Sequence, Callable, T, Any

from rich.align import Align
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from research_mapper.human_in_loop import parse_selection
from research_mapper.models import Evidence


class TerminalUI:
    def __init__(self, console_width: int = 100):
        terminal_width = shutil.get_terminal_size().columns
        self.console = Console(width=terminal_width // 2)

    def print(self, *args, spacing: bool = True, **kwargs):
        self.console.print(*args, **kwargs)
        if spacing:
            self.console.print()

    def input(self, *args, spacing: bool = True, **kwargs) -> str:
        raw = self.console.input(*args, **kwargs)
        if spacing:
            self.console.print()
        return raw

    def print_welcome(self):
        self.console.print()
        self.print(
            Align.center(
                Panel(
                    Text("Research Mapper", justify="center", style="bold"),
                    subtitle="Mapping evidence from the DESTINY repository",
                    width=self.console.width // 2,
                )
            )
        )

    def print_evidence(self, evidence: list[Evidence]):
        self.console.rule(
            f"[dim]{len(evidence)} result{'s' if len(evidence) != 1 else ''} found[/dim]"
        )
        self.console.print()
        for i, source in enumerate(evidence, 1):
            title = source.title or "Unknown"
            abstract = source.abstract or "—"
            authors = ", ".join(source.authors[:3]) + (
                " et al." if len(source.authors) > 3 else ""
            )
            year = str(source.year) if source.year else ""
            subtitle = " · ".join(filter(None, [authors, year]))
            self.print(
                Panel(
                    f"[dim]{abstract}[/dim]",
                    title=f"[bold][{i}] {title}[/bold]",
                    title_align="left",
                    subtitle=f"[dim]{subtitle}[/dim]" if subtitle else None,
                    border_style="dim",
                    padding=(0, 1),
                )
            )

    def print_info(self, message: str):
        self.print(f"{message}")

    def print_process_status(
        self,
        process: Callable[..., Any],
        status_message: str,
        *args,
        complete_message: str | None = None,
        **kwargs,
    ) -> Any | None:
        with self.console.status(f"{status_message}\n"):
            outputs = process(*args, **kwargs)
        if complete_message is not None:
            self.print_info(complete_message)
        return outputs

    def prompt_user(self, message: str | None = None):
        if message is not None:
            self.print_info(message)
        prompt = self.input("[dim]❯[/dim] ")
        return prompt

    def select_from_list(
        self,
        items: Sequence[T],
        label: Callable[[T], str] = str,
        title: str | None = None,
    ) -> list[T]:
        table = Table(title=title, show_header=False, box=None, padding=(0, 1))
        table.add_column(style="bold dim", width=3)
        table.add_column(style="cyan")
        for i, item in enumerate(items, start=1):
            table.add_row(str(i), label(item))
        self.print(table)

        while True:
            raw = self.prompt_user(
                "[dim]Keep (space-separated numbers, or Enter for all):[/dim] "
            ).strip()
            try:
                return parse_selection(raw, items)
            except ValueError as e:
                self.print_info(f"[red] {e} — try again.[/red]")


class LivePanelGroup:
    def __init__(
        self,
        buffers: dict,
        active: dict,
        items: Sequence,
        label: Callable,
        max_lines: int,
        content_width: int,
        status_text: str = "Thinking...",
    ):
        self._buffers = buffers
        self._active = active
        self._items = items
        self._label = label
        self._max_lines = max_lines
        self._content_width = content_width
        self._status_text = status_text
        self._spinner = Spinner("dots", style="cyan")

    def __rich__(self):
        panels = []
        for item in self._items:
            wrapped = self._wrap(self._buffers[item])
            visible = "\n".join(wrapped[-self._max_lines :])
            active = self._active[item]
            panels.append(
                Panel(
                    visible,
                    title=self._label(item),
                    title_align="left",
                    subtitle="[dim]reasoning...[/dim]"
                    if active
                    else "[green]done[/green]",
                    border_style="cyan" if active else "green",
                    padding=(0, 1),
                )
            )
        spaced = list(chain.from_iterable((p, Text("")) for p in panels))
        n_active = sum(1 for value in self._active.values() if value)
        self._spinner.text = (
            f"{self._status_text} {n_active} subagent(s) still working."
        )
        if any(self._active.values()):
            return Group(
                self._spinner, Text(""), *spaced
            )  # the empty text is for spacing
        return Group(*spaced)

    def _wrap(self, text: str) -> list[str]:
        lines = []
        for paragraph in text.split("\n"):
            lines.extend(textwrap.wrap(paragraph, self._content_width) or [""])
        return lines


class LiveAgentPanels:
    def __init__(
        self,
        items: Sequence[T],
        tui: TerminalUI,
        label: Callable[[T], str] = str,
        max_lines: int = 50,
    ):
        self._buffers = {item: "" for item in items}
        self._active = {item: True for item in items}
        content_width = tui.console.width - 4  # panel borders
        self._live = Live(
            LivePanelGroup(
                self._buffers, self._active, items, label, max_lines, content_width
            ),
            refresh_per_second=10,
            console=tui.console,
        )

    def get_callback_for_buffer(self, item: T) -> Callable[[str, bool], None]:
        def append(chunk: str, completed: bool = False):
            self._buffers[item] += chunk
            if completed:
                self._active[item] = False

        return append

    def __enter__(self):
        self._live.__enter__()
        return self

    def __exit__(self, *args):
        self._live.__exit__(*args)


def LiveAgentPanel(
    item: T, tui: TerminalUI, label: Callable[[T], str] = str
) -> LiveAgentPanels:
    """
    A factory function for producing a single LiveAgentPanel object.
    :param item: the hashable object associated with the panel
    :param tui: the TerminalUI object to write to the terminal with
    :param label: the callable to generate the item's label from
    :return: an instance of LiveAgentPanels with a single item
    """
    return LiveAgentPanels([item], tui, label)
