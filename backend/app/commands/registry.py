"""Magic /slash command registry for fast conversation control."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Callable

from app.i18n import t


@dataclass
class CommandResult:
    handled: bool = True
    response: str = ""
    new_thread_id: str | None = None
    action: str = ""
    # If True, the chat route should continue into the LLM after this command.
    pass_through: bool = False


@dataclass
class Command:
    name: str  # without leading slash
    description: str
    handler: Callable[[dict], CommandResult]
    aliases: list[str] = field(default_factory=list)


class CommandRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}
        self._alias: dict[str, str] = {}
        self._register_builtins()

    def register(self, command: Command) -> None:
        self._commands[command.name] = command
        for a in command.aliases:
            self._alias[a] = command.name

    def get(self, name: str) -> Command | None:
        key = name.lstrip("/")
        if key in self._commands:
            return self._commands[key]
        if key in self._alias:
            return self._commands[self._alias[key]]
        return None

    def list_commands(self, lang: str | None = None) -> list[dict]:
        return [
            {
                "name": f"/{c.name}",
                "description": t(f"commands.{c.name}.description", lang) if c.description.startswith("commands.") else c.description,
                "aliases": [f"/{a}" for a in c.aliases],
            }
            for c in self._commands.values()
        ]

    def parse(self, message: str) -> tuple[str, str] | None:
        """Return (command_name, args) if message is a slash command, else None."""
        text = message.strip()
        if not text.startswith("/"):
            return None
        parts = text[1:].split(maxsplit=1)
        if not parts:
            return None
        return parts[0], (parts[1] if len(parts) > 1 else "")

    def execute(self, message: str, context: dict | None = None) -> CommandResult | None:
        parsed = self.parse(message)
        if parsed is None:
            return None
        name, args = parsed
        command = self.get(name)
        if command is None:
            return None
        ctx = dict(context or {})
        ctx["args"] = args
        return command.handler(ctx)

    # ----- built-in commands -----
    def _register_builtins(self) -> None:
        self.register(Command("new", "commands.new.description", self._cmd_new))
        self.register(Command("clear", "commands.clear.description", self._cmd_clear, aliases=["reset"]))
        self.register(Command("stop", "commands.stop.description", self._cmd_stop))
        self.register(Command("restart", "commands.restart.description", self._cmd_restart))
        self.register(Command("help", "commands.help.description", self._cmd_help))
        self.register(Command("plan", "commands.plan.description", self._cmd_plan))

    def _cmd_new(self, ctx: dict) -> CommandResult:
        return CommandResult(response=t("commands.new.response", ctx.get("lang")), new_thread_id=uuid.uuid4().hex[:16], action="new")

    def _cmd_clear(self, ctx: dict) -> CommandResult:
        return CommandResult(response=t("commands.clear.response", ctx.get("lang")), new_thread_id=uuid.uuid4().hex[:16], action="clear")

    def _cmd_stop(self, ctx: dict) -> CommandResult:
        return CommandResult(response=t("commands.stop.response", ctx.get("lang")), action="stop")

    def _cmd_restart(self, ctx: dict) -> CommandResult:
        return CommandResult(response=t("commands.restart.response", ctx.get("lang")), action="restart")

    def _cmd_help(self, ctx: dict) -> CommandResult:
        lang = ctx.get("lang")
        lines = [f"{c['name']} - {c['description']}" for c in self.list_commands(lang)]
        return CommandResult(response=t("commands.help.header", lang) + "\n" + "\n".join(lines), action="help")

    def _cmd_plan(self, ctx: dict) -> CommandResult:
        # Pass through to the agent so the PlanGate handles it.
        return CommandResult(handled=False, pass_through=True, action="plan")


command_registry = CommandRegistry()
