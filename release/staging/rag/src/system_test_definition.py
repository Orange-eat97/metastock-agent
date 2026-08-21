from __future__ import annotations

import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SCHEMA_VERSION = "1.0"
COL_REFERENCE_RE = re.compile(r"\bCol[A-L]\b", re.IGNORECASE)


class PositionLimit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    max_positions: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_limit(self) -> "PositionLimit":
        if self.enabled and self.max_positions < 1:
            raise ValueError("max_positions must be at least 1 when position_limit is enabled.")
        return self


class GeneralSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The current MetaStock creator has stable UIA coverage for this MVP only.
    order_bias: Literal["long"] = "long"
    portfolio_bias: Literal["single"] = "single"
    position_limit: PositionLimit = Field(default_factory=PositionLimit)


class OrderSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    signal_formula: str = ""

    @field_validator("signal_formula")
    @classmethod
    def normalize_formula(cls, value: str) -> str:
        return str(value or "").strip()

    @model_validator(mode="after")
    def validate_enabled_formula(self) -> "OrderSignal":
        if self.enabled and not self.signal_formula:
            raise ValueError("An enabled order requires a non-empty signal_formula.")
        if not self.enabled and self.signal_formula:
            raise ValueError("A disabled order must use an empty signal_formula.")
        if COL_REFERENCE_RE.search(self.signal_formula):
            raise ValueError(
                "System Test formulas cannot contain Explorer column references such as ColA."
            )
        return self


class Orders(BaseModel):
    model_config = ConfigDict(extra="forbid")

    buy: OrderSignal
    sell: OrderSignal
    sell_short: OrderSignal = Field(
        default_factory=lambda: OrderSignal(enabled=False, signal_formula="")
    )
    buy_to_cover: OrderSignal = Field(
        default_factory=lambda: OrderSignal(enabled=False, signal_formula="")
    )

    @model_validator(mode="after")
    def validate_long_only(self) -> "Orders":
        if not self.buy.enabled or not self.sell.enabled:
            raise ValueError("The long-only System Test requires enabled buy and sell orders.")
        if self.sell_short.enabled or self.buy_to_cover.enabled:
            raise ValueError("The current conversion service supports long-only tests.")
        return self


class ToggleSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: Literal[False] = False


class SystemTestMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    generator: Literal["metastock-RAG-LLM"] = "metastock-RAG-LLM"
    conversion_kind: Literal["explorer_to_system_test"] = (
        "explorer_to_system_test"
    )


class SystemTestDefinition(BaseModel):
    """Exact JSON object consumed by MetaStockSystemTestService.create_system_test()."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    system_test_id: UUID
    source_explorer_id: UUID
    name: str = Field(min_length=1, max_length=160)
    description: str = ""
    general: GeneralSettings = Field(default_factory=GeneralSettings)
    orders: Orders
    stops: ToggleSettings = Field(default_factory=ToggleSettings)
    optimizations: ToggleSettings = Field(default_factory=ToggleSettings)
    metadata: SystemTestMetadata = Field(default_factory=SystemTestMetadata)

    @field_validator("name", "description")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return str(value or "").strip()

    @model_validator(mode="after")
    def validate_supported_creator_boundary(self) -> "SystemTestDefinition":
        if self.stops.enabled:
            raise ValueError("Stops must remain disabled until stable UIA coverage exists.")
        if self.optimizations.enabled:
            raise ValueError(
                "Optimizations must remain disabled until stable UIA coverage exists."
            )
        if not self.general.position_limit.enabled:
            raise ValueError("The long-only MVP requires position_limit.enabled=true.")
        if self.general.position_limit.max_positions != 1:
            raise ValueError("The long-only MVP requires max_positions=1.")
        return self
