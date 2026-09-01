# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['api.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'diffusers', 'transformers', 'whisper', 'llama_cpp', 'accelerate', 'matplotlib', 'numpy', 'scipy'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='backend',
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

# onedir, not onefile: a onefile exe is really a bootloader that unpacks
# itself and launches a *separate child process* to do the real work — that
# child does not reliably inherit the parent's Windows Job Object, so
# force-killing Flutter could leave it running. onedir is a single real
# process, so the Job Object covers it directly with no propagation gap.
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='backend',
)
