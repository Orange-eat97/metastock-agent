from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


SYSTEM_TEST_CREATION_SCHEMA_VERSION = "1.0"
_EXPLORER_COLUMN_REFERENCE_RE = re.compile(r"\bCol[A-Z]\b", re.IGNORECASE)


@dataclass(frozen=True)
class SystemTestGeneralSettings:
    """General-tab settings that are currently covered by inspected UIA IDs."""

    order_bias: str = "long"
    portfolio_bias: str = "single"
    position_limit_enabled: bool = True
    max_positions: int = 1

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any] | None,
    ) -> "SystemTestGeneralSettings":
        raw = dict(payload or {})
        position_limit = raw.get("position_limit") or {}
        if not isinstance(position_limit, Mapping):
            raise TypeError("general.position_limit must be an object.")

        return cls(
            order_bias=str(raw.get("order_bias") or "long"),
            portfolio_bias=str(
                raw.get("portfolio_bias") or "single"
            ),
            position_limit_enabled=bool(
                position_limit.get("enabled", True)
            ),
            max_positions=int(
                position_limit.get("max_positions", 1)
            ),
        )


@dataclass(frozen=True)
class SystemTestOrderDefinition:
    """One System Editor order tab."""

    enabled: bool
    signal_formula: str = ""

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any] | None,
        *,
        default_enabled: bool,
    ) -> "SystemTestOrderDefinition":
        raw = dict(payload or {})
        return cls(
            enabled=bool(raw.get("enabled", default_enabled)),
            signal_formula=str(raw.get("signal_formula") or ""),
        )


@dataclass(frozen=True)
class SystemTestOrders:
    buy: SystemTestOrderDefinition
    sell: SystemTestOrderDefinition
    sell_short: SystemTestOrderDefinition
    buy_to_cover: SystemTestOrderDefinition

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any] | None,
    ) -> "SystemTestOrders":
        raw = dict(payload or {})
        return cls(
            buy=SystemTestOrderDefinition.from_dict(
                _mapping_or_none(raw.get("buy")),
                default_enabled=True,
            ),
            sell=SystemTestOrderDefinition.from_dict(
                _mapping_or_none(raw.get("sell")),
                default_enabled=True,
            ),
            sell_short=SystemTestOrderDefinition.from_dict(
                _mapping_or_none(raw.get("sell_short")),
                default_enabled=False,
            ),
            buy_to_cover=SystemTestOrderDefinition.from_dict(
                _mapping_or_none(raw.get("buy_to_cover")),
                default_enabled=False,
            ),
        )


@dataclass(frozen=True)
class SystemTestCreationRequest:
    """
    Structured RAGLLM -> MetaStock creation contract.

    The current inspection-grounded UIA creator supports:
    - General tab name/notes/long bias/portfolio/position limit.
    - Buy Order and Sell Order signal formula bodies.

    Short-order tabs, Stops, and Optimizations must remain disabled until
    those controls have been inspected.
    """

    schema_version: str
    name: str
    description: str
    general: SystemTestGeneralSettings
    orders: SystemTestOrders
    system_test_id: str | None = None
    source_explorer_id: str | None = None
    stops_enabled: bool = False
    optimizations_enabled: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "SystemTestCreationRequest":
        if not isinstance(payload, Mapping):
            raise TypeError("System-test creation payload must be an object.")

        raw = dict(payload)
        stops = raw.get("stops") or {}
        optimizations = raw.get("optimizations") or {}

        if not isinstance(stops, Mapping):
            raise TypeError("stops must be an object.")
        if not isinstance(optimizations, Mapping):
            raise TypeError("optimizations must be an object.")

        request = cls(
            schema_version=str(
                raw.get("schema_version")
                or SYSTEM_TEST_CREATION_SCHEMA_VERSION
            ),
            system_test_id=_optional_text(raw.get("system_test_id")),
            source_explorer_id=_optional_text(
                raw.get("source_explorer_id")
            ),
            name=str(raw.get("name") or ""),
            description=str(
                raw.get("description")
                or raw.get("notes")
                or ""
            ),
            general=SystemTestGeneralSettings.from_dict(
                _mapping_or_none(raw.get("general"))
            ),
            orders=SystemTestOrders.from_dict(
                _mapping_or_none(raw.get("orders"))
            ),
            stops_enabled=bool(stops.get("enabled", False)),
            optimizations_enabled=bool(
                optimizations.get("enabled", False)
            ),
            metadata=dict(raw.get("metadata") or {}),
        )
        return request.normalized()

    def normalized(self) -> "SystemTestCreationRequest":
        schema_version = str(self.schema_version or "").strip()
        name = str(self.name or "").strip()
        description = str(self.description or "")

        if schema_version != SYSTEM_TEST_CREATION_SCHEMA_VERSION:
            raise ValueError(
                "Unsupported system-test creation schema version: "
                f"{schema_version!r}. Expected "
                f"{SYSTEM_TEST_CREATION_SCHEMA_VERSION!r}."
            )
        if not name:
            raise ValueError("name is required.")

        order_bias = str(self.general.order_bias or "").strip().lower()
        portfolio_bias = str(
            self.general.portfolio_bias or ""
        ).strip().lower()

        if order_bias != "long":
            raise ValueError(
                "general.order_bias must be 'long' for the current "
                "inspection-grounded creator. Sell Short Order and Buy to "
                "Cover Order have not been inspected."
            )
        if portfolio_bias not in {"single", "multiple"}:
            raise ValueError(
                "general.portfolio_bias must be 'single' or 'multiple'."
            )
        if self.general.max_positions <= 0:
            raise ValueError(
                "general.position_limit.max_positions must be positive."
            )

        if self.stops_enabled:
            raise ValueError(
                "stops.enabled=true is not supported by the current UIA "
                "creator because the Stops tab has not been inspected."
            )
        if self.optimizations_enabled:
            raise ValueError(
                "optimizations.enabled=true is not supported by the current "
                "UIA creator because the Optimizations tab has not been "
                "inspected."
            )

        normalized_orders = SystemTestOrders(
            buy=_normalize_order(self.orders.buy, "orders.buy"),
            sell=_normalize_order(self.orders.sell, "orders.sell"),
            sell_short=_normalize_order(
                self.orders.sell_short,
                "orders.sell_short",
            ),
            buy_to_cover=_normalize_order(
                self.orders.buy_to_cover,
                "orders.buy_to_cover",
            ),
        )

        _require_enabled_formula(
            normalized_orders.buy,
            "orders.buy",
        )
        _require_enabled_formula(
            normalized_orders.sell,
            "orders.sell",
        )

        if normalized_orders.sell_short.enabled:
            raise ValueError(
                "orders.sell_short.enabled must be false because the Sell "
                "Short Order tab has not been inspected."
            )
        if normalized_orders.buy_to_cover.enabled:
            raise ValueError(
                "orders.buy_to_cover.enabled must be false because the Buy "
                "to Cover Order tab has not been inspected."
            )

        return SystemTestCreationRequest(
            schema_version=schema_version,
            system_test_id=_optional_text(self.system_test_id),
            source_explorer_id=_optional_text(self.source_explorer_id),
            name=name,
            description=description,
            general=SystemTestGeneralSettings(
                order_bias=order_bias,
                portfolio_bias=portfolio_bias,
                position_limit_enabled=bool(
                    self.general.position_limit_enabled
                ),
                max_positions=int(self.general.max_positions),
            ),
            orders=normalized_orders,
            stops_enabled=False,
            optimizations_enabled=False,
            metadata=dict(self.metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _mapping_or_none(value: Any) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError("Expected an object.")
    return value


def _optional_text(value: Any) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned or None


def _normalize_order(
    order: SystemTestOrderDefinition,
    field_name: str,
) -> SystemTestOrderDefinition:
    formula = str(order.signal_formula or "").strip()
    if _EXPLORER_COLUMN_REFERENCE_RE.search(formula):
        raise ValueError(
            f"{field_name}.signal_formula contains an Explorer-only ColX "
            "reference. RAGLLM must expand ColA/ColB/etc. into their "
            "underlying formulas before creating a System Test."
        )

    return SystemTestOrderDefinition(
        enabled=bool(order.enabled),
        signal_formula=formula,
    )


def _require_enabled_formula(
    order: SystemTestOrderDefinition,
    field_name: str,
) -> None:
    if not order.enabled:
        raise ValueError(f"{field_name}.enabled must be true.")
    if not order.signal_formula:
        raise ValueError(f"{field_name}.signal_formula is required.")
