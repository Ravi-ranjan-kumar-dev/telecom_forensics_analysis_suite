# Desktop GUI launcher for EthicalArmor - Telecom & Digital Forensics Suite.
from __future__ import annotations

import faulthandler
import os
import sys

# Windowed Windows builds have no stderr stream.
try:
    faulthandler.enable()
except (AttributeError, RuntimeError):
    pass

if __name__ == '__main__':
    from multiprocessing import freeze_support
    freeze_support()

os.environ['TELECOM_GUI_MODE'] = '1'
os.environ['TELECOM_GUI_FAST_MODE'] = '1'
os.environ.setdefault('QT_LOGGING_RULES', 'qt.accessibility.atspi*=false')
os.environ.setdefault('QT_LINUX_ACCESSIBILITY_ALWAYS_ON', '0')

try:
    from gui.utils.thread_dispatcher import install_qt_thread_and_font_guards
    install_qt_thread_and_font_guards()
    from gui.app import main
    if __name__ == '__main__':
        sys.exit(main())
except Exception as e:
    import traceback
    print(f'[!] Critical GUI Startup Error: {e}', flush=True)
    traceback.print_exc()
    sys.exit(1)


