# Stable and beta builder releases

The release workflow accepts `vX.Y.Z`, `vX.Y.Z-beta.N`, and `vX.Y.Z-rc.N`, without leading
zeroes in numeric components. The numeric base must match `VERSION` in
`tools/xml1builder/__init__.py`. Keep that source version numeric; CI passes the full tag in
`XML1_RELEASE_TAG` to the freezer and both smoke runs. A suffix does not change `CONTENT_VERSION`
or assign a new lobby identity. Changes to generated game output still require the content
version and release-identity work described in the [release checklist](RELEASE_CHECKLIST.md).

**0.4.1 (the port's beta 8):** `REQUIRED_XML2FIX` is `1.9` and `REQUIRED_XML2FIX_PRERELEASE` `beta.1`, so a 0.4.1 beta
declares `>=1.9.0-beta.1` and the stable 0.4.1 `>=1.9`; neither XML2 Fix 1.8.0-beta.7 nor a stable 1.8.0 satisfies
it (it knows none of the beta 8 keys and runs rule 16 as revision 11). Tags for that line: `v0.4.1-beta.N` here and
`v1.9.0-beta.N` for XML2 Fix (numeric bases 0.4.1 / 1.9.0, set by the release step). The 0.4.0 notes follow.

Beta and rc builders declare `requires_xml2fix: ">=1.8.0-beta.7"` in the release manifest and
`requires.xml2fix` in the generated build stamp (`REQUIRED_XML2FIX_PRERELEASE`, `beta.7` since
0.4.0-beta.7, which writes the schema 4 `[NpcSemiAuto]` rows for every gun NPC, `[Game] ClassicSpeakers` and
`[Game] WorldBackfaces`, first read by XML2 Fix 1.8.0-beta.7), so companion `1.8.0-beta.7` and later betas, rc and
final fixes satisfy the requirement while `1.8.0-beta.6` and older and `1.7.x` do not (0.4.0-beta.6 declared
`>=1.8.0-beta.6`, 0.4.0-beta.5 `>=1.8.0-beta.5`, 0.3.0-beta.3 and 0.4.0-beta.4 `>=1.8.0-beta.3`, 0.3.0-beta.2 `>=1.8.0-beta.2`,
0.3.0-beta.1 `>=1.8.0-0`). Stable builders retain the exact `>=1.8`
requirement. Both paths use `xml1build.fix_ini.required_xml2fix`; `REQUIRED_XML2FIX` stays numeric.
The builder's installed-DLL checks still require the 1.8 capabilities, so beta DLLs with numeric
`1.8.0.x` VERSIONINFO work and an older DLL missing those capabilities is refused.

The full version, without the leading `v`, appears in `xml1-builder.json`, bundled
`build-info.json`, the frozen builder's `--version` and JSON hello events, and the zip name.
Windows numeric VERSIONINFO stays `X.Y.Z.0`; its string fields carry the full version.
The manifest keeps its existing keys. Launcher 0.3.2 (`b83afac`) and the 0.4.0 candidate
(`14e718f`) accept the suffix: `tools/tool_install.cpp::parse_manifest` validates `version`
through `tools/tool_check.cpp::is_safe_version`, which permits letters, digits, dots and hyphens.
The zip-name checks and builder hello-event reader also preserve the full string. Their legacy
dotted-number comparator is not semver-aware; Beta release selection uses the companion
launcher's semver/API logic. Stable users continue receiving the stable `releases/latest` feed.
Assets use the same names in both channels:

- `xml1-builder-<version>-win64.zip`, for example `xml1-builder-0.4.0-beta.4-win64.zip`.
- `xml1-builder.json`.
- `SHA256SUMS.txt`.

Beta and rc releases use `--prerelease --latest=false` when created **and when an existing
release is edited**. Their notes start with `Beta - test build` and include the `## vX.Y.Z`
base section of `CHANGELOG.md`, standalone instructions and checksums. The base section must
exist for prereleases. Stable releases keep their default GitHub flags and missing-section
behavior. Stable launchers resolve `releases/latest`; Beta launchers select the highest semver
release including prereleases and fetch the manifest and zip by the selected tag.

## Cut a beta

First commit and review the workflow changes, check the numeric source base and its changelog
section, and complete the applicable [local release gates](RELEASE_CHECKLIST.md). From this
repository, for the current `0.4.0` base:

```powershell
python tools/test_release_metadata.py
python tools/freeze_builder.py --check-tag v0.4.0-beta.4
git tag -a v0.4.0-beta.4 -m "Legends Classic 0.4.0 beta 4"
git push https://github.com/ChronoRixun/legends-classic.git refs/tags/v0.4.0-beta.4
```

Increment to `v0.4.0-beta.5` for the next candidate, or use `v0.4.0-rc.1`. Do not reuse tags.
The betas `v0.3.0-beta.1` to `v0.3.0-beta.3` were cut before the line was renumbered (no stable 0.3.0 was
published); the numbering continues at `v0.4.0-beta.4`.
The stable tag is `v0.4.0`, placed on the reviewed stable commit. Pushing a tag starts the
release workflow and publishes the release; these maintainer instructions do not authorize
publication during a local-only task.

To freeze a prerelease locally with the pinned toolchain and compiled sound kernel:

```powershell
$env:XML1_RELEASE_TAG = 'v0.4.0-beta.4'
python tools/freeze_builder.py --smoke
Remove-Item Env:XML1_RELEASE_TAG
```

`python tools/freeze_smoke.py <unpacked-folder>` also accepts a beta/rc bundle without that
environment variable: it validates the bundle's version against the source's numeric base.

The policy script tests tags, flags, base-version mismatches, note extraction, the manifest
version/zip naming, and frozen runtime identity using synthetic files. A real tag run must
still prove native-kernel compilation, PyInstaller freezing, both executable smoke runs,
artifact transfer, and GitHub's prerelease/latest state (including an existing release).
Confirm that `releases/latest` remains on the stable tag after publishing a beta.
