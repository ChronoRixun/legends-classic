# Using your own X-Men Legends Xbox disc

The builder reads **an image or verified extracted files from your own Xbox disc** of X-Men Legends. It never needs, and this project never links
to, a downloaded copy: only image discs you own, and check the laws that apply where you live.

## What the builder accepts

| Image | What it is | |
|---|---|---|
| **Full disc image** (`.iso`, about 7.8 GB) | every sector of the disc, the way disc-preservation projects image Xbox discs | best: `info` can match it against a known good dump |
| **XISO** (`.iso` / `.xiso`, smaller) | only the disc's game partition (the Xbox file system) | fine: it holds everything the build needs |
| Compressed images (CCI, CSO) | used by some modded consoles and emulators | not yet: decompress back to an ISO with the tool that made it |
| **Extracted install folder** | the original files extracted from your disc, including a recomp install | accepted when every original file the builder needs matches its trusted World dump reference |

The PlayStation 2 and GameCube releases of X-Men Legends are different builds of the game and don't work; the
builder recognises their images and says so.

## Already play the recomp? Point the builder at its folder

Use the folder that contains `default.xbe` and `z/assetsfb.zip`. You do not need to turn it back into an ISO.
The existing `--iso` option accepts either an image file or a folder and detects which you supplied:

```
xml1-builder info --iso "path\to\your recomp folder"
xml1-builder build --iso "path\to\your recomp folder" --xml2 "path\to\your XML2 folder" --out "path\to\a new build"
xml1-builder verify --out "path\to\a new build" --iso "path\to\your recomp folder" --deep
```

`info` reports a verified extracted install only after checking the size and SHA-256 of all 252 required originals
against the builder's reference for the World Xbox dump. It reads `default.xbe`, the original `z/assetsfb.zip`,
the original sound banks under `sounds/zsds`, and the NTSC movies under `movies/ntsc`. Keep the movies even with
`--no-movies`: the builder still reads their details. These checks read the original files and can take a while.

The builder unpacks its assets from the original archive. It ignores the recomp's modified loose assets,
`UDATA`, `TDATA`, and settings. It does not import recomp saves. A missing or changed original stops the build
with a message naming the file; restore that file from your own disc. Folders with an unknown original executable
are refused. The unknown-image warning described below applies to images only.

Required paths and their ancestors must be ordinary files and directories, with no links, junctions, hard links
or names differing only by case. The builder checks names only in the directories needed to find the originals;
it never walks the loose asset or save trees. It detects changes to originals during a build and keeps folder
caches separate from image caches. Choose output, cache and log locations outside the source folder. The source
install stays read-only. After a successful build, you can omit `--iso` to rebuild from its prepared cache.

## Making the image

Xbox game discs use a layout that ordinary PC DVD drives can't read in full, so a normal "copy disc to ISO" on a PC
won't work. There are two usual ways to image a disc you own:

1. **A PC DVD drive that can read Xbox discs.** Some DVD drive models, with firmware made for disc preservation,
   read the Xbox game partition and the rest of the disc. Their disc-imaging software writes a full image (`.iso`)
   and reports checksums you can compare with a preservation database. This gives the full disc image above.
2. **Your own Xbox console.** An original Xbox that runs a homebrew dashboard can copy the disc's game partition to
   its hard drive or to a PC over the network, as a folder or an XISO. Keep the original extracted files or an XISO.

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
