from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(
    path: Path,
    old: str,
    new: str,
    *,
    already: str | None = None,
) -> None:
    content = path.read_text(encoding="utf-8")

    if already and already in content:
        print(f"Already patched: {path}")
        return

    count = content.count(old)
    if count != 1:
        raise RuntimeError(
            f"Expected one patch target in {path}; found {count}."
        )

    path.write_text(
        content.replace(old, new, 1),
        encoding="utf-8",
    )
    print(f"Patched: {path}")


def patch_tool_contracts() -> None:
    path = ROOT / "tools" / "tool_contracts.py"
    old = '''class ReviseExplorerInput(BaseModel):
    explorer_id: str = Field(
        description="Primary key of the explorer_outputs row to revise."
    )
    revision_instruction: str = Field(
        description="Human instruction for changing the Explorer logic."
    )


class GetExplorerInput(BaseModel):
'''
    new = '''class ReviseExplorerInput(BaseModel):
    explorer_id: str = Field(
        description="Primary key of the explorer_outputs row to revise."
    )
    revision_instruction: str = Field(
        description="Human instruction for changing the Explorer logic."
    )


class ReviseExplorerOutput(BaseModel):
    explorer: ExplorerDTO
    assumptions: list[str] = Field(
        default_factory=list
    )
    retrieved_refs: list[
        dict[str, Any]
    ] = Field(default_factory=list)
    revised_from_explorer_id: str
    revision_instruction: str


class GetExplorerInput(BaseModel):
'''
    replace_once(
        path,
        old,
        new,
        already="class ReviseExplorerOutput",
    )


def patch_explorer_tools() -> None:
    path = ROOT / "tools" / "explorer_tools.py"

    replace_once(
        path,
        '''    ReviseExplorerInput,
    RunExplorerInput,
''',
        '''    ReviseExplorerInput,
    ReviseExplorerOutput,
    RunExplorerInput,
''',
        already="ReviseExplorerOutput,",
    )

    old = '''    def revise_explorer(self, payload: ReviseExplorerInput) -> ToolResult:
        return ToolResult(
            tool_name="revise_explorer",
            ok=False,
            status=ToolStatus.NOT_IMPLEMENTED,
            message="Explorer revision is not implemented yet.",
            error=ToolError(
                code="TOOL_NOT_IMPLEMENTED",
                message=(
                    "revise_explorer is reserved for future MITL correction. "
                    "Use repair_explorer only for syntax/contract repair."
                ),
            ),
            display=ToolDisplay(
                title="Revision Not Implemented",
                markdown=(
                    "Explorer revision is not implemented yet. "
                    "This will later support human instructions such as "
                    "`change RSI threshold to 35` or `use 50-day volume average`."
                ),
                severity="warning",
            ),
        )
'''
    new = '''    def revise_explorer(self, payload: ReviseExplorerInput) -> ToolResult:
        try:
            state = self.review_workflow.revise_for_review(
                explorer_id=payload.explorer_id,
                revision_instruction=(
                    payload.revision_instruction
                ),
            )
            explorer = self._state_to_explorer_dto(state)
            output = ReviseExplorerOutput(
                explorer=explorer,
                assumptions=list(state.assumptions),
                retrieved_refs=[
                    dict(ref)
                    for ref in state.retrieved_refs
                ],
                revised_from_explorer_id=(
                    payload.explorer_id
                ),
                revision_instruction=(
                    payload.revision_instruction
                ),
            )

            return ToolResult(
                tool_name="revise_explorer",
                ok=True,
                status=ToolStatus.SUCCESS,
                message=(
                    "Explorer revision completed and "
                    "saved as a new row."
                ),
                data=output.model_dump(mode="json"),
                display=self._explorer_display(
                    title="Revised Explorer",
                    explorer=explorer,
                ),
            )

        except Exception as exc:
            return self._exception_result(
                tool_name="revise_explorer",
                exc=exc,
            )
'''
    replace_once(
        path,
        old,
        new,
        already="state = self.review_workflow.revise_for_review",
    )


def patch_review_workflow() -> None:
    path = (
        ROOT
        / "agent_workflows"
        / "explorer_review_workflow.py"
    )
    marker = '''    @staticmethod
    def _build_review_state(
'''
    method = '''    def revise_for_review(
        self,
        explorer_id: str,
        revision_instruction: str,
    ) -> ExplorerReviewState:
        result = self.rag_client.revise_explorer(
            explorer_id=explorer_id,
            revision_instruction=revision_instruction,
        )
        explorer_row = (
            self.explorer_repository
            .get_explorer(result.explorer)
        )

        service_log_row = None
        if result.service_log:
            service_log_row = (
                self.explorer_repository
                .get_service_log(result.service_log)
            )

        return self._build_review_state(
            result=result,
            explorer_row=explorer_row,
            service_log_row=service_log_row,
        )

'''
    replace_once(
        path,
        marker,
        method + marker,
        already="def revise_for_review(",
    )


def patch_rag_client() -> None:
    path = ROOT / "services" / "rag_client.py"

    replace_once(
        path,
        '''        from src.rag_service import (
            RagExplorerRepairService,
            RagExplorerService,
        )
''',
        '''        from src.rag_revision_service import (
            RagExplorerRevisionService,
        )
        from src.rag_service import (
            RagExplorerRepairService,
            RagExplorerService,
        )
''',
        already="RagExplorerRevisionService",
    )

    replace_once(
        path,
        '''        self._repair_service = (
            RagExplorerRepairService()
        )
        self._read_service = (
''',
        '''        self._repair_service = (
            RagExplorerRepairService()
        )
        self._revision_service = (
            RagExplorerRevisionService()
        )
        self._read_service = (
''',
        already="self._revision_service",
    )

    marker = '''    def get_explorer(
        self,
        explorer_id: str,
    ) -> dict[str, Any]:
'''
    method = '''    def revise_explorer(
        self,
        explorer_id: str,
        revision_instruction: str,
    ) -> RagGenerateResult:
        response = (
            self._revision_service
            .revise_explorer(
                explorer=explorer_id,
                revision_instruction=(
                    revision_instruction
                ),
            )
        )

        return RagGenerateResult(
            explorer=response.explorer,
            explorer_created_at=(
                response.explorer_created_at
            ),
            service_log=response.service_log,
            service_log_created_at=(
                response.service_log_created_at
            ),
            validation_passed=(
                response.validation.passed
            ),
            validation_errors=[
                str(error)
                for error in response.validation.errors
            ],
            source=response.source,
            assumptions=[
                str(assumption)
                for assumption in response.assumptions
            ],
            retrieved_refs=[
                (
                    ref.model_dump(mode="json")
                    if hasattr(ref, "model_dump")
                    else dict(ref)
                )
                for ref in response.retrieved_refs
            ],
            validation_warnings=[
                str(warning)
                for warning in getattr(
                    response.validation,
                    "warnings",
                    [],
                )
            ],
        )

'''
    replace_once(
        path,
        marker,
        method + marker,
        already="def revise_explorer(\n        self,\n        explorer_id:",
    )


def main() -> None:
    patch_tool_contracts()
    patch_explorer_tools()
    patch_review_workflow()
    patch_rag_client()
    print("Agent revision service wiring applied.")


if __name__ == "__main__":
    main()
