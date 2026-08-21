from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ui_interacter.coordinate_calibration import (
    CalibratedPoint,
    CalibrationProfile,
    CalibrationStore,
    CalibrationWizard,
    CoordinateMapper,
)


class FakeRectangle:
    def __init__(self, left: int, top: int, width: int, height: int):
        self.left = left
        self.top = top
        self.right = left + width
        self.bottom = top + height

    def width(self) -> int:
        return self.right - self.left

    def height(self) -> int:
        return self.bottom - self.top


class FakeWindow:
    handle = 0

    def __init__(self, rect: FakeRectangle):
        self._rect = rect

    def rectangle(self) -> FakeRectangle:
        return self._rect

    def window_text(self) -> str:
        return "Main - MetaStock"


class FakeRecorder:
    def __init__(self, points: list[tuple[int, int]]):
        self._points = iter(points)

    def capture_anchor(self, *, anchor_name: str, instruction: str):
        del anchor_name, instruction
        return next(self._points)


class CoordinateCalibrationTests(unittest.TestCase):
    def make_profile(self) -> CalibrationProfile:
        return CalibrationProfile(
            profile_version="1.0",
            profile_name="test",
            window_title="Main - MetaStock",
            window_width=1000,
            window_height=800,
            dpi=96,
            created_at_epoch=1.0,
            points={
                "explore_tab": CalibratedPoint(
                    name="explore_tab",
                    absolute_x=110,
                    absolute_y=220,
                    window_relative_x=100,
                    window_relative_y=200,
                    normalized_x=0.1,
                    normalized_y=0.25,
                )
            },
        )

    def test_store_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = CalibrationStore(directory)
            profile = self.make_profile()
            path = store.save(profile)

            self.assertEqual(path, Path(directory) / "test.json")
            self.assertEqual(store.load("test"), profile)

    def test_mapper_uses_window_relative_normalized_point(self) -> None:
        profile = self.make_profile()
        mapper = CoordinateMapper(profile, max_size_change_ratio=1.0)
        window = FakeWindow(FakeRectangle(50, 70, 1200, 900))

        self.assertEqual(
            mapper.resolve(main=window, point_name="explore_tab"),
            (170, 295),
        )

    def test_mapper_blocks_large_window_change(self) -> None:
        mapper = CoordinateMapper(self.make_profile())
        window = FakeWindow(FakeRectangle(0, 0, 1400, 800))

        with self.assertRaisesRegex(RuntimeError, "Re-run coordinate calibration"):
            mapper.resolve(main=window, point_name="explore_tab")

    def test_wizard_merges_separate_modes_into_one_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = CalibrationStore(directory)
            window = FakeWindow(FakeRectangle(10, 20, 1000, 800))

            CalibrationWizard(
                store=store,
                recorder=FakeRecorder([(110, 220)]),
            ).run(
                main=window,
                profile_name="laptop",
                anchors=[("explore_tab", "explore")],
            )

            CalibrationWizard(
                store=store,
                recorder=FakeRecorder([(210, 320)]),
            ).run(
                main=window,
                profile_name="laptop",
                anchors=[("system_test_tab", "system test")],
            )

            profile = store.load("laptop")
            self.assertEqual(
                set(profile.points),
                {"explore_tab", "system_test_tab"},
            )


if __name__ == "__main__":
    unittest.main()
