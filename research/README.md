# Research notes

The reverse engineering and design work behind the port, in our own words: how the two games' file formats work,
what XMen2.exe (X-Men Legends II PC) and the first game's Xbox executable do at given addresses, and what was
measured or verified in game. The pipeline's specifications (`tools/xml1build/SPEC.md`, `SPEC_heroes.md`) cite these
notes for their decisions.

| Folder | What |
|---|---|
| `_summaries/` | early survey summaries (characters, scripts, sound, the whole-data sweep) |
| `characters/` | character / skin / animation namespaces, stats schema, the Ghidra helper (`ghidra/`) |
| `heroes/` | playable heroes: roster, powers, party seating, forced parties, levels, conversation speakers |
| `scripts/` | the script engines: function tables of both executables, the XML1 -> XML2 function map, variables |
| `sound/` | the sound bank formats (ZSND), the Xbox -> PC audio conversion, layered music (`music0x20/`) |
| `sweep/` | the whole-data sweep: zones, missions and the reachability graph, bundle overlaps, UI inventory |
| `frontend/`, `input/`, `automaps/`, `limits/`, `online/` | menus, controller prompts, automaps, engine limits, online play |
| `campaign/`, `regression/` | play-test and regression reports |
| `release/` | the builder's design and the publishing rules (`BUILDER_DESIGN.md`) |

**What is here and what isn't.** The notes, the scripts that produced the findings, and fact tables (names,
addresses, counts, hashes) are here. Decoded game files, game text, disassembly listings and screenshots are not -
they stay on the machine of whoever produced them (see CONTRIBUTING.md). Some notes mention such outputs by name
(`out/`, `verify/*.txt`, screenshots): run the script to make them from your own copy.

**Running the research scripts.** They were written against the data the builder extracts from your own disc (the
`disc/loose`, `disc/assets` and `disc/xbox` folders of a build cache, which older scripts call `xml1_loose/`,
`xml1_assets/` and `xml1_xbox/` at the repository root) and your X-Men Legends II install (`XML2_DIR`, default a
folder named `X-Men Legends II` in the current directory). Most are one-off probes kept for the record; the ones the
build depends on have been ported into `tools/xml1build/` (prepare stages and `lib/`) and the old files are thin
shims.

The two tables the builder reads from here that carried game text ship without it: `sweep/graph.json` without the
mission names and descriptions (the builder takes them from your disc), `sweep/zones.json` reduced to the two fields
the build reads.
