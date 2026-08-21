# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_submodules,
)


project_root = Path(SPECPATH).parent
release_root = project_root / "release"
staging_root = release_root / "staging"

rag_root = staging_root / "rag"
automator_root = (
    staging_root
    / "automator"
    / "main"
)

entry_point = release_root / "beta_entry.py"
release_env = release_root / "release.env"


required_paths = [
    entry_point,
    rag_root / "src",
    automator_root / "automator_service.py",
]

for required_path in required_paths:
    if not required_path.exists():
        raise RuntimeError(
            f"Required release path is missing: {required_path}"
        )


datas = [
    (
        str(rag_root),
        "services/rag",
    ),
    (
        str(staging_root / "automator"),
        "services/automator",
    ),
]

if release_env.is_file():
    datas.append(
        (
            str(release_env),
            ".",
        )
    )


# Dependencies used through dynamic imports need to be visible to
# PyInstaller even though they may not appear in the entry-point import graph.
hiddenimports = [
    "src.rag_service",
    "src.rag_revision_service",
    "src.rag_read_service",
    "src.rag_result_store_service",
    "automator_service",
    "src.rag_explorer_update_service",
]

hiddenimports += collect_submodules(
    "langgraph"
)
hiddenimports += collect_submodules(
    "langgraph.checkpoint.postgres"
)
hiddenimports += collect_submodules(
    "langchain_postgres"
)
hiddenimports += collect_submodules(
    "supabase"
)
hiddenimports += collect_submodules(
    "pywinauto"
)

# Let normal PyInstaller hooks handle PySide6 binaries and plugins.
datas += collect_data_files(
    "certifi",
)


analysis = Analysis(
    [str(entry_point)],
    pathex=[
        str(project_root),
        str(rag_root),
        str(automator_root),
    ],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "unittest.mock",
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="MetaStockAgentBeta",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)