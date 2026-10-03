"""Physical position of every screen area, in key-image pixels (a 96x96 key image = one window).

Measured from photos: a coordinate grid as background (LOG) image, then each key showing a
known crop of that grid, then labelled test patterns. Accurate to a few pixels. Once any key
image is set the background is not shown.

The right-hand strip is one tall window, 80 px wide and about 420 px tall, at the same scale as
the key images. Slots 16, 17 and 18 start level with the three key rows (150 px apart) and draw
their JPEG downwards from there, so three slices of 80x152, 80x152 and 80x120 fill the strip.
A single tall image in slot 16 does not work: the firmware's decode buffer for a key image is
too small, so only part of it gets drawn (and oversized images can hang the device).
JPEG dimensions should be multiples of 8; other sizes decode with garbage along an edge.
"""
from streamdock import COLS, KEY_SIZE, ROWS, key_index

PITCH_X = 146  # distance between key columns
PITCH_Y = 150  # distance between key rows (and between strip slots)

STRIP_W = 80
STRIP_SLICES = {16: 152, 17: 152, 18: 120}  # slot -> slice height; each overlaps the next by 2 px
STRIP_X = (COLS - 1) * PITCH_X + 138
STRIP_Y = 12  # top of slot 16 relative to the top of key row 0


def screen_rects():
    """{hardware index: ((left, top, width, height), (out_w, out_h))}.

    The first tuple is the area in the shared layout (key-image pixels, relative to the
    top-left key); the second is the pixel size of the image sent to that slot.
    """
    rects = {}
    for c in range(COLS):
        for r in range(ROWS):
            rects[key_index(c, r)] = ((c * PITCH_X, r * PITCH_Y, KEY_SIZE, KEY_SIZE), (KEY_SIZE, KEY_SIZE))
    for r, (slot, h) in enumerate(STRIP_SLICES.items()):
        rects[slot] = ((STRIP_X, STRIP_Y + r * PITCH_Y, STRIP_W, h), (STRIP_W, h))
    return rects


VIEW_W = STRIP_X + STRIP_W
VIEW_H = max((ROWS - 1) * PITCH_Y + KEY_SIZE, STRIP_Y + (ROWS - 1) * PITCH_Y + STRIP_SLICES[18])
