import shutil
from contextlib import contextmanager
from typing import IO, Iterator, Sequence, Callable, T, Any

import dspy
from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from research_mapper.human_in_loop import parse_file_path, parse_selection, parse_yes_no
from research_mapper.models import Evidence, EvidenceMap


class _StageStatusMessageProvider(dspy.streaming.StatusMessageProvider):
    """
    Phrases DSPy's built-in LM/tool callback events as short progress messages, for display on a
    spinner while a single (non-batched) program call is in flight.
    """

    def __init__(self, thinking_message: str = "Thinking...") -> None:
        self._thinking_message = thinking_message

    def lm_start_status_message(self, instance: Any, inputs: dict[str, Any]) -> str:
        return self._thinking_message

    def tool_start_status_message(self, instance: Any, inputs: dict[str, Any]) -> str:
        return f"Calling {instance.name}..."


class _LiveReasoningPanel:
    """
    A single Panel that grows as a program streams its `reasoning` field, for use inside a
    `rich.Live` display. Shows a caller-supplied status message as placeholder text until
    reasoning tokens start arriving.
    """

    def __init__(self, label: str, placeholder: str) -> None:
        self._label = label
        self._placeholder = placeholder
        self._buffer = ""
        self._done = False

    def set_placeholder(self, text: str) -> None:
        """Updates the placeholder shown while no reasoning tokens have arrived yet."""
        self._placeholder = text

    def append(self, chunk: str) -> None:
        """Appends a streamed chunk of reasoning text to the panel's content."""
        self._buffer += chunk

    def finish(self) -> None:
        """Marks the panel as complete, switching it to its resting style."""
        self._done = True

    def __rich__(self) -> Panel:
        content = self._buffer or self._placeholder
        return Panel(
            f"[dim]{content}[/dim]",
            title=f"[bold]{self._label}[/bold]",
            title_align="left",
            subtitle="[green]done[/green]" if self._done else "[dim]reasoning...[/dim]",
            border_style="green" if self._done else "cyan",
            padding=(0, 1),
        )


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

    @contextmanager
    def full_width(self) -> Iterator[None]:
        """
        Temporarily widens the console to the full terminal width, restoring its previous width on
        exit. Useful for wide content (e.g. the evidence map crosstab table) that would otherwise be
        constrained to the UI's default half-width.
        :return: a context manager
        """
        original_size = self.console.size
        terminal_width = shutil.get_terminal_size().columns
        self.console.size = (terminal_width, original_size.height)
        try:
            yield
        finally:
            self.console.size = original_size

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

    def print_evidence_map(self, evidence_map: EvidenceMap) -> None:
        """
        Prints a 2D crosstab of the two dimensions with the fewest subtopics, where each cell lists
        the (1-based) indices of evidence mapped to that combination of subtopics, followed by the
        indexed evidence itself, clustered by the subtopics of the remaining dimension.
        :param evidence_map: the EvidenceMap to display
        :return: Nothing.
        """
        mapped_evidence = evidence_map.mapped_evidence
        row_dim, col_dim, cluster_dim = sorted(
            evidence_map.dimensions, key=lambda d: len(d.subtopics)
        )

        grid: dict[tuple[str, str], list[int]] = {}
        for index, item in enumerate(mapped_evidence, start=1):
            key = (item.coordinate[row_dim.name], item.coordinate[col_dim.name])
            grid.setdefault(key, []).append(index)

        with self.full_width():
            table = Table(title=f"{row_dim.name} × {col_dim.name}")
            table.add_column(row_dim.name, style="bold")
            for col_subtopic in col_dim.subtopics:
                table.add_column(col_subtopic.name, justify="center")
            for row_subtopic in row_dim.subtopics:
                cells = [
                    ", ".join(
                        str(i)
                        for i in grid.get((row_subtopic.name, col_subtopic.name), [])
                    )
                    or "-"
                    for col_subtopic in col_dim.subtopics
                ]
                table.add_row(row_subtopic.name, *cells)
            self.print(table)

            for cluster_subtopic in cluster_dim.subtopics:
                items = [
                    (index, item)
                    for index, item in enumerate(mapped_evidence, start=1)
                    if item.coordinate[cluster_dim.name] == cluster_subtopic.name
                ]
                if not items:
                    continue
                self.console.rule(
                    f"[bold]{cluster_dim.name}: {cluster_subtopic.name}[/bold]"
                )
                self.console.print()
                for index, item in items:
                    title = item.evidence.title or "Unknown"
                    self.print(
                        f"[dim]{index}.[/dim] {title} - DESTINY ID: {item.evidence.destiny_id}",
                        spacing=False,
                    )
                self.console.print()

    def print_info(self, message: str) -> None:
        """
        Prints a piece of content to terminal.
        :param message: content message to print
        :return: Nothing.
        """
        self.print(f"{message}")

    def print_reasoning(self, label: str, reasoning: str) -> None:
        """
        Prints a completed reasoning trace for a single item, once it's finished generating.
        :param label: a label identifying what the reasoning belongs to
        :param reasoning: the reasoning text to print
        :return: Nothing.
        """
        self.print(
            Panel(
                f"[dim]{reasoning}[/dim]",
                title=f"[bold]{label}[/bold]",
                title_align="left",
                border_style="dim",
                padding=(0, 1),
            )
        )

    def print_reasoning_batch(
        self, labels: Sequence[str], reasonings: Sequence[str]
    ) -> None:
        """
        Prints completed reasoning traces for a batch of items, e.g. after a `dspy.Module.batch`
        call, whose tqdm progress bar leaves the cursor without a trailing newline.
        :param labels: labels identifying what each reasoning trace belongs to
        :param reasonings: the reasoning texts to print, one per label
        :return: Nothing.
        """
        self.console.print()
        for label, reasoning in zip(labels, reasonings):
            self.print_reasoning(label, reasoning)

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

    def run_with_status(
        self,
        program: dspy.Module,
        label: str,
        status: str | None = None,
        **program_inputs,
    ) -> dspy.Prediction:
        """
        Runs a single (non-batched) DSPy program, live-updating a panel with its `reasoning`
        field as it streams in (falling back to a status message before reasoning tokens
        arrive), so the user sees liveness during calls that would otherwise print nothing
        until they complete. The finished panel is left in the scrollback, so callers don't
        need to print the reasoning again afterwards.
        :param program: the DSPy program to run
        :param label: the label to title the live panel with
        :param status: the status message to show as a placeholder before reasoning tokens
            arrive (and while any tool calls are in flight). Defaults to "{label}..." if not given
        :param program_inputs: the arguments to be forwarded to the program
        :return: the program's final Prediction
        :raises ValueError: if the program's stream never yielded a Prediction
        """
        status = status or f"{label}..."
        stream_predict = dspy.streamify(
            program,
            status_message_provider=_StageStatusMessageProvider(status),
            stream_listeners=[
                dspy.streaming.StreamListener(signature_field_name="reasoning")
            ],
            async_streaming=False,
        )
        panel = _LiveReasoningPanel(label, placeholder=status)
        result = None
        with Live(panel, console=self.console, refresh_per_second=10):
            for chunk in stream_predict(**program_inputs):
                if isinstance(chunk, dspy.streaming.StatusMessage):
                    panel.set_placeholder(chunk.message)
                elif isinstance(chunk, dspy.streaming.StreamResponse):
                    panel.append(chunk.chunk)
                elif isinstance(chunk, dspy.Prediction):
                    panel.finish()
                    result = chunk
                    break
        self.console.print()
        if result is None:
            raise ValueError("No Prediction reached")
        return result

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
            raw = self.input(f"[dim]{label} \\[y/N]:[/dim] ", spacing=False)
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
            raw = self.input(f"[dim]Accept these {noun}? [Y (Enter)/n]:[/dim] ")
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
