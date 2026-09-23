"""
Case Analysis GUI
Tkinter-based front-end for Snowflake case tools.
"""
# Reconstructed from PyInstaller/Python-3.14 bytecode disassembly.
# This file is a best-effort manual reconstruction, not a guaranteed byte-exact
# recovery. Please review/test before relying on it, especially the larger
# GUI panel methods further down (marked TODO / needs review).

import getpass
import os
import sys
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk


class _LogFileStream:
    """Minimal file-like object that appends every write() to gui_debug.log."""

    def __init__(self, path):
        self._path = path

    def write(self, data):
        # TODO: verify exact append/flush behavior against bytecode (lines 34-41)
        with open(self._path, "a") as f:
            f.write(data)

    def flush(self):
        # TODO: verify exact body (lines 42+) - likely a no-op
        pass


if getattr(sys, "frozen", False):
    _debug_log_base = os.path.dirname(sys.executable)
else:
    _debug_log_base = os.path.dirname(os.path.abspath(__file__))

_debug_log_path = os.path.join(_debug_log_base, "gui_debug.log")

if sys.stdout is None:
    sys.stdout = _LogFileStream(_debug_log_path)
if sys.stderr is None:
    sys.stderr = _LogFileStream(_debug_log_path)


def _install_robust_browser_open():
    import webbrowser as _wb

    _original_open_new = _wb.open_new

    def _robust_open_new(url):
        if sys.platform == "win32":
            try:
                import subprocess
                subprocess.Popen(
                    f'start "" "{url}"',
                    shell=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                return True
            except Exception:
                pass
        return _original_open_new(url)

    _wb.open_new = _robust_open_new


_install_robust_browser_open()

_ssl_ok = False
_ssl_ready = threading.Event()


def _init_ssl():
    """Run in a background thread so the window opens immediately."""
    global _ssl_ok
    try:
        import ssl_setup
        _ssl_ok = ssl_setup.configure()
    except Exception:
        _ssl_ok = False
    finally:
        _ssl_ready.set()


threading.Thread(target=_init_ssl, daemon=True).start()


def _build_connection_params():
    """Block (briefly) until SSL is configured, then return params."""
    _ssl_ready.wait()
    return {
        "account": "ciena-ciena",
        "user": getpass.getuser().upper() + "@CIENA.COM",
        "authenticator": "externalbrowser",
        "role": "SSO_SNOWFLAKE_GAI_SVC_RO",
        "warehouse": "GAI_POC",
        "database": "FLYGAIP",
        "schema": "GAI_SERVICES",
        "insecure_mode": not _ssl_ok,
        "disable_ocsp_checks": True,
    }


# TODO: class CaseAnalysisApp - see GUI_disassembly_full.txt line 672 onward.
# This is the bulk of the application (35+ methods). Reconstructing it
# reliably requires going through it method-by-method - let's do that next.


def main():
    root = tk.Tk()
    CaseAnalysisApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
