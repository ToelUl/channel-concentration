# Selected original computation sources

Numerical producers and scientific configurations retain their exact source bytes.
`common.py` has a documented candidate-run I/O change: no frozen figures are copied.
`runtime/cft_runtime.py` extracts the original CFT route and required path helpers
without changing function bodies. `project.toml` is a new public I/O profile.
Use the supported `cc-repro` CLI described in the repository README; legacy
qualification/document/packaging controllers are not a supported public interface.
The original plotting producer is retained unchanged as readable source. The
public figures command checks its registry and input paths, not manuscript TeX.
No manuscript, supplemental source, or rendered artwork is included.
