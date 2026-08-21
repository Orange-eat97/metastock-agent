from orchestration.sequence_workflows import (
    ExplorerSequenceCatalog,
    ResolvedExplorerSequenceRequest,
    ResolvedExplorerSequenceStage,
)


def test_sequence_catalog_preserves_stage_instruments_and_creation():
    request = ResolvedExplorerSequenceRequest(
        stages=[
            ResolvedExplorerSequenceStage(
                stage_index=0,
                explorer_id="11111111-1111-1111-1111-111111111111",
                explorer_reference="Explorer A",
                instruments="Singapore Exchange",
                create_in_metastock=True,
            ),
            ResolvedExplorerSequenceStage(
                stage_index=1,
                explorer_id="22222222-2222-2222-2222-222222222222",
                explorer_reference="Explorer B",
                instruments="NASDAQ,NYSE",
                create_in_metastock=False,
            ),
        ]
    )

    plan = ExplorerSequenceCatalog().prepare(request)

    assert len(plan.stages) == 2
    assert [
        step.tool_name
        for step in plan.stages[0].workflow_plan.steps
    ] == [
        "create_explorer_in_metastock",
        "select_explorer_in_metastock",
        "run_selected_explorer_in_metastock",
        "read_metastock_explorer_results",
    ]
    assert [
        step.tool_name
        for step in plan.stages[1].workflow_plan.steps
    ] == [
        "select_explorer_in_metastock",
        "run_selected_explorer_in_metastock",
        "read_metastock_explorer_results",
    ]
    assert (
        plan.stages[0].workflow_plan.workflow_arguments["instruments"]
        == "Singapore Exchange"
    )
    assert (
        plan.stages[1].workflow_plan.workflow_arguments["instruments"]
        == "NASDAQ,NYSE"
    )
