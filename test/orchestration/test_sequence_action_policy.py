from chat.models import ChatContext
from orchestration.action_policy import ConversationActionPolicy
from orchestration.conversation_actions import (
    SEQUENCE_ACTION_NAME,
    ConversationActionCall,
    ConversationActionDefinition,
    ConversationModelRequest,
    ConversationModelResponse,
)


class _NameResolver:
    def resolve_explorer_id(self, explorer_name: str) -> str:
        mapping = {
            "Explorer A": "11111111-1111-1111-1111-111111111111",
            "Explorer B": "22222222-2222-2222-2222-222222222222",
        }
        return mapping[explorer_name]


class _Registry:
    pass


def test_policy_resolves_each_sequence_stage_independently():
    action = ConversationActionDefinition(
        name=SEQUENCE_ACTION_NAME,
        description="Run multiple Explorers sequentially.",
        kind="command",
        parameters={"type": "object"},
    )
    request = ConversationModelRequest(
        user_message=(
            "Run Explorer A on Singapore Exchange, then Explorer B "
            "on NASDAQ and capture both results."
        ),
        context=ChatContext(),
        actions=[action],
    )
    response = ConversationModelResponse(
        action_call=ConversationActionCall(
            name=SEQUENCE_ACTION_NAME,
            arguments={
                "stages": [
                    {
                        "explorer_reference": "Explorer A",
                        "instruments": "Singapore Exchange",
                        "create_in_metastock": True,
                    },
                    {
                        "explorer_reference": "Explorer B",
                        "instruments": "NASDAQ",
                        "create_in_metastock": False,
                    },
                ],
                "stop_on_failure": True,
            },
        )
    )

    resolution = ConversationActionPolicy(
        registry=_Registry(),
        explorer_name_resolver=_NameResolver(),
    ).resolve(request=request, response=response)

    assert resolution.outcome == "sequence"
    sequence = resolution.arguments["sequence"]
    assert sequence["stages"][0]["explorer_id"].startswith("1111")
    assert sequence["stages"][0]["instruments"] == "Singapore Exchange"
    assert sequence["stages"][1]["explorer_id"].startswith("2222")
    assert sequence["stages"][1]["instruments"] == "NASDAQ"
