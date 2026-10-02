"""Frame evidence for the issue #2 probes, calibrated for the 1280x720 harness.

The first frame is a title reference, not OCR: visually confirm it names the boss.
A changed title invalidates the numeric comparison. These are probes, not pass/fail tests.
"""
import json
import time
from pathlib import Path

from PIL import Image
import boss_common as B


class Evidence:
    def __init__(self, zone):
        self.zone = zone
        self.title = None
        self.records = []

    def shot(self, label):
        assert B.zone() == self.zone, (B.zone(), self.zone)
        path = B.shot(label)
        im = Image.open(path).convert('RGB')
        red = blue = 0
        for x in range(449, 852):
            r, g, b = im.getpixel((x, 72))
            red += 100 <= r <= 140 and g < 45 and b < 45
            blue += 100 <= r <= 140 and 100 <= g <= 140 and b > 160
        signature = B.title_sig(path)
        if self.title is None and red + blue:
            self.title = signature
        distance = (sum(abs(a - b) for a, b in zip(signature, self.title)) / len(signature)
                    if self.title is not None else 255)
        valid = distance < 18 and bool(red + blue)
        record = dict(label=label, red_pixels=red, blue_pixels=blue,
                      health_pct=round(100 * (red + blue) / 403, 1) if valid else None,
                      same_title=valid)
        self.records.append(record)
        B.log(record)
        return record

    def save(self, name):
        Path(B.OUT, name + '.json').write_text(json.dumps(self.records, indent=2), encoding='utf-8')


def command(*statements):
    B.script(*statements)
    time.sleep(.5)
