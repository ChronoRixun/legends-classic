# Making a disc image of your own X-Men Legends disc

The builder reads **an image of your own Xbox disc** of X-Men Legends. It never needs, and this project never links
to, a downloaded copy: only image discs you own, and check the laws that apply where you live.

## What the builder accepts

| Image | What it is | |
|---|---|---|
| **Full disc image** (`.iso`, about 7.8 GB) | every sector of the disc, the way disc-preservation projects image Xbox discs | best: `info` can match it against a known good dump |
| **XISO** (`.iso` / `.xiso`, smaller) | only the disc's game partition (the Xbox file system) | fine: it holds everything the build needs |
| Compressed images (CCI, CSO) | used by some modded consoles and emulators | not yet: decompress back to an ISO with the tool that made it |
| A folder of extracted files | | not supported: the builder reads the image itself |

The PlayStation 2 and GameCube releases of X-Men Legends are different builds of the game and don't work; the
builder recognises their images and says so.

## Making the image

Xbox game discs use a layout that ordinary PC DVD drives can't read in full, so a normal "copy disc to ISO" on a PC
won't work. There are two usual ways to image a disc you own:

1. **A PC DVD drive that can read Xbox discs.** Some DVD drive models, with firmware made for disc preservation,
   read the Xbox game partition and the rest of the disc. Their disc-imaging software writes a full image (`.iso`)
   and reports checksums you can compare with a preservation database. This gives the full disc image above.
2. **Your own Xbox console.** An original Xbox that runs a homebrew dashboard can copy the disc's game partition to
   its hard drive or to a PC over the network, as a folder or an XISO. Keep or convert it to an XISO file.

Community guides for both methods are easy to find by searching for "Xbox disc dumping" or "Xbox disc preservation".
This project doesn't recommend a particular tool or site.

## Checking the image

```
xml1-builder info --iso "path\to\your image.iso"
```

It reports the format (full image or XISO), the game (title id `4156001E`), whether the image matches a known good
dump, and whether every file the build needs is present. After a build,
`xml1-builder verify --out <build> --iso <image> --deep` also re-checks every file inside the image against its
checksum. A damaged or unknown image is reported with the reason; an unknown but complete image of the right game
is accepted with a warning.

Keep the image somewhere safe: the builder only reads it. After the first build its cache holds what the build needs,
so later rebuilds don't need the image unless you delete the cache.
