import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lambda_s3_trigger as handler  # noqa: E402


def s3_event(*keys):
    return {"Records": [{"s3": {"bucket": {"name": "raw"}, "object": {"key": k}}} for k in keys]}


def test_one_run_per_object_with_decoded_key():
    glue = MagicMock()
    glue.start_job_run.side_effect = [{"JobRunId": "jr_1"}, {"JobRunId": "jr_2"}]
    with patch.object(handler, "glue_client", return_value=glue):
        result = handler.lambda_handler(s3_event("claims/2026+01/file%3D1.parquet", "claims/b.parquet"), None)
    first = glue.start_job_run.call_args_list[0].kwargs
    assert first["Arguments"] == {"--source_path": "s3://raw/claims/2026 01/file=1.parquet"}
    assert '"jr_1", "jr_2"' in result["body"]


def test_folder_placeholders_are_skipped():
    glue = MagicMock()
    with patch.object(handler, "glue_client", return_value=glue):
        handler.lambda_handler(s3_event("claims/"), None)
    glue.start_job_run.assert_not_called()
