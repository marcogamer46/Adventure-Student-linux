"""Published finite DEVELOPMENT controls, separate from gameplay parameters."""

PROJECT_LIMITS = dict(import_seconds=5, generation_seconds=5, callback_seconds=2,
    controller_seconds=10, worker_seconds=15, output_bytes=65536, result_bytes=16 * 1024 * 1024,
    input_bytes=16 * 1024 * 1024, temporary_bytes=40 * 1024 * 1024,
    temporary_files=32, source_bytes=4194304, source_files=256)


def resource_policy():
    return dict(policy_id="DEV-PUBLIC-PROJECT-RESOURCES-TASK035", status="DEVELOPMENT",
        classroom_calibration_approved=False, units="seconds and bytes as named",
        scope="cooperative fresh Python workers; no hostile-code sandbox claim",
        limits=dict(PROJECT_LIMITS))
