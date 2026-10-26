# Native builds: run this spec separately on each supported operating system.
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

root = Path(SPECPATH)
hidden = collect_submodules('modules') + collect_submodules('gui')
datas = collect_data_files('modules.reporting', includes=['assets/*'])
if (root / 'assets').is_dir():
    datas.append((str(root / 'assets'), 'assets'))
a = Analysis(
    [str(root / 'run_gui.py')], pathex=[str(root)], binaries=[], datas=datas,
    hiddenimports=hidden, hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['pytest', '_pytest', 'IPython', 'notebook', 'jupyter',
              'matplotlib', 'scipy', 'torch', 'tensorflow',
              'PyQt5', 'PyQt6', 'PySide2'], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='EthicalArmor',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False, argv_emulation=False,
    target_arch=None, codesign_identity=None, entitlements_file=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='EthicalArmor')
if sys.platform == 'darwin':
    app = BUNDLE(coll, name='EthicalArmor.app', bundle_identifier='org.ethicalarmor.desktop')
