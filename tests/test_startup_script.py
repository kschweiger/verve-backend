import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("sync_failure", [False, True])
def test_catalog_sync_precedes_server_start(tmp_path, sync_failure) -> None:
    script = Path(__file__).resolve().parents[1] / "run.sh"
    log = tmp_path / "calls"
    for program in ("alembic", "python", "uvicorn"):
        stub = tmp_path / program
        stub.write_text(
            "#!/bin/sh\n"
            'echo "' + program + ' $*" >> "$STARTUP_TEST_LOG"\n'
            'if [ "'
            + program
            + '" = python ] && [ "$2" = verve_backend.cli.import_exercises ]; then\n'
            '  exit "$STARTUP_SYNC_EXIT"\n'
            "fi\n"
        )
        stub.chmod(0o755)
    result = subprocess.run(
        ["/bin/bash", str(script)],
        env={
            **os.environ,
            "PATH": str(tmp_path),
            "ADMIN_PASSWORD": "",
            "STARTUP_TEST_LOG": str(log),
            "STARTUP_SYNC_EXIT": "1" if sync_failure else "0",
        },
        capture_output=True,
        text=True,
        timeout=10,
    )
    calls = log.read_text().splitlines()
    assert calls[:2] == [
        "alembic upgrade head",
        "python -m verve_backend.cli.import_exercises",
    ]
    if sync_failure:
        assert result.returncode != 0
        assert len(calls) == 2
    else:
        assert result.returncode == 0, result.stderr
        assert calls[2] == "python -m verve_backend.cli.ensure_rls"
        assert calls[3].startswith("uvicorn verve_backend.main:app")
