from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


APP_NAME = "MetaStockAgent"


def is_frozen() -> bool:
    """Return True when running inside a PyInstaller executable."""
    return bool(getattr(sys, "frozen", False))


def get_bundle_root() -> Path:
    """
    Frozen mode:
        Return PyInstaller's temporary extraction directory.

    Source mode:
        Return the release directory containing this file.
    """
    if is_frozen():
        bundle_path = getattr(sys, "_MEIPASS", None)

        if not bundle_path:
            raise RuntimeError(
                "Frozen application does not expose its bundle directory."
            )

        return Path(bundle_path).resolve()

    return Path(__file__).resolve().parent


def get_executable_directory() -> Path:
    """
    Frozen mode:
        Directory containing MetaStockAgentBeta.exe.

    Source mode:
        Current working directory, normally the repository root.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent

    return Path.cwd().resolve()


def configure_application_import_path(
    bundle_root: Path,
) -> None:
    """
    Make the MetaStock Agent repository importable when beta_entry.py
    is executed directly from the release directory.

    PyInstaller handles application imports itself in frozen mode.
    """
    if is_frozen():
        return

    repository_root = bundle_root.parent.resolve()
    repository_root_string = str(repository_root)

    if repository_root_string not in sys.path:
        sys.path.insert(0, repository_root_string)

def load_release_environment(
    *,
    bundle_root: Path,
    executable_directory: Path,
) -> Path | None:
    """
    Source mode:
        Prefer release/release.env so the source smoke test uses the
        same configuration that will be bundled.

    Frozen mode:
        Prefer an optional external .env beside the executable, then
        fall back to the bundled release.env.
    """
    bundled_env = bundle_root / "release.env"

    if not is_frozen():
        if bundled_env.is_file():
            load_dotenv(
                bundled_env,
                override=True,
            )
            return bundled_env

        return None

    external_env = executable_directory / ".env"

    if external_env.is_file():
        load_dotenv(
            external_env,
            override=True,
        )
        return external_env

    if bundled_env.is_file():
        load_dotenv(
            bundled_env,
            override=True,
        )
        return bundled_env

    return None


def find_first_directory(
    candidates: list[Path],
    *,
    label: str,
) -> Path:
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()

    formatted_candidates = "\n".join(
        f"  - {candidate}"
        for candidate in candidates
    )

    raise RuntimeError(
        f"{label} directory is missing. Checked:\n"
        f"{formatted_candidates}"
    )


def resolve_runtime_service_directories(
    bundle_root: Path,
) -> tuple[Path, Path]:
    """
    Frozen executable layout:

        _MEIPASS/
          services/
            rag/
            automator/
              main/

    Source smoke-test layout:

        release/
          staging/
            rag/
            automator/
              main/

    Legacy staging folder names are accepted temporarily so the
    launcher also works before those folders are renamed.
    """
    if is_frozen():
        rag_candidates = [
            bundle_root / "services" / "rag",
        ]
        automator_candidates = [
            bundle_root
            / "services"
            / "automator"
            / "main",
        ]
    else:
        staging_root = bundle_root / "staging"

        rag_candidates = [
            staging_root / "rag",
            staging_root / "metastock-RAG-LLM",
        ]

        automator_candidates = [
            staging_root / "automator" / "main",
            staging_root
            / "metastock-automator"
            / "main",
        ]

    rag_directory = find_first_directory(
        rag_candidates,
        label="RAG service",
    )

    automator_directory = find_first_directory(
        automator_candidates,
        label="Automator service",
    )

    return rag_directory, automator_directory


def configure_runtime_paths(
    bundle_root: Path,
) -> tuple[Path, Path]:
    rag_directory, automator_directory = (
        resolve_runtime_service_directories(
            bundle_root
        )
    )

    rag_service = (
        rag_directory
        / "src"
        / "rag_service.py"
    )
    automator_service = (
        automator_directory
        / "automator_service.py"
    )

    if not rag_service.is_file():
        raise RuntimeError(
            "RAG staging directory does not contain "
            f"src\\rag_service.py: {rag_service}"
        )

    if not automator_service.is_file():
        raise RuntimeError(
            "Automator staging directory does not contain "
            f"automator_service.py: {automator_service}"
        )

    os.environ["METASTOCK_RAG_REPO"] = str(
        rag_directory
    )
    os.environ["METASTOCK_AUTOMATOR_REPO"] = str(
        automator_directory
    )

    return rag_directory, automator_directory


def configure_writable_directory() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")

    if not local_app_data:
        local_app_data = str(
            get_executable_directory()
        )

    app_data_directory = (
        Path(local_app_data)
        / APP_NAME
    )

    app_data_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    os.environ.setdefault(
        "METASTOCK_APP_DATA_DIR",
        str(app_data_directory),
    )

    return app_data_directory


def main() -> int:
    bundle_root = get_bundle_root()
    executable_directory = (
        get_executable_directory()
    )

    configure_application_import_path(
        bundle_root
    )

    environment_path = load_release_environment(
        bundle_root=bundle_root,
        executable_directory=(
            executable_directory
        ),
    )

    rag_directory, automator_directory = (
        configure_runtime_paths(
            bundle_root
        )
    )

    app_data_directory = (
        configure_writable_directory()
    )

    mode = "frozen" if is_frozen() else "source"

    print(f"[release] Runtime mode: {mode}")
    print(f"[release] Bundle root: {bundle_root}")
    print(
        "[release] Environment: "
        f"{environment_path or 'not found'}"
    )
    print(f"[release] RAG service: {rag_directory}")
    print(
        "[release] Automator service: "
        f"{automator_directory}"
    )
    print(
        "[release] Writable data: "
        f"{app_data_directory}"
    )

    # Import only after paths and environment variables are ready.
    #
    # scripts.desktop_app creates QApplication before constructing the
    # Automator client, preserving the required Windows GUI/OLE order.
    from scripts.desktop_app import (
        main as desktop_main,
    )

    return desktop_main()


if __name__ == "__main__":
    raise SystemExit(main())