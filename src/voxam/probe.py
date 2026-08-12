"""The probe harness: interrogating a recording empirically.

A seeded acceptance script is a deterministic timeline: the same
commands under the same seed produce the same session, every time
(§2.4 remarks). A Probe exploits that to answer "what would happen
if...?" -- replay the recorded prefix exactly, then try a variant
tail and read each command's response, with anything spoken in the
parser's refusal dialect flagged inline.

This is how recordings are debugged: probe first, theorize later.
The dwarf ambush that survives every retry, the command that
silently did nothing thirty turns before its absence surfaces, the
walkthrough phrase the game does not speak -- each shows up as one
line of one probe run. Probes themselves are throwaway; this module
is the part that never changed between them.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from voxam.acceptance import AcceptanceScript, refusal_in
from voxam.errors import VoxamError
from voxam.frontend import PlainFrontend
from voxam.zmachine.machine import Machine
from voxam.zmachine.story import Story


@dataclass(frozen=True)
class ProbeStep:
    """One command of a probe run and what the story said back.

    Attributes:
        command: The line that was typed.
        response: Everything the story printed before the next
            command was typed -- including, at its tail, any prompt
            for that next command.
        refusal: The response line spoken in the refusal dialect, or
            None when the command seems to have been accepted.
    """

    command: str
    response: str
    refusal: str | None


@dataclass(frozen=True)
class ProbeRun:
    """The outcome of one probe run.

    Attributes:
        steps: The judged commands, in order. A command the machine
            never asked for -- because the story quit or halted
            first -- has no step.
        error: The message of the VoxamError that halted the run, or
            None when the session ended by quitting or by running
            out of commands.
        machine: The machine as the run left it, for post-mortem
            reads: globals, object parents, dynamic memory.
    """

    steps: tuple[ProbeStep, ...]
    error: str | None
    machine: Machine

    @property
    def refusals(self) -> tuple[ProbeStep, ...]:
        """Just the steps whose commands look refused."""

        return tuple(step for step in self.steps if step.refusal is not None)


@dataclass(frozen=True)
class Probe:
    """A recording held still for questioning.

    Every run boots a fresh machine and replays from the beginning
    under the script's seed, so no run can contaminate another: the
    recorded prefix is the same timeline every time.

    Attributes:
        script: The parsed acceptance script.
        story: The loaded story the script names.
    """

    script: AcceptanceScript
    story: Story

    @classmethod
    def load(cls, path: Path | str) -> Self:
        """Open an acceptance script and its story for probing.

        Args:
            path: The script's location.

        Returns:
            A probe over that recording.

        Raises:
            AcceptanceError: If the script cannot be parsed.
            VoxamError: If the story it names cannot be loaded.
            OSError: If either file cannot be read.
        """

        script = AcceptanceScript.parse(Path(path))

        return cls(script=script, story=Story.load(script.game))

    def attempt(self, extra: Sequence[str] = (), *, drop_last: int = 0) -> ProbeRun:
        """Replay the recording, then try a variant tail.

        Args:
            extra: Commands to type after the recorded ones.
            drop_last: How many trailing recorded commands to leave
                off first -- the way to re-try a recording's ending
                without editing the file.

        Returns:
            The run, with steps for the extra commands only; the
            recorded prefix is the known timeline.
        """

        keep = len(self.script.commands) - drop_last
        prefix = list(self.script.commands[:keep])

        return self._run([*prefix, *extra], first=len(prefix))

    def run(self, commands: Sequence[str]) -> ProbeRun:
        """Run an arbitrary command list from boot, judging every step.

        For surgery the recorded prefix cannot express -- inserting
        turns mid-timeline, say -- build the full list yourself and
        judge all of it.

        Args:
            commands: Every command of the session, in order.

        Returns:
            The run, with a step for each command the machine
            consumed.
        """

        return self._run(list(commands), first=0)

    def _run(self, commands: list[str], first: int) -> ProbeRun:
        """Replay commands through a fresh machine, marking output."""

        output: list[str] = []
        length = [0]
        marks: dict[int, int] = {}
        counter = iter(range(len(commands)))

        def collect(text: str) -> None:
            output.append(text)
            length[0] += len(text)

        def source() -> str:
            index = next(counter)
            marks[index] = length[0]

            return commands[index]

        machine = Machine(
            self.story,
            PlainFrontend(collect),
            source,
            seed=self.script.seed,
        )
        error: str | None = None

        try:
            machine.run()
        except (EOFError, StopIteration):
            pass
        except VoxamError as halt:
            error = str(halt)

        text = "".join(output)
        steps = []

        for index in range(first, len(commands)):
            if index not in marks:
                break

            end = marks.get(index + 1, len(text))
            response = text[marks[index] : end]

            steps.append(
                ProbeStep(
                    command=commands[index],
                    response=response,
                    refusal=refusal_in(response),
                )
            )

        return ProbeRun(steps=tuple(steps), error=error, machine=machine)
