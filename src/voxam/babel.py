"""The Treaty of Babel: computing a story's IFID.

The treaty gives every work of interactive fiction an IFID,
"analogous to the ISBN code assigned to every published book"
(Babel: The IFID unique identifier), and lays down per-format
rules for computing one where none is embedded. This module
carries the rules for the formats Voxam plays: Z-code and Glulx.

Modern design systems brand both formats with a UUID://...//
string in byte-accessible memory, and the brand wins wherever it
is found. Legacy files earn their IFIDs from their header numbers
instead -- human-readable identities like ZCODE-88-840726, which
the treaty prefers to hashes because Infocom's files "sometimes
crop up with spurious tails" (Babel: The IFID for a legacy Z-code
story file).
"""

import re
from dataclasses import dataclass
from xml.etree import ElementTree

from voxam.glulx.story import MAGIC as GLULX_MAGIC

# The brand modern design systems burn into byte-accessible
# memory. The treaty spells an IFID with digits, capitals, and
# hyphens, but Alan writes lowercase hexadecimal, "converted to
# upper case when reading" (Babel: Game formats that embed an
# IFID) -- so the scan accepts both cases and the answer wears
# capitals.
_BRAND = re.compile(rb"UUID://([0-9A-Za-z-]+)//")

# Serial codes that never earn a checksum suffix: the test and
# user-modified forms the treaty names (Babel: The IFID for a
# legacy Z-code story file).
_UNTRUSTED_SERIALS = frozenset({"000000", "999999", "------"})

# The Z-code header's identifying words (§11.1): release, serial,
# checksum -- the treaty's three elements.
_Z_RELEASE = slice(0x02, 0x04)
_Z_SERIAL = slice(0x12, 0x18)
_Z_CHECKSUM = slice(0x1C, 0x1E)

# The Glulx header's identifying words (Glulx: The Header), plus
# the Inform-compiled fields past its end (Babel: The IFID for a
# legacy Glulx story file).
_GLULX_EXTENT = slice(12, 16)
_GLULX_CHECKSUM = slice(32, 36)
_GLULX_COMPILER = slice(36, 40)
_GLULX_RELEASE = slice(52, 54)
_GLULX_SERIAL = slice(54, 60)
_INFORM = b"Info"

# A story too short to hold the identifying header words can hold
# no identity either.
_HEADER_EXTENT = 0x40

# The Z-Machine's eight story file versions (§11.1): a plausible
# version byte is what marks loose bytes as Z-code.
_LAST_Z_VERSION = 8


def ifid(data: bytes) -> str | None:
    """The IFID for a story file's bytes; None for neither format.

    A Glulx file answers by its magic word, anything else with a
    plausible version byte as Z-code. The caller unwraps blorbs
    first: a blorbed story's IFID is its packaged story's, until
    an iFiction record says otherwise (Babel: The IFID for a
    blorbed story file).
    """

    if len(data) < _HEADER_EXTENT:
        return None

    if data[:4] == GLULX_MAGIC:
        return glulx_ifid(data)

    if 1 <= data[0] <= _LAST_Z_VERSION:
        return zcode_ifid(data)

    return None


def zcode_ifid(data: bytes) -> str:
    """A Z-code story's IFID from its brand or its header.

    The serial gates the brand scan: a file whose serial dates it
    before 2006 -- the 1980s, the 1990s, 2000 through 2005 --
    cannot carry the UUID brand, so "searching for this is
    unnecessary" and only the rest are scanned (Babel: The IFID
    for a legacy Z-code story file).
    """

    serial = _cleaned(data[_Z_SERIAL])

    if not (serial.startswith(("8", "9")) or "00" <= serial[:2] <= "05"):
        branded = _branded(data)

        if branded is not None:
            return branded

    release = int.from_bytes(data[_Z_RELEASE], "big")
    head = f"ZCODE-{release}-{serial}"

    if serial[0] in "012345679" and serial not in _UNTRUSTED_SERIALS:
        # The post-1990 form: Inform-era serials carry the
        # checksum as four hexadecimal digits, while Infocom's
        # 8x serials -- and the untrusted forms -- stay bare
        # (Babel: The IFID for a legacy Z-code story file).
        checksum = int.from_bytes(data[_Z_CHECKSUM], "big")

        return f"{head}-{checksum:04X}"

    return head


def glulx_ifid(data: bytes) -> str:
    """A Glulx story's IFID from its brand or its header.

    An Inform-compiled file identifies like Z-code -- release,
    serial, checksum -- and announces itself with "Info" past the
    header proper; a file from any other tool has only its
    checksum, supplemented by the stated size of the initial
    memory map (Babel: The IFID for a legacy Glulx story file).
    """

    branded = _branded(data)

    if branded is not None:
        return branded

    checksum = int.from_bytes(data[_GLULX_CHECKSUM], "big")

    if data[_GLULX_COMPILER] == _INFORM:
        release = int.from_bytes(data[_GLULX_RELEASE], "big")
        serial = _cleaned(data[_GLULX_SERIAL])

        return f"GLULX-{release}-{serial}-{checksum:08X}"

    extent = int.from_bytes(data[_GLULX_EXTENT], "big")

    return f"GLULX-{extent:08X}-{checksum:08X}"


@dataclass(frozen=True)
class IFiction:
    """The bibliographic heart of an iFiction record.

    Attributes:
        ifid: The record's primary IFID -- the first listed, which
            the treaty puts foremost when a work carries several
            (Babel: The iFiction format).
        title: The work's title, or None unrecorded.
        author: The author, or None unrecorded.
        headline: The subtitle-like headline, or None unrecorded.
        description: The work's blurb, or None unrecorded -- its
            <br/> line breaks carried as newlines, since the
            treaty spells paragraph breaks with them (Babel: The
            iFiction format).
    """

    ifid: str | None = None
    title: str | None = None
    author: str | None = None
    headline: str | None = None
    description: str | None = None


def ifiction(xml: bytes) -> IFiction | None:
    """The first story record in iFiction XML; None for unreadable.

    Elements are matched by local name alone: the treaty
    namespaces <ifindex>, but records in the wild are not always
    so careful, and bibliography is a courtesy that should survive
    a missing xmlns. Records the treaty itself warns about -- the
    pre-1.0 versions still circulating -- answer whatever of the
    record they can (Babel: The iFiction format).
    """

    try:
        root = ElementTree.fromstring(xml)  # noqa: S314 -- local file bytes, no network entities
    except ElementTree.ParseError:
        return None

    story = _child(root, "story")

    if story is None:
        return None

    identification = _child(story, "identification")
    bibliographic = _child(story, "bibliographic")

    return IFiction(
        ifid=_field(identification, "ifid"),
        title=_field(bibliographic, "title"),
        author=_field(bibliographic, "author"),
        headline=_field(bibliographic, "headline"),
        description=_broken_field(bibliographic, "description"),
    )


def _child(element: ElementTree.Element, name: str) -> ElementTree.Element | None:
    """The first child whose local name matches, namespace-blind."""

    for child in element:
        if child.tag.rpartition("}")[2] == name:
            return child

    return None


def _field(section: ElementTree.Element | None, name: str) -> str | None:
    """A section's first named child's text, stripped, or None."""

    if section is None:
        return None

    found = _child(section, name)

    if found is None or found.text is None:
        return None

    return found.text.strip() or None


def _broken_field(section: ElementTree.Element | None, name: str) -> str | None:
    """A field whose <br/> children mark line breaks, walked whole.

    A description is mixed content: taking .text alone would
    silently drop everything after the first break, so the walk
    keeps every piece with a newline at each <br/> (Babel: The
    iFiction format).
    """

    if section is None:
        return None

    found = _child(section, name)

    if found is None:
        return None

    pieces = [found.text or ""]

    for child in found:
        if child.tag.rpartition("}")[2] == "br":
            pieces.append("\n")

        pieces.append(child.text or "")
        pieces.append(child.tail or "")

    lines = [line.strip() for line in "".join(pieces).split("\n")]

    return "\n".join(lines).strip() or None


def _branded(data: bytes) -> str | None:
    """The embedded UUID://...// brand, uppercased, or None.

    "Its location cannot be guaranteed, so the whole of
    byte-accessible memory must be scanned" (Babel: Game formats
    that embed an IFID) -- and the file is the practical superset
    of byte-accessible memory.
    """

    matched = _BRAND.search(data)

    if matched is None:
        return None

    return matched.group(1).decode("ascii").upper()


def _cleaned(serial: bytes) -> str:
    """Serial bytes as text, non-alphanumerics turned to hyphens.

    Only ASCII alphanumerics survive: "converting any
    non-alphanumeric characters (in particular, nulls) to
    hyphens" (Babel: The IFID for a legacy Z-code story file).
    """

    return "".join(
        chr(byte) if chr(byte).isascii() and chr(byte).isalnum() else "-"
        for byte in serial
    )
