# Issue Resolution Report

Issues found: 4
AI-assisted resolutions: disabled

Analysis goal: Find why C drives are filling up and recommend remediation.

## `RecoveredGB` contains negative values

- ID: `examples_data_disk_maintenance_sample_csv_recoveredgb_negative_values`
- Severity: medium
- File: examples\data\disk_maintenance_sample.csv

### Evidence

- Minimum value is -0.35.

### Local Recommendation

Verify whether negative values are valid for this measure or correct the source data.

### Action Plan

1. Filter `RecoveredGB` for values below 0 and identify the affected records.
2. Compare before/after source measurements for those records.
3. Fix collection math, timing drift, or source values if negative recovery is invalid.
4. Rerun the operation for affected records and confirm the minimum value is 0 or higher.

## `UserTemp_RecoveredGB` contains negative values

- ID: `examples_data_disk_maintenance_sample_csv_usertemp_recoveredgb_negative_values`
- Severity: medium
- File: examples\data\disk_maintenance_sample.csv

### Evidence

- Minimum value is -0.45.

### Local Recommendation

Verify whether negative values are valid for this measure or correct the source data.

### Action Plan

1. Filter `UserTemp_RecoveredGB` for values below 0 and identify the affected records.
2. Compare before/after source measurements for those records.
3. Fix collection math, timing drift, or source values if negative recovery is invalid.
4. Rerun the operation for affected records and confirm the minimum value is 0 or higher.

## `WindowsErrorReporting_RecoveredGB` contains negative values

- ID: `examples_data_disk_maintenance_sample_csv_windowserrorreporting_recoveredgb_negative_values`
- Severity: medium
- File: examples\data\disk_maintenance_sample.csv

### Evidence

- Minimum value is -0.56.

### Local Recommendation

Verify whether negative values are valid for this measure or correct the source data.

### Action Plan

1. Filter `WindowsErrorReporting_RecoveredGB` for values below 0 and identify the affected records.
2. Compare before/after source measurements for those records.
3. Fix collection math, timing drift, or source values if negative recovery is invalid.
4. Rerun the operation for affected records and confirm the minimum value is 0 or higher.

## `DISM_Status` has non-success status values

- ID: `examples_data_disk_maintenance_sample_csv_dism_status_non_success_status_values`
- Severity: medium
- File: examples\data\disk_maintenance_sample.csv

### Evidence

- Non-success values: ExitCode_5 (1), ExitCode_-2146498554 (1), ExitCode_14098 (1).

### Local Recommendation

Review the affected records, group them by failure reason, and rerun the operation after correcting access, service, or script errors.

### Action Plan

1. Filter `DISM_Status` to the non-success values listed in the evidence.
2. Group affected records by status code and failure message if available.
3. Resolve the highest-count failure group first.
4. Rerun the source operation for affected records.
5. Rerun the analyzer and confirm the non-success count is reduced or cleared.
