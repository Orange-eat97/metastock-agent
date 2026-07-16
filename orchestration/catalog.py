from __future__ import annotations

from typing import Any, Protocol

from orchestration.decisions import (
    ToolManifestItem,
)


class ToolCatalogProtocol(Protocol):
    def list_tools(self) -> list[Any]:
        ...


def build_tool_manifest(
    registry: ToolCatalogProtocol,
) -> list[ToolManifestItem]:
    """
    Convert existing ToolDefinition objects into planner-safe DTOs.

    The ToolRegistry remains the source of truth. The planner receives only
    names, descriptions, enabled state, and JSON input schemas.
    """
    manifest: list[ToolManifestItem] = []

    for definition in registry.list_tools():
        schema_method = getattr(
            definition,
            "input_json_schema",
            None,
        )

        if not callable(schema_method):
            raise TypeError(
                "A registered tool definition "
                "does not expose "
                "input_json_schema()."
            )

        manifest.append(
            ToolManifestItem(
                name=str(
                    getattr(
                        definition,
                        "name",
                    )
                ),
                description=str(
                    getattr(
                        definition,
                        "description",
                        "",
                    )
                ),
                input_schema=schema_method(),
                enabled=bool(
                    getattr(
                        definition,
                        "enabled",
                        True,
                    )
                ),
            )
        )

    return sorted(
        manifest,
        key=lambda item: item.name,
    )
