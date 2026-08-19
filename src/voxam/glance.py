"""A read-only tour of a story file's header (§11.1).

The header is the story's own manifest: what machine it wants,
where its tables live, and which courtesies it hopes the
interpreter can offer. This report reads the pristine file --
before the interpreter stamps in any capabilities of its own -- so
every line shows what the compiler shipped, hexadecimal where the
value is an address, with the Standard section that defines it.
The checksum is computed as §15's verify opcode would and judged
against the stored word, which is the part no static field listing
ever did for you.
"""

from voxam.zmachine.header import (
    FLAGS_1,
    FLAGS_2,
    GRAPHICS_BIT,
    MENUS_BIT,
    MOUSE_BIT,
    OFFSET_VERSIONS,
    PACKED_PC_VERSION,
    PICTURE_FLAGS_VERSION,
    SOUND_BIT,
    STATUS_FLAGS_VERSION,
    TANDY_BIT,
)
from voxam.zmachine.story import Story

# The game-authored request bits of Flags 2 (§11.1): the low byte
# holds pictures-or-font (3), undo (4), mouse (5), colours (6),
# and sound (7); menus are bit 8, in the word's high byte. The
# transcription and fixed-pitch bits describe a player's session,
# not the shipped file, and are left to the session that owns them.
UNDO_BIT = 0x10
COLOURS_REQUEST_BIT = 0x40


def report(story: Story) -> str:
    """Compose the header report for a loaded story.

    Args:
        story: The story file to describe.

    Returns:
        The report as a newline-joined block of text.
    """

    lines = [
        *_identity(story),
        "",
        *_memory_map(story),
        "",
        *_requests(story),
    ]

    return "\n".join(lines)


def _field(name: str, value: str, meaning: str) -> str:
    """One report line: a name, a value, and its meaning."""

    return f"  {name:<18} {value:>12}   {meaning}"


def _address(value: int) -> str:
    """A byte address in the Standard's own $hex dress."""

    return f"${value:04x}"


def _identity(story: Story) -> list[str]:
    """The stanza that names the story and judges its checksum."""

    header = story.header
    declared = header.declared_file_length
    lines = [
        "Identity",
        _field("version", str(header.version), "the Z-Machine version (§11.1)"),
        _field("release", str(header.release), "the story's release number (§11.1)"),
        _field(
            "serial",
            header.serial_number,
            "six characters, conventionally the compile date (§11.1)",
        ),
        _field(
            "file length",
            f"{declared} bytes",
            f"declared, at the version's scale (§11.1.6); {len(story.data)} on disk",
        ),
    ]

    stored = header.stored_checksum
    computed = header.computed_checksum

    if header.verify():
        verdict = f"${stored:04x} stored and computed agree (§15 verify)"
    elif stored == 0:
        verdict = (
            f"stored $0000, computed ${computed:04x} -- some early "
            f"Version 3 files store none (§11.1)"
        )
    else:
        verdict = (
            f"MISMATCH: stored ${stored:04x}, computed ${computed:04x} (§15 verify)"
        )

    lines.append(_field("checksum", "", verdict).rstrip())

    return lines


def _memory_map(story: Story) -> list[str]:
    """The stanza of table addresses and region boundaries."""

    header = story.header
    lines = ["Memory map"]

    if header.version == PACKED_PC_VERSION:
        lines.append(
            _field(
                "main routine",
                _address(header.main_routine_packed_address),
                "packed routine address; execution calls it (§5.4, §11.1)",
            )
        )
    else:
        lines.append(
            _field(
                "initial pc",
                _address(header.initial_program_counter),
                "the first instruction's byte address (§5.5, §11.1)",
            )
        )

    lines.extend(
        [
            _field(
                "static memory",
                _address(header.static_memory_base),
                "writes stop here (§1.1.1, §1.1.2)",
            ),
            _field(
                "high memory",
                _address(header.high_memory_base),
                "routines and strings begin (§1.1.3)",
            ),
            _field(
                "dictionary",
                _address(header.dictionary_address),
                "the parser's word list (§13, §11.1)",
            ),
            _field(
                "objects",
                _address(header.object_table_address),
                "the object table (§12, §11.1)",
            ),
            _field(
                "globals",
                _address(header.global_variables_address),
                "240 global variables (§6.2, §11.1)",
            ),
            _field(
                "abbreviations",
                _address(header.abbreviations_table_address),
                "the abbreviations table (§3.3, §11.1)",
            ),
        ]
    )

    alphabet = header.alphabet_table_address

    lines.append(
        _field(
            "alphabet table",
            _address(alphabet) if alphabet else "standard",
            "custom alphabets (§3.5.5)"
            if alphabet
            else "the standard alphabets (§3.5)",
        )
    )

    unicode_table = header.unicode_translation_address

    lines.append(
        _field(
            "unicode table",
            _address(unicode_table) if unicode_table else "default",
            "custom translations (§3.8.5.2)"
            if unicode_table
            else "the default table (§3.8.5.3)",
        )
    )

    if header.version in OFFSET_VERSIONS:
        lines.extend(
            [
                _field(
                    "routines offset",
                    _address(header.routines_offset),
                    "as stored, divided by 8 (§1.2.3)",
                ),
                _field(
                    "strings offset",
                    _address(header.static_strings_offset),
                    "as stored, divided by 8 (§1.2.3)",
                ),
            ]
        )

    return lines


def _requests(story: Story) -> list[str]:
    """The stanza of flags: what the game declares and asks for."""

    header = story.header
    flags_1 = header.data[FLAGS_1]
    flags_2 = int.from_bytes(header.data[FLAGS_2 : FLAGS_2 + 2], "big")
    lines = [
        "Flags, as shipped",
        _field("flags 1", f"${flags_1:02x}", "the byte at $01 (§11.1)"),
        _field("flags 2", f"${flags_2:04x}", "the word at $10 (§11.1)"),
    ]

    if header.version <= STATUS_FLAGS_VERSION:
        kind = "time of day" if header.time_game else "score and turns"

        lines.append(_field("status line", kind, "what the top line shows (§8.2.3)"))

        if flags_1 & TANDY_BIT:
            lines.append(
                _field(
                    "tandy bit",
                    "set",
                    "shipped minding its manners (§11.1.4 remarks)",
                )
            )

    asks = []

    if flags_2 & GRAPHICS_BIT:
        asks.append(
            "pictures (§11.1)"
            if header.version >= PICTURE_FLAGS_VERSION
            else "the §16 character graphics font (§8.1.5.1)"
        )

    if flags_2 & UNDO_BIT:
        asks.append("undo (§11.1)")

    if flags_2 & MOUSE_BIT:
        asks.append("a mouse (§11.1.2)")

    if flags_2 & COLOURS_REQUEST_BIT:
        asks.append("colours (§8.3.3)")

    if flags_2 & SOUND_BIT:
        asks.append("sound effects (§9, §11.1)")

    if flags_2 & (MENUS_BIT << 8):
        asks.append("menus (§11.1.2)")

    if asks:
        lines.append("  the game asks for:")
        lines.extend(f"    - {ask}" for ask in asks)
    else:
        lines.append("  the game asks for no optional courtesies")

    return lines
