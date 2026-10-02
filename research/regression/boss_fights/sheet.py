"""Tile frames into one contact sheet: sheet.py OUT.png COLS W frame1.png frame2.png ..."""
import sys, glob, os
from PIL import Image, ImageDraw
out, cols, w = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
files = []
for a in sys.argv[4:]:
    files += sorted(glob.glob(a))
h = int(w * 720 / 1280)
rows = (len(files) + cols - 1) // cols
im = Image.new('RGB', (cols * w, rows * h), 'black')
d = ImageDraw.Draw(im)
for i, f in enumerate(files):
    t = Image.open(f).convert('RGB').resize((w, h))
    im.paste(t, ((i % cols) * w, (i // cols) * h))
    d.text(((i % cols) * w + 4, (i // cols) * h + 2), os.path.basename(f)[:-4], fill='yellow')
im.save(out)
print(out, len(files))
