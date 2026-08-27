"""The Å-machine savefile: the AASV form written and revived.

A saved game is IFF: form AASV holding HEAD, DATA, and REGS
(Aa-machine: Savefile). HEAD is the story's own header, copied
byte for byte so a savefile can never be revived into the wrong
story. DATA is the whole game state -- the initialized registers,
then the random access area, the auxiliary heap, and the main
heap, big-endian words all -- exclusive-orred against the INIT
chunk padded with the unused word, then run-length encoded: a
null byte followed by N-1 stands for a stretch of N nulls. REGS
carries the sixty-four general registers, the special registers,
and the open divs.

The captured-state tuple these functions speak is the machine's
own: the same shape Machine._captured builds and Machine._restored
takes back.
"""

from voxam.aamachine.story import Story
from voxam.errors import AAMachineError
from voxam.iff import Chunk, chunk, parse_form

FORM_ID = b"AASV"

# The unused-word stamp that pads the INIT chunk out to the full
# state (Aa-machine: Savefile).
_UNUSED = b"\x3f\x3f"

# The REGS chunk's fixed bytes before the div list: sixty-four
# registers, two longs, eight words, two lone bytes, and the div
# count itself (Aa-machine: Savefile).
_REGS_FIXED = 156

# The longest null run one encoded pair can spell.
_RUN_TOP = 256

# One captured game state: the initialized registers, the three
# memory areas masked to their allocations, the general and
# special registers, and the open divs (Aa-machine: Savefile).
State = tuple[
    tuple[int, int, int],
    tuple[int, ...],
    tuple[int, ...],
    tuple[int, ...],
    tuple[int, ...],
    tuple[int, int, int, int, int, int],
    tuple[int, int, int, int, int, int],
    tuple[int, ...],
]


def kept(story: Story, state: State) -> bytes:
    """One captured state as a whole AASV savefile (Aa-machine: Savefile)."""

    counted, ram, aux, heap, regs, flow, stacks, divs = state
    told = _worded(counted) + _worded(ram) + _worded(aux) + _worded(heap)
    base = _grounded(story, len(told))
    diff = bytes(a ^ b for a, b in zip(told, base, strict=True))
    landing, cont, top, env, cho, sim = flow
    auxp, trl, sta, stc, cwl, spc = stacks
    registers = (
        _worded(regs)
        + landing.to_bytes(4, "big")
        + cont.to_bytes(4, "big")
        + _worded((top, env, cho, sim, auxp, trl, sta, stc))
        + bytes([cwl, spc])
        + len(divs).to_bytes(2, "big")
        + _worded(divs)
    )
    return chunk(
        b"FORM",
        FORM_ID
        + chunk(b"HEAD", _headed(story))
        + chunk(b"DATA", _shrunk(diff))
        + chunk(b"REGS", registers),
    )


def revived(story: Story, data: bytes) -> State:
    """A savefile's captured state, verified against its story.

    Raises:
        AAMachineError: For a form that is not AASV, a HEAD that
            does not match the story's own, or DATA or REGS that
            cannot hold the story's whole state.
        IFFError: If the FORM itself cannot be walked.
    """

    form, chunks = parse_form(data)

    if form != FORM_ID:
        msg = (
            f"a saved game is FORM AASV, not FORM "
            f"{form.decode('ascii', 'replace')} (Aa-machine: Savefile)"
        )

        raise AAMachineError(msg)

    held: dict[bytes, Chunk] = {}

    for piece in chunks:
        held.setdefault(piece.chunk_id, piece)

    for name in (b"HEAD", b"DATA", b"REGS"):
        if name not in held:
            msg = (
                f"the savefile is missing its {name.decode('ascii')} "
                f"chunk (Aa-machine: Savefile)"
            )

            raise AAMachineError(msg)

    if held[b"HEAD"].payload != _headed(story):
        msg = (
            "the savefile's HEAD does not match this story's -- it "
            "belongs to another game or another release (Aa-machine: Savefile)"
        )

        raise AAMachineError(msg)

    words = 3 + story.ram_size + story.aux_size + story.heap_size
    diff = _grown(held[b"DATA"].payload)

    if len(diff) != words * 2:
        msg = (
            f"the savefile's DATA unpacks to {len(diff)} bytes, but this "
            f"story's state is {words * 2} (Aa-machine: Savefile)"
        )

        raise AAMachineError(msg)

    base = _grounded(story, len(diff))
    told = bytes(a ^ b for a, b in zip(diff, base, strict=True))
    values = [int.from_bytes(told[at : at + 2], "big") for at in range(0, len(told), 2)]
    ram_end = 3 + story.ram_size
    aux_end = ram_end + story.aux_size

    return (
        (values[0], values[1], values[2]),
        tuple(values[3:ram_end]),
        tuple(values[ram_end:aux_end]),
        tuple(values[aux_end:]),
        *_registered(held[b"REGS"].payload),
    )


def _registered(
    payload: bytes,
) -> tuple[
    tuple[int, ...],
    tuple[int, int, int, int, int, int],
    tuple[int, int, int, int, int, int],
    tuple[int, ...],
]:
    """The REGS chunk's registers and divs (Aa-machine: Savefile).

    Raises:
        AAMachineError: For a chunk too short for its own claims.
    """

    if len(payload) < _REGS_FIXED:
        msg = "the savefile's REGS chunk is too short (Aa-machine: Savefile)"

        raise AAMachineError(msg)

    regs = tuple(int.from_bytes(payload[at : at + 2], "big") for at in range(0, 128, 2))
    landing = int.from_bytes(payload[128:132], "big")
    cont = int.from_bytes(payload[132:136], "big")
    top, env, cho, sim, auxp, trl, sta, stc = (
        int.from_bytes(payload[136 + at * 2 : 138 + at * 2], "big") for at in range(8)
    )
    cwl = payload[152]
    spc = payload[153]
    counted = int.from_bytes(payload[154:156], "big")

    if 156 + counted * 2 > len(payload):
        msg = (
            f"the savefile claims {counted} open divs, past the REGS "
            f"chunk's end (Aa-machine: Savefile)"
        )

        raise AAMachineError(msg)

    divs = tuple(
        int.from_bytes(payload[156 + at * 2 : 158 + at * 2], "big")
        for at in range(counted)
    )

    return (
        regs,
        (landing, cont, top, env, cho, sim),
        (auxp, trl, sta, stc, cwl, spc),
        divs,
    )


def _headed(story: Story) -> bytes:
    """The story's own HEAD payload, the savefile's identity check."""

    return story.summed(b"HEAD").payload


def _worded(values: "tuple[int, ...]") -> bytes:
    """Words as big-endian bytes (Aa-machine: Savefile)."""

    return b"".join(value.to_bytes(2, "big") for value in values)


def _grounded(story: Story, length: int) -> bytes:
    """The INIT chunk padded with the unused word to a length."""

    base = story.summed(b"INIT").payload

    if len(base) < length:
        base = base + _UNUSED * ((length - len(base) + 1) // 2)

    return base[:length]


def _shrunk(data: bytes) -> bytes:
    """Run-length encode: N nulls become a null and N-1."""

    told = bytearray()
    at = 0

    while at < len(data):
        if data[at]:
            told.append(data[at])
            at += 1
        else:
            run = 1

            while run < _RUN_TOP and at + run < len(data) and not data[at + run]:
                run += 1

            told.append(0)
            told.append(run - 1)
            at += run

    return bytes(told)


def _grown(data: bytes) -> bytes:
    """Run-length decode, the encoder's exact inverse.

    Raises:
        AAMachineError: For a stream ending inside a null run.
    """

    told = bytearray()
    at = 0

    while at < len(data):
        if data[at]:
            told.append(data[at])
            at += 1
        else:
            if at + 1 >= len(data):
                msg = (
                    "the savefile's DATA ends inside a null run (Aa-machine: Savefile)"
                )

                raise AAMachineError(msg)

            told.extend(b"\x00" * (data[at + 1] + 1))
            at += 2

    return bytes(told)
