import shutil
import textwrap
from itertools import chain
from typing import IO, Sequence, Callable, T, Any, Self

from rich.align import Align
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from research_mapper.human_in_loop import parse_file_path, parse_selection, parse_yes_no
from research_mapper.models import Evidence


class TerminalUI:
    """
    A wrapper over rich to build a stylised CLI.
    """

    def __init__(self, console_width: int = 100) -> None:
        """
        Initialises the UI.
        :param console_width: the width of the UI
        """
        terminal_width = shutil.get_terminal_size().columns
        self.console = Console(width=terminal_width // 2)

    def print(self, *args, spacing: bool = True, **kwargs) -> None:
        """
        Prints arbitrary content to the console with default spacing below.
        :param args: the content to be printed
        :param spacing: whether a blank space should be included below the content
        :param kwargs: any additional configurations to be forwarded to rich's underlying print()
        :return:
        """
        self.console.print(*args, **kwargs)
        if spacing:
            self.console.print()

    def input(self, *args, spacing: bool = True, **kwargs) -> str:
        """
        Asks for and returns text input from user.
        :param args: any argument to be passed to rich's underlying input()
        :param spacing: whether a blank space should be included after the query for input
        :param kwargs: any keyword argument to be passed to rich's underlying input()
        :return: the raw input from the user
        """
        raw = self.console.input(*args, **kwargs)
        if spacing:
            self.console.print()
        return raw

    def print_welcome(self) -> None:
        """
        Prints the application's welcome message.
        :return: Nothing.
        """
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

    def print_evidence(self, evidence: list[Evidence]) -> None:
        """
        Prints collections of Evidence objects cleanly to terminal.
        :param evidence: collection of evidence objects to print
        :return: Nothing.
        """
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

    def print_info(self, message: str) -> None:
        """
        Prints a piece of content to terminal.
        :param message: content message to print
        :return: Nothing.
        """
        self.print(f"{message}")

    def print_process_status(
        self,
        process: Callable[..., Any],
        status_message: str,
        *args,
        complete_message: str | None = None,
        **kwargs,
    ) -> Any | None:
        """
        Runs a process behind a pretty animation of spinner indicating an ongoing operation.
        :param process: the function/process to trigger/execute
        :param status_message: the message to display by the animated spinner
        :param args: any arguments that need forwarding to the callable process/function to be ran
        :param complete_message: an optional message to print to terminal once process completes
        :param kwargs: any keyword arguments that need forwarding to the callable process/function to be ran
        :return: whatever the process/function to be ran returns
        """
        with self.console.status(f"{status_message}\n"):
            outputs = process(*args, **kwargs)
        if complete_message is not None:
            self.print_info(complete_message)
        return outputs

    def prompt_user(self, message: str | None = None) -> str:
        """
        Prettified way of querying for user input.
        :param message: the message to display to the user when prompting for input
        :return: the user's input
        """
        if message is not None:
            self.print_info(message)
        prompt = self.input("[dim]❯[/dim] ")
        return prompt

    def prompt_file_export(
        self,
        writer: Callable[[IO[str]], None],
        default_filename: str = "results.ris",
        label: str = "Export results to a file?",
    ) -> None:
        """
        Prompts the user to optionally export results to a file using the provided writer.
        :param writer: a callable that writes content to an open file handle
        :param default_filename: the filename to use when the user provides no path
        :param label: the prompt shown when asking whether to export
        :return: Nothing.
        """
        self.console.rule()
        while True:
            raw = self.input(f"[dim]{label} [y/N]:[/dim] ", spacing=False)
            try:
                confirmed = parse_yes_no(raw, default=False)
                break
            except ValueError as e:
                self.print_info(f"[red]{e}[/red]")

        if not confirmed:
            return

        raw_path = self.input(
            f"[dim]Output path [{default_filename}]:[/dim] ", spacing=False
        )
        path = parse_file_path(raw_path, default=default_filename)

        try:
            with path.open("w", encoding="utf-8") as f:
                writer(f)
            self.print(f"[green]✓[/green] Exported to {path}")
        except OSError as e:
            self.print_info(f"[red]Failed to write {path}: {e}[/red]")

    def confirm_or_replace(
        self,
        items: Sequence[T],
        title: str | None = None,
        noun: str = "items",
        allow_drop: bool = False,
    ) -> list[T]:
        """
        Lets the user accept a collection of suggested items (each with `name` and
        `description` attributes) outright, or replace/drop each individually by name.
        :param items: the suggested items
        :param title: the title for the table used to display the items
        :param noun: a plural noun describing the items, used in prompts
        :param allow_drop: whether the user may remove items entirely rather than
            keeping or replacing them
        :return: the finalised items, in the same order (minus any dropped items)
        """
        table = Table(title=title, show_header=False, box=None, padding=(0, 1))
        table.add_column(style="bold dim", width=3)
        table.add_column(style="cyan")
        for i, item in enumerate(items, start=1):
            table.add_row(str(i), f"{item.name}\n[dim]{item.description}[/dim]")
        self.print(table)

        while True:
            raw = self.input(f"[dim]Accept these {noun}? [Y/n]:[/dim] ", spacing=False)
            try:
                accepted = parse_yes_no(raw, default=True)
                break
            except ValueError as e:
                self.print_info(f"[red]{e}[/red]")

        if accepted:
            return list(items)

        instructions = "Press Enter to keep, type a new name to replace"
        if allow_drop:
            instructions += ', or "-" to drop'

        finalised = []
        for item in items:
            raw = self.prompt_user(
                f"[dim]Replace '{item.name}'? {instructions}:[/dim]"
            ).strip()
            if allow_drop and raw == "-":
                continue
            finalised.append(type(item)(name=raw, description="") if raw else item)
        return finalised

    def select_from_list(
        self,
        items: Sequence[T],
        label: Callable[[T], str] = str,
        title: str | None = None,
    ) -> list[T]:
        """
        Filters a collection of items via user by asking for the indices of enumerated items to keep.
        :param items: the collection of items to select from
        :param label: a function that returns a label to display for a given item
        :param title: the title for the table used to display the items the user must pick from
        :return: the collection of selected items
        """
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
    """
    A collection of live updating rich Panel objects.
    """

    def __init__(
        self,
        buffers: dict,
        active: dict,
        items: Sequence,
        label: Callable,
        max_lines: int,
        content_width: int,
        status_text: str = "Thinking...",
    ) -> None:
        """
        Initialises with relevant state to manage and update an arbitrary number of live panels.
        :param buffers: the text buffers that will store the text of each live panel
        :param active: a dictionary mapping each item to a boolean representing whether it's still expecting updates
        :param items: the collection of items to each be given a panel
        :param label: a function to be used for generating panel labels
        :param max_lines: the maximum number of lines any one panel should have
        :param content_width: the width of the panels
        :param status_text: the text to be displayed at the top of the live panels
        """
        self._buffers = buffers
        self._active = active
        self._items = items
        self._label = label
        self._max_lines = max_lines
        self._content_width = content_width
        self._status_text = status_text
        self._spinner = Spinner("dots", style="cyan")

    def __rich__(self) -> Group:
        """
        Live updates text in panels using rich's underlying special method called during each update of the console.
        :return: a rich Group object containing all the panels
        """
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
        """
        Wraps text to the content width LivePanelGroup was initialised with.
        :param text: the text to wrap
        :return: the collection of wrapped text
        """
        lines = []
        for paragraph in text.split("\n"):
            lines.extend(textwrap.wrap(paragraph, self._content_width) or [""])
        return lines


class LiveAgentPanels:
    """
    A collection of live panels tailored to displaying streamed responses of DSPy agents and programs.
    """

    def __init__(
        self,
        items: Sequence[T],
        tui: TerminalUI,
        label: Callable[[T], str] = str,
        max_lines: int = 50,
    ) -> None:
        """
        Initialises LiveAgentPanels object with the necessary state to manage and display streamed responses live.
        :param items: the collection of items to each be given a panel
        :param tui: the terminal UI instance to use
        :param label: the function to be used for generating panel labels from items
        :param max_lines: the maximum number of lines any one panel should have
        """
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
        """
        Returns a callback to allow external processes to modify the buffer contents of items.
        :param item: the item to get the callback for
        :return: a callback to append text to the item's buffer
        """

        def append(chunk: str, completed: bool = False) -> None:
            """
            Appends text chunk to buffer contents and updates active status.
            :param chunk: text chunk to append
            :param completed: whether the live process that "owns" the buffer has completed
            :return: Nothing.
            """
            self._buffers[item] += chunk
            if completed:
                self._active[item] = False

        return append

    def __enter__(self) -> Self:
        """
        Wrapper over rich's Live's context manager
        :return: own LiveAgentPanels instance
        """
        self._live.__enter__()
        return self

    def __exit__(self, *args) -> None:
        """
        Wrapper over rich's Live's context manager
        :param args:
        :return: Nothing.
        """
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
