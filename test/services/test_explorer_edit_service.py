from __future__ import annotations

import unittest

from services.explorer_edit_service import (
    ExplorerEditService,
    ExplorerEditValidationError,
)


class FakeExplorerRepository:
    def __init__(self) -> None:
        self.last_call: dict | None = None

    def get_explorer(self, explorer_id: str) -> dict:
        return {"id": explorer_id}

    def get_explorers_by_ids(self, explorer_ids: list[str]) -> list[dict]:
        return [{"id": explorer_id} for explorer_id in explorer_ids]

    def update_explorer_full_json(
        self,
        *,
        explorer_id: str,
        expected_version: int,
        patch: dict,
    ) -> dict:
        self.last_call = {
            "explorer_id": explorer_id,
            "expected_version": expected_version,
            "patch": patch,
        }
        return {
            "id": explorer_id,
            "manual_edit_version": expected_version + 1,
            **patch,
        }


class RepositoryValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


class RejectingExplorerRepository(FakeExplorerRepository):
    def update_explorer_full_json(
        self,
        *,
        explorer_id: str,
        expected_version: int,
        patch: dict,
    ) -> dict:
        self.last_call = {
            "explorer_id": explorer_id,
            "expected_version": expected_version,
            "patch": patch,
        }
        raise RepositoryValidationError(
            [
                "col C: Function may be unsupported or missing "
                "from whitelist: InvalidFunction"
            ]
        )


class ExplorerEditServiceTests(unittest.TestCase):
    def test_saves_only_explicit_full_json_fields(self) -> None:
        repository = FakeExplorerRepository()
        service = ExplorerEditService(repository)  # type: ignore[arg-type]

        result = service.save_edits(
            explorer_id="explorer-1",
            expected_version=4,
            name="AI_Breakout",
            description="Manual edit",
            columns=[
                {"col_letter": "a", "col_code": "C"},
                {"col_letter": "B", "col_code": "V"},
            ],
            filter_formula="C > Ref(HHV(H,20),-1)",
            assumptions=[" Completed bars only ", ""],
        )

        self.assertEqual(result["manual_edit_version"], 5)
        self.assertEqual(
            repository.last_call,
            {
                "explorer_id": "explorer-1",
                "expected_version": 4,
                "patch": {
                    "explorer_name": "AI_Breakout",
                    "explorer_description": "Manual edit",
                    "explorer_code_body": "C > Ref(HHV(H,20),-1)",
                    "col_definitions": [
                        {"col_letter": "A", "col_code": "C"},
                        {"col_letter": "B", "col_code": "V"},
                    ],
                    "assumptions": ["Completed bars only"],
                },
            },
        )

    def test_maps_deterministic_validator_errors_without_ai_repair(self) -> None:
        repository = RejectingExplorerRepository()
        service = ExplorerEditService(repository)  # type: ignore[arg-type]

        with self.assertRaises(ExplorerEditValidationError) as context:
            service.save_edits(
                explorer_id="explorer-1",
                expected_version=0,
                name="AI_Breakout",
                description="",
                columns=[
                    {"col_letter": "A", "col_code": "C"},
                    {"col_letter": "B", "col_code": "V"},
                    {
                        "col_letter": "C",
                        "col_code": "InvalidFunction(C,20)",
                    },
                ],
                filter_formula="C > 0",
                assumptions=[],
            )

        self.assertIn("col C", context.exception.errors[0])
        self.assertIn("InvalidFunction", context.exception.errors[0])

    def test_rejects_non_sequential_column_letters(self) -> None:
        repository = FakeExplorerRepository()
        service = ExplorerEditService(repository)  # type: ignore[arg-type]

        with self.assertRaises(ExplorerEditValidationError) as context:
            service.save_edits(
                explorer_id="explorer-1",
                expected_version=0,
                name="AI_Breakout",
                description="",
                columns=[
                    {"col_letter": "A", "col_code": "C"},
                    {"col_letter": "C", "col_code": "V"},
                ],
                filter_formula="C > 0",
                assumptions=[],
            )

        self.assertIn("must be B", context.exception.errors[0])
        self.assertIsNone(repository.last_call)

    def test_rejects_empty_required_formula_before_repository_write(self) -> None:
        repository = FakeExplorerRepository()
        service = ExplorerEditService(repository)  # type: ignore[arg-type]

        with self.assertRaisesRegex(ValueError, "filter_formula is required"):
            service.save_edits(
                explorer_id="explorer-1",
                expected_version=0,
                name="AI_Breakout",
                description="",
                columns=[{"col_letter": "A", "col_code": "C"}],
                filter_formula="",
                assumptions=[],
            )

        self.assertIsNone(repository.last_call)


if __name__ == "__main__":
    unittest.main()
