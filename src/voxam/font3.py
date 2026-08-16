"""Font 3's own pixels: the §16 bitmaps, byte for byte.

Every 8x8 character graphic, derived from the Standard's own
bitmap listings in §16 -- one byte per row, bit 7 the leftmost
pixel, exactly as the spec draws them. A pixel glass renders these
directly, which no character terminal could: the map's road tips
are single pixels, the stat gauge fills by eighths, and the
reverse-video twins at 123 to 126 are carried as the spec's own
inverted bitmaps rather than a style flip. The derivation script
asserted the twins are exact inversions of their plain shapes
before this table was written down.
"""

# Each entry: eight row bytes for one §16 character code.
FONT_3_BITMAPS = {
    32: bytes.fromhex("0000000000000000"),  # blank
    33: bytes.fromhex("00002060fe602000"),  # left arrow
    34: bytes.fromhex("0000080cfe0c0800"),  # right arrow
    35: bytes.fromhex("0102040810204080"),  # diagonal, rising
    36: bytes.fromhex("8040201008040201"),  # diagonal, falling
    37: bytes.fromhex("0000000000000000"),  # blank
    38: bytes.fromhex("00000000ff000000"),  # horizontal line, low
    39: bytes.fromhex("000000ff00000000"),  # horizontal line, high
    40: bytes.fromhex("0808080808080808"),  # vertical, right of centre
    41: bytes.fromhex("1010101010101010"),  # vertical, left of centre
    42: bytes.fromhex("080808ff00000000"),  # line up joined to a horizontal
    43: bytes.fromhex("00000000ff080808"),  # line down joined to a horizontal
    44: bytes.fromhex("080808080f080808"),  # vertical joined rightward
    45: bytes.fromhex("10101010f0101010"),  # vertical joined leftward
    46: bytes.fromhex("101010101f000000"),  # corner, up-right
    47: bytes.fromhex("0000001f10101010"),  # corner, down-right
    48: bytes.fromhex("000000f808080808"),  # corner, down-left
    49: bytes.fromhex("08080808f8000000"),  # corner, up-left
    50: bytes.fromhex("101010101f204080"),  # up-right, tail dropped
    51: bytes.fromhex("8040201f10101010"),  # down-right, tail dropped
    52: bytes.fromhex("010204f808080808"),  # down-left, tail dropped
    53: bytes.fromhex("08080808f8040201"),  # up-left, tail dropped
    54: bytes.fromhex("ffffffffffffffff"),  # solid block
    55: bytes.fromhex("ffffffffff000000"),  # upper five-eighths
    56: bytes.fromhex("000000ffffffffff"),  # lower five-eighths
    57: bytes.fromhex("f8f8f8f8f8f8f8f8"),  # left five-eighths
    58: bytes.fromhex("1f1f1f1f1f1f1f1f"),  # right five-eighths
    59: bytes.fromhex("080808ffffffffff"),  # lower block, line up dropped
    60: bytes.fromhex("ffffffffff080808"),  # upper block, line down dropped
    61: bytes.fromhex("f8f8f8f8fff8f8f8"),  # left block, line right dropped
    62: bytes.fromhex("1f1f1f1fff1f1f1f"),  # right block, line left dropped
    63: bytes.fromhex("1f1f1f1f1f000000"),  # mass, upper right
    64: bytes.fromhex("0000001f1f1f1f1f"),  # mass, lower right
    65: bytes.fromhex("000000f8f8f8f8f8"),  # mass, lower left
    66: bytes.fromhex("f8f8f8f8f8000000"),  # mass, upper left
    67: bytes.fromhex("1f1f1f1f1f204080"),  # upper-right mass meeting a diagonal
    68: bytes.fromhex("8040201f1f1f1f1f"),  # lower-right mass meeting a diagonal
    69: bytes.fromhex("010204f8f8f8f8f8"),  # lower-left mass meeting a diagonal
    70: bytes.fromhex("f8f8f8f8f8040201"),  # upper-left mass meeting a diagonal
    71: bytes.fromhex("0100000000000000"),  # road tip, top right
    72: bytes.fromhex("0000000000000001"),  # road tip, bottom right
    73: bytes.fromhex("0000000000000080"),  # road tip, bottom left
    74: bytes.fromhex("8000000000000000"),  # road tip, top left
    75: bytes.fromhex("ff00000000000000"),  # top edge stroke
    76: bytes.fromhex("00000000000000ff"),  # bottom edge stroke
    77: bytes.fromhex("8080808080808080"),  # left edge stroke
    78: bytes.fromhex("0101010101010101"),  # right edge stroke
    79: bytes.fromhex("00ff00000000ff00"),  # gauge rails, empty
    80: bytes.fromhex("00ff80808080ff00"),  # gauge, one eighth
    81: bytes.fromhex("00ffc0c0c0c0ff00"),  # gauge, two eighths
    82: bytes.fromhex("00ffe0e0e0e0ff00"),  # gauge, three eighths
    83: bytes.fromhex("00fff0f0f0f0ff00"),  # gauge, four eighths
    84: bytes.fromhex("00fff8f8f8f8ff00"),  # gauge, five eighths
    85: bytes.fromhex("00fffcfcfcfcff00"),  # gauge, six eighths
    86: bytes.fromhex("00fffefefefeff00"),  # gauge, seven eighths
    87: bytes.fromhex("00ffffffffffff00"),  # gauge, full
    88: bytes.fromhex("0001010101010100"),  # gauge, right rim
    89: bytes.fromhex("0080808080808000"),  # gauge, left rim
    90: bytes.fromhex("8142241818244281"),  # diagonal cross
    91: bytes.fromhex("08080808ff080808"),  # four-way join
    92: bytes.fromhex("183cdb1818181800"),  # up arrow
    93: bytes.fromhex("18181818db3c1800"),  # down arrow
    94: bytes.fromhex("183cdb18db3c1800"),  # up-down arrow
    95: bytes.fromhex("ff818181818181ff"),  # outlined box
    96: bytes.fromhex("3c66060c18001800"),  # question mark
    97: bytes.fromhex("c4a890c0a0908000"),  # rune ac
    98: bytes.fromhex("6050487048506000"),  # rune beorc
    99: bytes.fromhex("1018149250301000"),  # rune eoh
    100: bytes.fromhex("82c6aa92aac68200"),  # rune daeg
    101: bytes.fromhex("82c6aa9282828200"),  # rune eh
    102: bytes.fromhex("94a8d0a0c0808000"),  # rune feoh
    103: bytes.fromhex("8244281028448200"),  # rune gyfu
    104: bytes.fromhex("c2a2d2aa968a8600"),  # rune haegl
    105: bytes.fromhex("1010101010101000"),  # rune is
    106: bytes.fromhex("1038549254381000"),  # rune ger
    107: bytes.fromhex("1010103854929200"),  # rune calc
    108: bytes.fromhex("1018141210101000"),  # rune lagu
    109: bytes.fromhex("c6aa92aac6828200"),  # rune man
    110: bytes.fromhex("9050381412101000"),  # rune nyd
    111: bytes.fromhex("c4acd4a890808000"),  # rune os
    112: bytes.fromhex("80808090a8c48200"),  # rune peorth
    113: bytes.fromhex("4040407844444400"),  # rune cen
    114: bytes.fromhex("6050485060504800"),  # rune rad
    115: bytes.fromhex("40444c5464440400"),  # rune sigel
    116: bytes.fromhex("1038549210101000"),  # rune tir
    117: bytes.fromhex("6050484444444400"),  # rune ur
    118: bytes.fromhex("10ba541010101000"),  # rune ear
    119: bytes.fromhex("6050485060404000"),  # rune wynn
    120: bytes.fromhex("9254381010101000"),  # rune eolh
    121: bytes.fromhex("e0d0a8949a969200"),  # rune yr
    122: bytes.fromhex("1028442810284400"),  # rune ethel
    123: bytes.fromhex("e7c324e7e7e7e7ff"),  # up arrow, reversed
    124: bytes.fromhex("e7e7e7e724c3e7ff"),  # down arrow, reversed
    125: bytes.fromhex("e7c324e724c3e7ff"),  # up-down arrow, reversed
    126: bytes.fromhex("c399f9f3e7ffe7ff"),  # question mark, reversed
}

ROWS = 8
PIXELS = 8
