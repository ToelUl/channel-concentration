# Reproduce and inspect the candidate

Use Linux/WSL and Python 3.12.13. Unpack the release into a persistent Linux filesystem for execution. The commands below start at the extracted bundle root. No unpublished manuscript or original full ZIP is needed. Dependency installation may use the network.

## Integrity and clean installation

```sh
python tools/verify_release.py
conda create -n cc-baseline-reader --file environment/conda-explicit-linux-64.txt
conda activate cc-baseline-reader
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
python -B -m pip install --no-compile -r environment/requirements-pinned.txt
python -B -m pip install --no-deps --no-compile dist/cc_repro-0.5.2.dev0-py3-none-any.whl
python -B -m pip check
python -B -m pytest software/tests -q -p no:cacheprovider
```

All numerical dependency versions are fixed. The conda specification fixes the Python/base builds; the pip list is derived from installed package metadata, without local file URLs. The source distributions in `dist/` can be installed instead of wheels. Do not install several cc-repro versions simultaneously into one environment.

## Bounded fresh checks

```sh
python -B -m cc_repro exact --workspace ../small-check --run-id exact --mode fast
python -B -m cc_repro potts --workspace ../small-check --run-id potts-L6 --L 6
python -B -m cc_repro nnn-point --workspace ../small-check --run-id nnn-L6 --L 6 --j2 0.2
```

These are new small calculations, not substitutes for the supplied large campaign evidence. The full existing test suite also exercises failure refusals, source tampering, pause/resume and reader identity.

## Read the supplied current results without new eigensolves

```sh
python -B tools/replay_current.py --analysis nnn-ranked --workspace ../read-nnn
python -B tools/replay_current.py --analysis potts-7over5 --workspace ../read-potts-extended
python -B tools/replay_current.py --analysis projector-enclosures --workspace ../read-enclosures
```

The helper verifies the bundle, initializes a new workspace from installed public resources, copies exact raw inputs, calls the existing strict current reader, and compares selected numerical outputs with the bundled baseline. It never changes the receipt identities or numerical method. Use a separate empty workspace for each invocation. Reader environment mismatches are explicit failures; see the limitations document.

For Potts FSS and retained ranked weights, use a **separate environment with the 0.5.0.dev0 wheel**, since the original FSS/ranked adapter checks exact producer identity:

```sh
conda create -n cc-baseline-potts --file environment/conda-explicit-linux-64.txt
conda activate cc-baseline-potts
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
python -B -m pip install --no-compile -r environment/requirements-pinned.txt
python -B -m pip install --no-deps --no-compile dist/cc_repro-0.5.0.dev0-py3-none-any.whl
python -B tools/replay_current.py --analysis potts-fss --workspace ../read-potts-fss
python -B tools/replay_current.py --analysis potts-ranked --workspace ../read-potts-ranks
```

## Fresh large campaigns are optional and separately budgeted

Potts uses producer 0.5.0.dev0; NNN uses producer 0.5.1.dev0 in a separate frozen environment. The included numerical configurations are authoritative. Preserve the original single BLAS/OMP thread setting. Previous numerical jobs used one large job at a time with a 16 GiB memory cap and no swap; the private systemd manager is not included, and `--timeout` alone is not a memory limit. Supply and monitor an equivalent local resource boundary before starting large work.

```sh
# In the 0.5.0.dev0 producer environment, with local resource limits configured:
cc-repro campaign --workspace ../fresh-potts --run-id fixed --model potts --sizes 6 7 8 9 10 11 12 13 14
cc-repro ladder --workspace ../fresh-potts --run-id ladder
cc-repro controls --workspace ../fresh-potts --run-id p2 --control potts-p2
# In the 0.5.1.dev0 producer environment:
cc-repro nnn --workspace ../fresh-nnn --run-id publication --mode publication
```

Resume only through the corresponding original `--resume` entrypoint and verified checkpoint store. Fresh results can differ numerically within the original tolerances and receive new receipts. Do not overwrite the distributed baseline. This release's clean-install checks do not rerun all large eigensolves.

