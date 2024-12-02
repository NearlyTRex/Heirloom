import sys
from rich.console import Console as RichConsole
from rich.text import Text

class Console:
    def __init__(self, quiet: bool = False):
        """
        Initializes the Console with an option to suppress output.

        :param quiet: If True, suppresses all output.
        """
        self.quiet = quiet
        self.console = RichConsole()

    def print(self, *args, **kwargs):
        """
        Prints messages to the console unless `quiet` is set to True.
        """
        if not self.quiet:
            self.console.print(*args, **kwargs)

    def status(self, message: str, *args, **kwargs):
        """
        Displays a status message to the console unless `quiet` is True.
        """
        if not self.quiet:
            with self.console.status(message, *args, **kwargs):
                pass
        else:
            pass

    def log(self, text: str, style: str = 'info'):
        """
        Log messages with a specific style. No output if `quiet` is True.
        """
        if not self.quiet:
            self.console.log(text, style=style)

    def warn(self, text: str):
        """
        Display a warning message to the console.
        """
        if not self.quiet:
            self.console.print(f"[bold yellow]Warning:[/bold yellow] {text}", style="yellow")

    def error(self, text: str):
        """
        Display an error message to the console.
        """
        if not self.quiet:
            self.console.print(f"[bold red]Error:[/bold red] {text}", style="red")

    def success(self, text: str):
        """
        Display a success message to the console.
        """
        if not self.quiet:
            self.console.print(f"[bold green]Success:[/bold green] {text}", style="green")
