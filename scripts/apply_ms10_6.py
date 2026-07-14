from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(
    path: Path,
    old: str,
    new: str,
    *,
    already_present: str | None = None,
) -> None:
    content = path.read_text(
        encoding="utf-8"
    )

    if (
        already_present is not None
        and already_present in content
    ):
        print(f"Already patched: {path}")
        return

    count = content.count(old)

    if count != 1:
        raise RuntimeError(
            f"Expected one patch target in "
            f"{path}, found {count}."
        )

    path.write_text(
        content.replace(old, new, 1),
        encoding="utf-8",
    )
    print(f"Patched: {path}")


def patch_conversation_service() -> None:
    path = (
        ROOT
        / "services"
        / "conversation_application_service.py"
    )

    replace_once(
        path,
        (
            "from infrastructure.agent_state."
            "conversation_repository import (\n"
        ),
        (
            "from infrastructure.agent_state."
            "checkpoints import (\n"
            "    CheckpointStoreProtocol,\n"
            ")\n"
            "from infrastructure.agent_state."
            "conversation_repository import (\n"
        ),
        already_present=(
            "CheckpointStoreProtocol"
        ),
    )

    replace_once(
        path,
        (
            "        controller_factory: "
            "ControllerFactory,\n"
            "        context_resolver: (\n"
        ),
        (
            "        controller_factory: "
            "ControllerFactory,\n"
            "        checkpoints: (\n"
            "            CheckpointStoreProtocol "
            "| None\n"
            "        ) = None,\n"
            "        context_resolver: (\n"
        ),
        already_present=(
            "self._checkpoints = checkpoints"
        ),
    )

    replace_once(
        path,
        (
            "        self._controller_factory = "
            "controller_factory\n"
            "        self._context_resolver = (\n"
        ),
        (
            "        self._controller_factory = "
            "controller_factory\n"
            "        self._checkpoints = "
            "checkpoints\n"
            "        self._context_resolver = (\n"
        ),
        already_present=(
            "self._checkpoints = checkpoints"
        ),
    )

    replace_once(
        path,
        (
            "    def clear_conversation(\n"
            "        self,\n"
            "        conversation_id: UUID,\n"
            "    ) -> ConversationRecord:\n"
            "        return self._conversations."
            "clear_content(\n"
            "            conversation_id\n"
            "        )\n"
        ),
        (
            "    def clear_conversation(\n"
            "        self,\n"
            "        conversation_id: UUID,\n"
            "    ) -> ConversationRecord:\n"
            "        self._conversations.require(\n"
            "            conversation_id\n"
            "        )\n"
            "        self._delete_checkpoint_thread(\n"
            "            conversation_id\n"
            "        )\n"
            "        return self._conversations."
            "clear_content(\n"
            "            conversation_id\n"
            "        )\n"
        ),
        already_present=(
            "self._delete_checkpoint_thread(\n"
            "            conversation_id\n"
            "        )"
        ),
    )

    replace_once(
        path,
        (
            "    def delete_conversation(\n"
            "        self,\n"
            "        conversation_id: UUID,\n"
            "    ) -> bool:\n"
            "        return self._conversations.delete(\n"
            "            conversation_id\n"
            "        )\n"
        ),
        (
            "    def delete_conversation(\n"
            "        self,\n"
            "        conversation_id: UUID,\n"
            "    ) -> bool:\n"
            "        if not self._conversations.exists(\n"
            "            conversation_id\n"
            "        ):\n"
            "            return False\n"
            "\n"
            "        self._delete_checkpoint_thread(\n"
            "            conversation_id\n"
            "        )\n"
            "        return self._conversations.delete(\n"
            "            conversation_id\n"
            "        )\n"
        ),
        already_present=(
            "if not self._conversations.exists("
        ),
    )

    replace_once(
        path,
        (
            "                    user_message="
            "normalised_user_content,\n"
            "                    context="
            "current_context,\n"
            "                )\n"
        ),
        (
            "                    user_message="
            "normalised_user_content,\n"
            "                    context="
            "current_context,\n"
            "                    thread_id="
            "conversation_id,\n"
            "                )\n"
        ),
        already_present=(
            "thread_id=conversation_id"
        ),
    )

    content = path.read_text(
        encoding="utf-8"
    )

    if "def _delete_checkpoint_thread(" not in content:
        marker = (
            "    @staticmethod\n"
            "    def _recover_tool_result(\n"
        )
        helper = (
            "    def _delete_checkpoint_thread(\n"
            "        self,\n"
            "        conversation_id: UUID,\n"
            "    ) -> None:\n"
            "        if self._checkpoints is None:\n"
            "            return\n"
            "\n"
            "        self._checkpoints.delete_thread(\n"
            "            str(conversation_id)\n"
            "        )\n"
            "\n"
        )

        if content.count(marker) != 1:
            raise RuntimeError(
                "Could not locate checkpoint "
                "helper insertion point."
            )

        path.write_text(
            content.replace(
                marker,
                helper + marker,
                1,
            ),
            encoding="utf-8",
        )
        print(
            "Added checkpoint deletion helper: "
            f"{path}"
        )


def patch_requirements() -> None:
    path = ROOT / "requirements.txt"
    content = path.read_text(
        encoding="utf-8"
    )

    dependency = (
        "langgraph-checkpoint-postgres"
    )

    if dependency in content:
        print(
            "Already present: "
            f"{dependency}"
        )
        return

    separator = (
        ""
        if content.endswith("\n")
        else "\n"
    )

    path.write_text(
        content
        + separator
        + dependency
        + "\n",
        encoding="utf-8",
    )
    print(f"Added dependency: {dependency}")


def main() -> None:
    patch_conversation_service()
    patch_requirements()
    print("MS10.6 patch complete.")


if __name__ == "__main__":
    main()
