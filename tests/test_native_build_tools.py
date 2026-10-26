from pathlib import Path
import runpy
import sys
import tarfile
from types import ModuleType

import pytest


def test_windowed_launcher_handles_missing_stderr(monkeypatch):
    import faulthandler
    import multiprocessing
    observed=[]
    def unavailable():raise RuntimeError('sys.stderr is None')
    monkeypatch.setattr(faulthandler,'enable',unavailable)
    monkeypatch.setattr(multiprocessing,'freeze_support',lambda:observed.append('freeze'))
    dispatcher=ModuleType('gui.utils.thread_dispatcher')
    dispatcher.install_qt_thread_and_font_guards=lambda:observed.append('guards')
    app=ModuleType('gui.app');app.main=lambda:0
    monkeypatch.setitem(sys.modules,'gui.utils.thread_dispatcher',dispatcher)
    monkeypatch.setitem(sys.modules,'gui.app',app)
    with pytest.raises(SystemExit) as result:
        runpy.run_path(str(Path(__file__).parents[1]/'run_gui.py'),run_name='__main__')
    assert result.value.code==0 and observed==['freeze','guards']


@pytest.mark.skipif(sys.platform in {'win32','darwin'},reason='Linux archive layout')
def test_native_archive_preserves_execution_and_excludes_project_data(tmp_path):
    from tools.package_desktop import package
    source=tmp_path/'dist/EthicalArmor';source.mkdir(parents=True)
    executable=source/'EthicalArmor';executable.write_bytes(b'synthetic executable');executable.chmod(0o755)
    (source/'_internal').mkdir();(source/'_internal/library.so').write_bytes(b'synthetic shared library')
    (source/'_internal/alias.so').symlink_to('library.so')
    (tmp_path/'database').mkdir();(tmp_path/'database/private.duckdb').write_bytes(b'NEVER PACKAGE')
    (tmp_path/'.env').write_text('SECRET=NEVER_PACKAGE')
    archive=package(tmp_path)
    with tarfile.open(archive) as reader:
        names=reader.getnames()
        assert reader.getmember('EthicalArmor/EthicalArmor').mode & 0o111
        assert reader.getmember('EthicalArmor/_internal/alias.so').issym()
        assert all('private.duckdb' not in name and '.env' not in name for name in names)
    assert archive.with_name(archive.name+'.sha256').is_file()
