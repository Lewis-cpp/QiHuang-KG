"""The M7 recovery drill must not let an inherited DSN redirect its subprocesses away from qihuang_restore.

Run with .venv/bin/python tests/test_drill_m7.py; touches no database.
"""

import os
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT))


def main():
    with patch('backend.services.application', return_value={'build_id': 'x'}):
        import drill_m7
    shutil.rmtree(drill_m7.TEMP, ignore_errors=True)
    with patch.dict(os.environ, POSTGRES_DSN='dbname=qihuang', VASTBASE_DSN='dbname=qihuang', KEEP='1'), \
            patch.object(drill_m7.subprocess, 'run') as run:
        drill_m7.run(['true'], env={'QIHUANG_CONFIG_DIR': '/tmp/x'})
    env = run.call_args.kwargs['env']
    assert 'POSTGRES_DSN' not in env and 'VASTBASE_DSN' not in env, 'DSN leaked into a drill subprocess'
    assert env['KEEP'] == '1' and env['QIHUANG_CONFIG_DIR'] == '/tmp/x'
    print('drill_m7: inherited DSNs are stripped from subprocesses')


if __name__ == '__main__':
    main()
