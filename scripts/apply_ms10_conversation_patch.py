from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = (
    ROOT
    / "services"
    / "conversation_application_service.py"
)


def replace_once(
    content: str,
    old: str,
    new: str,
    *,
    label: str,
) -> str:
    count = content.count(old)

    if count != 1:
        raise RuntimeError(
            f"Expected one {label} patch target, "
            f"found {count}."
        )

    return content.replace(old, new, 1)


def main() -> None:
    content = SERVICE_PATH.read_text(
        encoding="utf-8"
    )

    import_line = (
        "from services.planner_history import (\n"
        "    build_recent_planner_messages,\n"
        ")\n"
    )

    if import_line not in content:
        marker = (
            "from services.recording_tool_registry import (\n"
        )
        content = replace_once(
            content,
            marker,
            import_line + marker,
            label="planner-history import",
        )

    if "recent_messages=(" not in content:
        with_thread = (
            "                    context=current_context,\n"
            "                    thread_id=conversation_id,\n"
        )
        without_thread = (
            "                    context=current_context,\n"
            "                )\n"
        )
        replacement = (
            "                    context=current_context,\n"
            "                    recent_messages=(\n"
            "                        build_recent_planner_messages(\n"
            "                            previous_messages\n"
            "                        )\n"
            "                    ),\n"
            "                    thread_id=conversation_id,\n"
        )

        if with_thread in content:
            content = replace_once(
                content,
                with_thread,
                replacement,
                label="ChatTurnInput history",
            )
        elif without_thread in content:
            content = replace_once(
                content,
                without_thread,
                replacement + "                )\n",
                label="ChatTurnInput history and thread",
            )
        else:
            raise RuntimeError(
                "Could not locate ChatTurnInput "
                "construction."
            )

    SERVICE_PATH.write_text(
        content,
        encoding="utf-8",
    )
    print(
        "Applied MS10 conversation-awareness "
        "patch to:",
        SERVICE_PATH,
    )


if __name__ == "__main__":
    main()
