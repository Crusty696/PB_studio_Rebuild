---
type: synthesis
title: Runtime Manifest Drift - 2026-05-31
status: code-complete-live-pending
plan_id: PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31
task: Task 2 - Runtime Manifest Drift Audit/Fix
date: 2026-06-01
---

# Runtime Manifest Drift - 2026-05-31

## Task Quote

`Task 2 - Runtime Manifest Drift Audit/Fix`

## Summary

No manifest pin edit is required by current evidence.

Important drift exists outside the active app runtime: bare `python` resolves to Conda base Python 3.13.12 with Torch 2.6.0+cu124. The active PB Studio runtime used by the passing default gate is `C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe`, Python 3.10.20 with Torch 1.12.1+cu113.

Do not run PB Studio app/test commands with bare `python` unless the shell is explicitly inside the `pb-studio` Conda env.

## Commands Run

```powershell
python --version
python -m pip --version
python -m pip freeze
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" --version
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pip --version
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pip freeze
Get-Content requirements-py310-cu113.txt
Get-Content environment.yml
Get-Content pyproject.toml
Get-Content .github\workflows\ci.yml
python -c "import torch, PySide6, sqlalchemy; print('imports-ok'); print(torch.__version__); print(getattr(torch.version, 'cuda', None)); print(torch.cuda.is_available())"
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -c "import torch, PySide6, sqlalchemy; print('imports-ok'); print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available()); print(sqlalchemy.__version__)"
```

## Interpreter Evidence

| Runtime | Command | Result | Role |
|---|---|---|---|
| Bare shell | `python --version` | `Python 3.13.12` | Not active app runtime |
| Bare shell | `python -m pip --version` | `pip 26.0.1 from C:\Users\David Lochmann\miniconda3\Lib\site-packages\pip (python 3.13)` | Conda base |
| PB Studio env | `pb-studio\python.exe --version` | `Python 3.10.20` | Active app/test runtime |
| PB Studio env | `pb-studio\python.exe -m pip --version` | `pip 26.1.1 from C:\Users\David Lochmann\miniconda3\envs\pb-studio\lib\site-packages\pip (python 3.10)` | Active app/test runtime |

## Import Smoke

Bare shell:

```text
imports-ok
2.6.0+cu124
12.4
True
```

Active PB Studio env:

```text
imports-ok
1.12.1+cu113
11.3
True
2.0.49
```

## Manifest Evidence

| File | Relevant fact | Decision |
|---|---|---|
| `requirements-py310-cu113.txt` | Active target says Python 3.10 + CUDA 11.3 / cu113; exact pins for `torch==1.12.1+cu113`, `torchaudio==0.12.1+cu113`, `torchvision==0.13.1+cu113`. | Matches active env. No edit. |
| `environment.yml` | `name: pb-studio`, `python=3.10`, pip installs `requirements-py310-cu113.txt`. | Matches active env. No edit. |
| `pyproject.toml` | Comments state active target is Python 3.10 + torch 1.12.1+cu113; `requirements.txt` is legacy/future Python 3.11+cu124. Poetry allows `>=3.10,<3.12`. | No edit required for active runtime. |
| `.github/workflows/ci.yml` | Lint job uses Python 3.11 for ruff/bandit only. Unit-tests job uses Windows Python 3.10 and installs `requirements-py310-cu113.txt`. | CI has Python 3.10 runtime gate already. No matrix edit. |

## Drift Table

| Area | Installed / configured evidence | Manifest expectation | Status | Action |
|---|---|---|---|---|
| Shell interpreter | Bare `python` is Python 3.13.12 | Active runtime Python 3.10 | Drift outside app env | Documented; use explicit `pb-studio` env |
| Shell Torch | Bare `python` imports `torch==2.6.0+cu124`, CUDA 12.4 | GTX 1060 active path is cu113 | Drift outside app env | Do not use bare Python for app commands |
| Active env Python | Python 3.10.20 | `environment.yml`: `python=3.10` | Aligned | No edit |
| Active env Torch | `torch==1.12.1+cu113`, `torch.version.cuda == 11.3`, CUDA available `True` | exact cu113 pins | Aligned | No edit |
| PySide6 | Active env `PySide6==6.7.3` | `>=6.6.0,<6.8.0` | Aligned | No edit |
| SQLAlchemy | Active env `SQLAlchemy==2.0.49` | `>=2.0.20,<3.0.0` | Aligned | No edit |
| Alembic | Active env `alembic==1.18.4` | `>=1.13.0,<2.0.0` | Aligned | No edit |
| NumPy | Active env `numpy==1.26.4` | `>=1.24.0,<2.0.0` | Aligned | No edit |
| SciPy | Active env `scipy==1.15.3` | `>=1.11.0,<2.0.0` | Aligned | No edit |
| scikit-learn | Active env `scikit-learn==1.7.2` | `>=1.3.0,<2.0.0` | Aligned | No edit |
| numba | Active env `numba==0.59.1` | `>=0.58.0,<0.60.0` | Aligned | No edit |
| lancedb / pyarrow | Active env `lancedb==0.19.0`, `pyarrow==17.0.0` | `<0.20.0`, `<18.0.0` | Aligned, near upper bound | No edit without failing evidence |
| ONNX runtime | Active env `onnx==1.16.2`, `onnxruntime-gpu==1.18.1` | exact pins | Aligned | No edit |
| Dev tools | Active env `pytest==9.0.3`, `ruff==0.15.12`, `bandit==1.9.4` | `<10`, `<1`, `<2` | Aligned | No edit |
| vectorlite | Active env `vectorlite_py==0.2.0` | `vectorlite-py==0.2.0` | Aligned; normalized package name | No edit |
| CI lint Python | Python 3.11 in lint job | Runtime Python 3.10 for app/tests | Acceptable: lint-only | No edit |
| CI unit Python | Python 3.10 in unit job | Active runtime Python 3.10 | Aligned | No edit |

## Decision

No changes to `requirements-py310-cu113.txt`, `environment.yml`, or `pyproject.toml` are justified by evidence in Task 2.

The fix is documentation and handoff clarity: active app/test commands must use the `pb-studio` Conda env or CI's Python 3.10 unit-test job. Bare shell Python is a different runtime and currently imports a different CUDA stack.

## Active Environment Freeze

```text
accelerate==0.27.2
alembic==1.18.4
altgraph==0.17.5
annotated-types==0.7.0
antlr4-python3-runtime==4.9.3
anyio==4.13.0
apsw==3.53.1.0
audioread==3.0.1
bandit==1.9.4
beat-this @ file:///C:/Users/David%20Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/vendor/beat_this
certifi==2026.4.22
cffi==2.0.0
charset-normalizer==3.4.7
click==8.2.1
cloudpickle==3.1.2
colorama==0.4.6
coloredlogs==15.0.1
comtypes==1.4.16
coverage==7.14.0
decorator==5.2.1
demucs==4.0.1
deprecation==2.1.0
dora_search==0.1.12
einops==0.8.0
exceptiongroup==1.3.1
filelock==3.29.0
flatbuffers==25.12.19
fsspec==2026.3.0
greenlet==3.4.0
h11==0.16.0
httpcore==1.0.9
httpx==0.28.1
huggingface_hub==0.36.2
humanfriendly==10.0
idna==3.13
iniconfig==2.3.0
Jinja2==3.1.6
joblib==1.5.3
julius==0.2.7
lameenc==1.8.2
lancedb==0.19.0
lazy-loader==0.5
librosa==0.10.2
llvmlite==0.42.0
Mako==1.3.11
markdown-it-py==4.0.0
MarkupSafe==3.0.3
mdurl==0.1.2
MouseInfo==0.1.3
mpmath==1.3.0
msgpack==1.1.2
networkx==3.4.2
numba==0.59.1
numpy==1.26.4
omegaconf==2.3.0
onnx==1.16.2
onnxruntime-gpu==1.18.1
opencv-python==4.11.0.86
OpenTimelineIO==0.18.1
openunmix==1.3.0
otio-cmx3600-adapter==1.0.0
overrides==7.7.0
packaging @ file:///home/conda/feedstock_root/build_artifacts/bld/rattler-build_packaging_1777103621/work
pefile==2024.8.26
pillow==11.3.0
platformdirs==4.9.6
pluggy==1.6.0
pooch==1.9.0
protobuf==5.29.6
psutil==7.2.2
pyarrow==17.0.0
PyAutoGUI==0.9.54
pycparser==3.0
pydantic==2.13.4
pydantic_core==2.46.4
PyGetWindow==0.0.9
Pygments==2.20.0
pyinstaller==6.20.0
pyinstaller-hooks-contrib==2026.5
pylance==0.23.0
PyMsgBox==2.0.1
pynndescent==0.6.0
pyperclip==1.11.0
pyqtgraph==0.13.7
pyreadline3==3.5.4
PyRect==0.2.0
PyScreeze==1.0.1
PySide6==6.7.3
PySide6_Addons==6.7.3
PySide6_Essentials==6.7.3
pytest==9.0.3
pytest-cov==7.1.0
python-dotenv==1.2.2
pytweening==1.2.0
pywin32==311
pywin32-ctypes==0.2.3
pywinauto==0.6.9
PyYAML==6.0.3
RapidFuzz==3.14.5
regex==2026.5.9
requests==2.34.1
retrying==1.4.2
rich==14.3.4
rotary-embedding-torch==0.3.6
ruff==0.15.12
safetensors==0.4.2
scenedetect==0.7
scikit-learn==1.7.2
scipy==1.15.3
sentencepiece==0.2.1
shiboken6==6.7.3
six==1.17.0
sounddevice==0.5.1
soundfile==0.12.1
soxr==0.3.7
SQLAlchemy==2.0.49
sqlite-vec==0.1.9
stevedore==5.7.0
submitit==1.5.4
sympy==1.14.0
thefuzz==0.22.1
threadpoolctl==3.6.0
tokenizers==0.15.2
tomli==2.4.1
torch==1.12.1+cu113
torchaudio==0.12.1+cu113
torchvision==0.13.1+cu113
tqdm==4.67.3
transformers==4.38.2
treetable==0.2.6
typing-inspection==0.4.2
typing_extensions==4.15.0
umap-learn==0.5.12
urllib3==2.7.0
vectorlite_py==0.2.0
```

## Bare Shell Freeze Snapshot

Full bare `python -m pip freeze` capture:

```text
alembic==1.18.4
anaconda-anon-usage @ file:///opt/miniconda3/conda-bld/anaconda-anon-usage_1764636648062/work
anaconda-auth @ file:///C:/Users/task_177249130442320/croot/anaconda-cloud-auth-split_1772491372848/work
anaconda-cli-base @ file:///C:/Users/task_177038553276457/croot/anaconda-cli-base_1770385908202/work
annotated-types @ file:///C:/miniconda3/conda-bld/annotated-types_1761745107361/work
antlr4-python3-runtime==4.9.3
anyio @ file:///C:/miniconda3/conda-bld/anyio_1758622433823/work
archspec @ file:///home/task_175812491784513/conda-bld/archspec_1758124989039/work
audioop-lts==0.2.2
audioread==3.1.0
beat-this==1.1.0
boltons @ file:///C:/b/abs_e2_iokhxbp/croot/boltons_1751383740243/work
brotlicffi @ file:///C:/miniconda3/conda-bld/brotlicffi_1764961374486/work
certifi @ file:///C:/Users/task_176765924055489/croot/certifi_1767659363027/work/certifi
cffi @ file:///C:/miniconda3/conda-bld/cffi_1761832792955/work
charset-normalizer @ file:///C:/miniconda3/conda-bld/charset-normalizer_1761744975868/work
click @ file:///C:/miniconda3/conda-bld/click_1764332372183/work
cloudpickle==3.1.2
colorama @ file:///C:/Users/dev-admin/perseverance-python-buildout/croot/colorama_1729036581634/work
comtypes==1.4.16
conda @ file:///C:/Users/task_177140157604822/croot/conda_1771402255672/work/conda-src
conda-anaconda-telemetry @ file:///croot/conda-anaconda-telemetry_1755883788794/work
conda-anaconda-tos @ file:///C:/b/abs_c9yejtsx9g/croot/conda-anaconda-tos_1755123332641/work
conda-content-trust @ file:///C:/Users/dev-admin/perseverance-python-buildout/croot/conda-content-trust_1729088072778/work
conda-libmamba-solver @ file:///C:/miniconda3/conda-bld/conda-libmamba-solver_1764245615235/work/src
conda-package-handling @ file:///C:/miniconda3/conda-bld/conda-package-handling_1762366515145/work
conda_package_streaming @ file:///C:/miniconda3/conda-bld/conda-package-streaming_1762361689679/work
cryptography @ file:///C:/Users/task_177247529657270/croot/cryptography-split_1772475408670/work
decorator==5.2.1
demucs==4.0.1
distro @ file:///C:/Users/dev-admin/perseverance-python-buildout/croot/distro_1729059153117/work
dora_search==0.1.12
einops==0.8.2
filelock==3.29.0
frozendict @ file:///C:/miniconda3/conda-bld/frozendict_1761750728192/work
fsspec==2026.4.0
greenlet==3.5.0
h11 @ file:///C:/miniconda3/conda-bld/h11_1761931384726/work
httpcore @ file:///C:/b/abs_25m7_xthp6/croot/httpcore_1748526065845/work
httpx @ file:///C:/miniconda3/conda-bld/httpx_1760447475275/work
idna @ file:///C:/miniconda3/conda-bld/idna_1761912043388/work
jaraco.classes @ file:///C:/b/abs_6erueoob1v/croot/jaraco.classes_1755516340851/work
jaraco.context @ file:///C:/Users/task_176947773609372/croot/jaraco.context_1769477902330/work
jaraco.functools @ file:///C:/Users/task_176838914677671/croot/jaraco.functools_1768389438594/work
Jinja2==3.1.6
joblib==1.5.3
jsonpatch @ file:///C:/Users/dev-admin/perseverance-python-buildout/croot/jsonpatch_1729054776004/work
jsonpointer @ file:///C:/b/abs_73u73l7pl9/croot/jsonpointer_1753788460913/work
julius==0.2.7
keyring @ file:///C:/miniconda3/conda-bld/keyring_1763637203252/work
lameenc==1.8.2
lazy-loader==0.5
Levenshtein==0.27.3
libmambapy @ file:///C:/miniconda3/conda-bld/mamba-split_1763111608356/work/libmambapy
librosa==0.11.0
llvmlite==0.47.0
Mako==1.3.12
markdown-it-py @ file:///C:/Users/task_176700171154409/croot/markdown-it-py_1767001834659/work
MarkupSafe==3.0.3
mdurl @ file:///C:/miniconda3/conda-bld/mdurl_1758552277768/work
menuinst @ file:///C:/miniconda3/conda-bld/menuinst_1765382397455/work
more-itertools @ file:///C:/miniconda3/conda-bld/more-itertools_1761121564395/work
MouseInfo==0.1.3
mpmath==1.3.0
msgpack @ file:///C:/b/abs_4b3t4uhz3r/croot/msgpack-python_1750958631084/work
natsort==8.4.0
networkx==3.6.1
numba==0.65.1
numpy==2.4.5
omegaconf==2.3.0
openunmix==1.3.0
packaging @ file:///C:/miniconda3/conda-bld/packaging_1761049099114/work
pillow==12.2.0
pkce @ file:///C:/Users/dev-admin/perseverance-python-buildout/croot/pkce_1729049216383/work
platformdirs @ file:///C:/miniconda3/conda-bld/platformdirs_1762356623609/work
pluggy @ file:///C:/b/abs_dfec_m79vo/croot/pluggy_1733170145382/work
pooch==1.9.0
psutil==7.2.2
PyAutoGUI==0.9.54
pycosat @ file:///C:/b/abs_18nblzzn70/croot/pycosat_1736868434419/work
pycparser @ file:///C:/miniconda3/conda-bld/pycparser_1757496153123/work
pydantic @ file:///C:/miniconda3/conda-bld/pydantic_1764083582233/work
pydantic-settings @ file:///C:/miniconda3/conda-bld/pydantic-settings_1764165236385/work
pydantic_core @ file:///C:/miniconda3/conda-bld/pydantic-core_1764009799098/work
PyGetWindow==0.0.9
Pygments @ file:///C:/miniconda3/conda-bld/pygments_1762431428918/work
PyJWT @ file:///C:/miniconda3/conda-bld/pyjwt_1764332257117/work
PyMsgBox==2.0.1
pynndescent==0.6.0
pyperclip==1.11.0
pyqtgraph==0.13.7
PyRect==0.2.0
PyScreeze==1.0.1
PySide6==6.11.1
PySide6_Addons==6.11.1
PySide6_Essentials==6.11.1
PySocks @ file:///C:/miniconda3/conda-bld/pysocks_1761753030965/work
python-dotenv @ file:///C:/Users/task_176855922952874/croot/python-dotenv_1768559755085/work
python-Levenshtein==0.27.3
pytweening==1.2.0
pywin32==311
pywin32-ctypes @ file:///C:/Users/task_176829651200310/croot/pywin32-ctypes_1768296624234/work
pywinauto==0.6.9
PyYAML==6.0.3
RapidFuzz==3.14.5
readchar @ file:///C:/miniconda3/conda-bld/readchar_1760613474723/work
requests @ file:///C:/miniconda3/conda-bld/requests_1762359611326/work
retrying==1.4.2
rich @ file:///C:/miniconda3/conda-bld/rich_1760375661587/work
rotary-embedding-torch==0.8.9
ruamel.yaml @ file:///C:/miniconda3/conda-bld/ruamel.yaml_1762536064547/work
ruamel.yaml.clib @ file:///C:/miniconda3/conda-bld/ruamel.yaml.clib_1762530094515/work
scikit-learn==1.8.0
scipy==1.17.1
semver @ file:///C:/miniconda3/conda-bld/semver_1761903323755/work
setuptools==80.10.2
shellingham @ file:///C:/miniconda3/conda-bld/shellingham_1761912227081/work
shiboken6==6.11.1
six==1.17.0
sniffio @ file:///C:/miniconda3/conda-bld/sniffio_1764329222593/work
sounddevice==0.5.5
soundfile==0.13.1
soxr==1.1.0
SQLAlchemy==2.0.49
standard-aifc==3.13.0
standard-chunk==3.13.0
standard-sunau==3.13.0
submitit==1.5.4
sympy==1.13.1
thefuzz==0.22.1
threadpoolctl==3.6.0
tomli @ file:///C:/Users/task_176829653470725/croot/tomli_1768296655778/work
tomlkit @ file:///C:/miniconda3/conda-bld/tomlkit_1762896656167/work
torch==2.6.0+cu124
torchaudio==2.6.0+cu124
torchvision==0.21.0+cu124
tqdm @ file:///C:/Users/task_177139862118811/croot/tqdm_1771398768256/work
treetable==0.2.6
truststore @ file:///C:/miniconda3/conda-bld/truststore_1762521027919/work
typer==0.20.0
typer-slim==0.20.0
typing-inspection @ file:///C:/miniconda3/conda-bld/typing-inspection_1760614188477/work
typing_extensions @ file:///C:/b/abs_ecq8gc0vbm/croot/typing_extensions_1756281142218/work
umap-learn==0.5.12
urllib3 @ file:///C:/Users/task_176781035981662/croot/urllib3_1767810483132/work
wheel==0.46.3
win_inet_pton @ file:///C:/miniconda3/conda-bld/win_inet_pton_1761746278300/work
zstandard @ file:///C:/miniconda3/conda-bld/zstandard_1758189089298/work
```

## Verification Status

- Import smoke in bare shell: passed, but proves wrong runtime for app target.
- Import smoke in active PB Studio env: passed.
- Default gate carryover before Task 2: `2315 passed, 37 skipped, 6 deselected, 62 warnings in 810.22s`.
- App live verification: not run.
- `fixed` status written: no.
