from research_mapper.ui.tui import TerminalUI


class ConceptFilterGenerationTools:
    def __init__(self, ui: TerminalUI) -> None:
        self.ui = ui

    def ask_for_clarification(self, question: str):
        return self.ui.prompt_user(question)

    def ask_for_disambiguation(self, question: str):
        return self.ui.prompt_user(question)
