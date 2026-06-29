import os
import shutil
from pathlib import Path


TEST_DB = Path(__file__).parent / "test_control_hub.db"
TEST_WORKSPACE = Path(__file__).parent / "runtime_workspace"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["WORKSPACE_ROOT"] = str(TEST_WORKSPACE)
TEST_WORKSPACE.mkdir(exist_ok=True)


def pytest_sessionfinish(session, exitstatus):
    try:
        from app.database import engine

        engine.dispose()
    except Exception:
        pass
    for suffix in ("", "-shm", "-wal"):
        path = Path(f"{TEST_DB}{suffix}")
        if path.exists():
            try:
                path.unlink()
            except PermissionError:
                pass
    shutil.rmtree(TEST_WORKSPACE, ignore_errors=True)
