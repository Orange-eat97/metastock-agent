from __future__ import annotations

import ctypes
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional, Protocol


VK_R = 0x52
VK_ESCAPE = 0x1B
VK_LBUTTON = 0x01

CALIBRATION_DIRECTORY_ENV = "METASTOCK_CALIBRATION_DIR"
APP_DATA_DIRECTORY_ENV = "METASTOCK_APP_DATA_DIR"
ACTIVE_PROFILE_FILENAME = "active_profile.txt"


class WindowRectangle(Protocol):
    left: int
    top: int
    right: int
    bottom: int

    def width(self) -> int: ...

    def height(self) -> int: ...


class WindowWrapper(Protocol):
    handle: int

    def rectangle(self) -> WindowRectangle: ...

    def window_text(self) -> str: ...


class POINT(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long),
    ]


def _get_user32():
    """Return user32 on Windows and fail clearly elsewhere."""
    if os.name != "nt" or not hasattr(ctypes, "windll"):
        raise RuntimeError(
            "Interactive coordinate calibration is available only on Windows."
        )

    return ctypes.windll.user32


def _log(message: str) -> None:
    print(f"[MetaStockBot] {message}")


@dataclass(frozen=True)
class CalibratedPoint:
    """A point stored relative to the MetaStock window."""

    name: str
    absolute_x: int
    absolute_y: int
    window_relative_x: int
    window_relative_y: int
    normalized_x: float
    normalized_y: float


@dataclass(frozen=True)
class CalibrationProfile:
    profile_version: str
    profile_name: str
    window_title: str
    window_width: int
    window_height: int
    dpi: Optional[int]
    created_at_epoch: float
    points: dict[str, CalibratedPoint]

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["points"] = {
            name: asdict(point)
            for name, point in self.points.items()
        }
        return payload

    @classmethod
    def from_dict(cls, payload: dict) -> "CalibrationProfile":
        points = {
            str(name): CalibratedPoint(**point_payload)
            for name, point_payload in (payload.get("points") or {}).items()
        }

        return cls(
            profile_version=str(payload.get("profile_version") or "1.0"),
            profile_name=str(payload.get("profile_name") or "default"),
            window_title=str(payload.get("window_title") or ""),
            window_width=int(payload.get("window_width") or 0),
            window_height=int(payload.get("window_height") or 0),
            dpi=(
                int(payload["dpi"])
                if payload.get("dpi") is not None
                else None
            ),
            created_at_epoch=float(payload.get("created_at_epoch") or 0.0),
            points=points,
        )


def _safe_profile_name(profile_name: str) -> str:
    safe_name = "".join(
        char if char.isalnum() or char in {"-", "_"} else "_"
        for char in profile_name.strip()
    )
    return safe_name or "default"


def resolve_calibration_directory() -> Path:
    """
    Resolve the writable calibration-profile directory.

    The packaged Agent sets METASTOCK_CALIBRATION_DIR to:
        %LOCALAPPDATA%\\MetaStockAgent\\calibration_profiles

    Standalone Automator development keeps the historical package-local
    directory unless METASTOCK_APP_DATA_DIR or METASTOCK_CALIBRATION_DIR
    is supplied explicitly.
    """
    explicit_directory = (
        os.getenv(CALIBRATION_DIRECTORY_ENV)
        or ""
    ).strip()

    if explicit_directory:
        return Path(explicit_directory).expanduser()

    app_data_directory = (
        os.getenv(APP_DATA_DIRECTORY_ENV)
        or ""
    ).strip()

    if app_data_directory:
        return (
            Path(app_data_directory).expanduser()
            / "calibration_profiles"
        )

    return (
        Path(__file__).resolve().parents[1]
        / "calibration_profiles"
    )


class CalibrationStore:
    def __init__(self, directory: str | Path | None = None) -> None:
        self.directory = Path(
            directory
            if directory is not None
            else resolve_calibration_directory()
        )

    @property
    def active_profile_path(self) -> Path:
        return self.directory / ACTIVE_PROFILE_FILENAME

    def profile_path(self, profile_name: str) -> Path:
        return (
            self.directory
            / f"{_safe_profile_name(profile_name)}.json"
        )

    def save(self, profile: CalibrationProfile) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.profile_path(profile.profile_name)
        path.write_text(
            json.dumps(profile.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def load(self, profile_name: str) -> CalibrationProfile:
        path = self.profile_path(profile_name)

        if not path.exists():
            raise FileNotFoundError(
                f"Calibration profile does not exist: {path}"
            )

        payload = json.loads(path.read_text(encoding="utf-8"))
        return CalibrationProfile.from_dict(payload)

    def set_active_profile(self, profile_name: str) -> Path:
        safe_name = _safe_profile_name(profile_name)
        profile_path = self.profile_path(safe_name)

        if not profile_path.is_file():
            raise FileNotFoundError(
                "Cannot activate a calibration profile that does not "
                f"exist: {profile_path}"
            )

        self.directory.mkdir(parents=True, exist_ok=True)
        self.active_profile_path.write_text(
            safe_name + "\n",
            encoding="utf-8",
        )
        return self.active_profile_path

    def get_active_profile_name(self) -> str | None:
        marker = self.active_profile_path

        if not marker.is_file():
            default_path = self.profile_path("default")
            return "default" if default_path.is_file() else None

        profile_name = _safe_profile_name(
            marker.read_text(encoding="utf-8").strip()
        )

        if not self.profile_path(profile_name).is_file():
            return None

        return profile_name


class InteractiveCoordinateRecorder:
    """
    Windows-only interactive coordinate recorder.

    Per anchor:
      1. press R once to arm;
      2. click the intended point;
      3. press R again to accept and finish that anchor.

    The most recent click before the second R is used. ESC cancels.
    """

    def __init__(self, *, poll_interval: float = 0.02) -> None:
        self.poll_interval = poll_interval
        self._user32 = _get_user32()

    def capture_anchor(
        self,
        *,
        anchor_name: str,
        instruction: str,
    ) -> tuple[int, int]:
        print()
        print("=" * 68)
        print(f"CALIBRATION: {anchor_name}")
        print(instruction)
        print()
        print("1. Press R once to arm coordinate recording.")
        print("2. Click the requested point.")
        print("3. Press R again to accept this calibration point.")
        print("Press ESC at any time to cancel.")
        print("=" * 68)

        self._wait_for_key_press(VK_R)

        print(
            f"[Calibration] Recording armed for {anchor_name!r}. "
            "Click the target point, then press R."
        )

        latest_click: Optional[tuple[int, int]] = None
        r_was_down = self._is_key_down(VK_R)
        mouse_was_down = self._is_key_down(VK_LBUTTON)

        while True:
            if self._is_key_down(VK_ESCAPE):
                self._wait_for_key_release(VK_ESCAPE)
                raise KeyboardInterrupt("Calibration cancelled by user.")

            r_is_down = self._is_key_down(VK_R)
            mouse_is_down = self._is_key_down(VK_LBUTTON)

            if mouse_is_down and not mouse_was_down:
                latest_click = self._cursor_position()
                print(
                    "[Calibration] Click captured at "
                    f"{latest_click}. Click again to replace it, "
                    "or press R to accept."
                )

            if r_is_down and not r_was_down:
                if latest_click is None:
                    print(
                        "[Calibration] No click has been captured yet. "
                        "Click the target first."
                    )
                else:
                    self._wait_for_key_release(VK_R)
                    print(
                        "[Calibration] Accepted "
                        f"{anchor_name!r} at {latest_click}."
                    )
                    return latest_click

            r_was_down = r_is_down
            mouse_was_down = mouse_is_down
            time.sleep(self.poll_interval)

    def _wait_for_key_press(self, virtual_key: int) -> None:
        previous = self._is_key_down(virtual_key)

        while True:
            if self._is_key_down(VK_ESCAPE):
                self._wait_for_key_release(VK_ESCAPE)
                raise KeyboardInterrupt("Calibration cancelled by user.")

            current = self._is_key_down(virtual_key)

            if current and not previous:
                self._wait_for_key_release(virtual_key)
                return

            previous = current
            time.sleep(self.poll_interval)

    def _wait_for_key_release(self, virtual_key: int) -> None:
        while self._is_key_down(virtual_key):
            time.sleep(self.poll_interval)

    def _is_key_down(self, virtual_key: int) -> bool:
        return bool(self._user32.GetAsyncKeyState(virtual_key) & 0x8000)

    def _cursor_position(self) -> tuple[int, int]:
        point = POINT()

        if not self._user32.GetCursorPos(ctypes.byref(point)):
            raise RuntimeError("Windows GetCursorPos failed.")

        return int(point.x), int(point.y)


class CalibrationWizard:
    def __init__(
        self,
        *,
        store: CalibrationStore | None = None,
        recorder: InteractiveCoordinateRecorder | None = None,
    ) -> None:
        self.store = store or CalibrationStore()
        self.recorder = recorder or InteractiveCoordinateRecorder()

    def run(
        self,
        *,
        main: WindowWrapper,
        profile_name: str,
        anchors: Iterable[tuple[str, str]],
    ) -> CalibrationProfile:
        rect = main.rectangle()

        if rect.width() <= 0 or rect.height() <= 0:
            raise RuntimeError("MetaStock window has invalid bounds.")

        points: dict[str, CalibratedPoint] = {}

        for anchor_name, instruction in anchors:
            x, y = self.recorder.capture_anchor(
                anchor_name=anchor_name,
                instruction=instruction,
            )

            if not (
                rect.left <= x <= rect.right
                and rect.top <= y <= rect.bottom
            ):
                raise RuntimeError(
                    f"Captured point {anchor_name!r} ({x}, {y}) "
                    "is outside the MetaStock window."
                )

            relative_x = x - rect.left
            relative_y = y - rect.top

            points[anchor_name] = CalibratedPoint(
                name=anchor_name,
                absolute_x=x,
                absolute_y=y,
                window_relative_x=relative_x,
                window_relative_y=relative_y,
                normalized_x=relative_x / rect.width(),
                normalized_y=relative_y / rect.height(),
            )

        # Allow Explorer and System Tester anchors to be recorded separately.
        try:
            existing_profile = self.store.load(profile_name)
            merged_points = dict(existing_profile.points)
            merged_points.update(points)
            points = merged_points
        except FileNotFoundError:
            pass

        profile = CalibrationProfile(
            profile_version="1.0",
            profile_name=profile_name,
            window_title=main.window_text(),
            window_width=rect.width(),
            window_height=rect.height(),
            dpi=self._read_window_dpi(main),
            created_at_epoch=time.time(),
            points=points,
        )

        path = self.store.save(profile)
        _log(f"Calibration profile saved: {path}")
        return profile

    @staticmethod
    def _read_window_dpi(main: WindowWrapper) -> Optional[int]:
        try:
            user32 = _get_user32()
            return int(user32.GetDpiForWindow(int(main.handle)))
        except Exception:
            return None


class CoordinateMapper:
    """Resolve named calibration points against the current MetaStock window."""

    def __init__(
        self,
        profile: CalibrationProfile,
        *,
        max_size_change_ratio: float = 0.08,
    ) -> None:
        self.profile = profile
        self.max_size_change_ratio = max_size_change_ratio

    def resolve(
        self,
        *,
        main: WindowWrapper,
        point_name: str,
        require_matching_window: bool = True,
    ) -> tuple[int, int]:
        point = self.profile.points.get(point_name)

        if point is None:
            raise KeyError(f"Calibration point is missing: {point_name!r}")

        rect = main.rectangle()

        if require_matching_window:
            self.validate_window(main)

        x = rect.left + round(point.normalized_x * rect.width())
        y = rect.top + round(point.normalized_y * rect.height())
        return int(x), int(y)

    def validate_window(self, main: WindowWrapper) -> None:
        rect = main.rectangle()

        width_ratio = self._difference_ratio(
            rect.width(),
            self.profile.window_width,
        )
        height_ratio = self._difference_ratio(
            rect.height(),
            self.profile.window_height,
        )

        if (
            width_ratio > self.max_size_change_ratio
            or height_ratio > self.max_size_change_ratio
        ):
            raise RuntimeError(
                "MetaStock window size changed beyond the calibrated "
                "tolerance. Re-run coordinate calibration. "
                f"Calibrated={self.profile.window_width}x"
                f"{self.profile.window_height}, "
                f"Current={rect.width()}x{rect.height()}."
            )

    @staticmethod
    def _difference_ratio(current: int, reference: int) -> float:
        if reference <= 0:
            return 1.0

        return abs(current - reference) / reference
