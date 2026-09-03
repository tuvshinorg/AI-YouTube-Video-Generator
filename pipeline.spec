# -*- mode: python ; coding: utf-8 -*-
# Bundles pipeline.py + modules/ for the "no local Python needed" release —
# the Codex-only path (AI_PROVIDER=codex, IMAGE_PROVIDER=codex): text and
# images go through Codex, so the only heavy local dependency left is
# Whisper/transformers for subtitles, and this is built against a CPU-only
# torch (see .build_venv) specifically to keep that small. Excludes
# llama_cpp/diffusers/accelerate — the local-LLM/local-Flux path needs a
# real `pip install -r requirements.txt` checkout instead; see README.
#
# transformers and whisper both do import-time work PyInstaller's static
# analysis can't see (transformers' lazy-module __getattr__ proxies;
# whisper's bundled mel-filter/tokenizer assets aren't Python source at
# all) — collect_all() pulls in everything each package ships, not just
# what a plain Analysis() would find by parsing import statements.
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []

for pkg in ("whisper", "transformers", "tokenizers", "safetensors", "huggingface_hub", "fasttext", "edge_tts"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ['pipeline.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['llama_cpp', 'diffusers', 'accelerate', 'matplotlib', 'tkinter', 'PyQt5', 'PySide2'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='pipeline',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# onedir, matching backend.spec — see that file's comment on why (Job
# Object propagation to force-killed child processes needs one real
# process, not a onefile bootloader's unpacked child).
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='pipeline',
)
