# Baseline overview

The public numerical baseline is release `baseline-2026-09-09-rc1`, committed at `6fa71d1fc3d894d76a1b4ac8a17b37cc454d51da`. Its published status is a prerelease. That label identifies the release; it does not invalidate the archived numerical evidence or certify a final manuscript.

## Contents

- Original computational sources and separate frozen producer versions.
- Project numerical data, parameters, retained evidence, and provenance.
- Fixed environment specifications, wheels, and source distributions.
- Integrity tools, bounded regression tests, and current-result replay helpers.

The Potts producer is version `0.5.0.dev0`; the NNN producer is `0.5.1.dev0`; the compatible reader is `0.5.2.dev0`. Use separate environments for the versions. Some original postprocessing routes require the exact original producer identity.

## Ways to use the release

1. Verify distributed bytes with the standalone integrity checker.
2. Install a selected version in the documented Linux/WSL environment and run bounded tests.
3. Read the archived results through the documented strict replay routes, preserving their environment checks.
4. Run new small calculations in a separate workspace if needed.
5. Treat any fresh large campaign as separate, explicitly resourced work.

The final NNN invocation resumed existing results for 69 unique tasks and calculated no new tasks. The baseline records what was actually executed; resume completion must not be described as a fresh rerun of all tasks.

## Historical records

Files inside `baseline/` retain the original sealed content. Some historical descriptions predate public release, and two archived documents contain Chinese text. They remain unchanged to preserve their hashes. The current README and this English documentation provide a complete entry path without requiring those historical documents.

The baseline is numerical evidence, not a claim that every historical validation record is available. Preserve all qualifications in the [limitations document](https://github.com/ToelUl/channel-concentration/blob/6fa71d1fc3d894d76a1b4ac8a17b37cc454d51da/baseline/docs/KNOWN_LIMITATIONS.md), including conditional numerical premises and historical gaps.

See [verification](VERIFICATION.md) for the scope of the completed checks and [the release](https://github.com/ToelUl/channel-concentration/releases/tag/baseline-2026-09-09-rc1) for the downloadable assets.
