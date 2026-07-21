# MetaStock Automator — main(5) Coordinate-Only Overlay

This package is the stable `main(5)` Automator with a coordinate calibration
layer added underneath the existing workflows.

Calibration is a geometry adapter only. It does not replace selector logic,
change workflow sequencing, combine service boundaries, or alter result
scraping.

## Preserved boundaries

The agent-facing Explorer sequence remains:

```text
create_explorer
select_explorer
run_selected_explorer
read_results
```

The System Tester create/select/run services from `main(5)` are also retained.

The following remain selector-owned and are not calibrated:

```text
strategy selection
instrument selection
system-test row selection
```

## Calibration points

Explorer mode records:

```text
explore_tab
start_exploration
```

System Tester mode records:

```text
system_test_tab
start_system_test
```

These points are used only when the corresponding console code has already
entered its existing coordinate-fallback branch. UIA remains the first choice.

## Create a profile

Open MetaStock, resize it to the layout that will be automated, then run from
this directory:

```powershell
python .\calibrate_coordinates.py --profile t490-small --mode explore
```

For both consoles:

```powershell
python .\calibrate_coordinates.py --profile t490-small --mode all
```

Activate the profile for the current PowerShell process:

```powershell
$env:METASTOCK_CALIBRATION_PROFILE = "t490-small"
```

Profiles are stored in:

```text
calibration_profiles/<profile-name>.json
```

Use a separate profile for each materially different MetaStock window layout.
If the current window size differs from the profile by more than the safety
tolerance, the mapper stops instead of clicking an unsafe point.

## Start-button fallback safety

The stable `main(5)` opt-in remains in force:

```python
ALLOW_START_FALLBACK_CLICK = False
```

A calibrated start point does not bypass that safety gate. If UIA cannot find
the Start button and you have manually verified the calibrated fallback, enable
the existing flag deliberately.

## Validation

Compile and run unit tests:

```powershell
python -m compileall -q .
python -m unittest discover -s tests -v
```

For the live Explorer calibration test, keep run and read separate:

```powershell
python -c "from automator import ExploreRequest, build_workflow; req=ExploreRequest(strategy_name='#Anchor Full 01', select_all_instruments=True); w=build_workflow(max_execution_wait_sec=300); w.run_until_results_ready(req); print('OK: result window ready')"
```

After the result window settles:

```powershell
python -c "from automator import read_current_results, print_result_inspection; print_result_inspection(read_current_results(close_after_read=False))"
```

Do not use a combined run-and-scrape path as the calibrator acceptance test.
