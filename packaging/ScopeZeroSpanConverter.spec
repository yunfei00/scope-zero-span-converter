# Executed by PyInstaller; onedir keeps Qt DLLs independently replaceable.
from pathlib import Path
import json

root = Path(SPECPATH).parent
metadata = json.loads((root / "build/packaging/metadata.json").read_text(encoding="utf-8"))
datas = [(str(root / "configs/default.json"), "configs"),
         (str(root / "assets/app.ico"), "assets"),
         (str(root / "build/packaging/notices"), "licenses")]
for document in ("README.md", "CHANGELOG.md", "THIRD_PARTY_NOTICES.md"):
    datas.append((str(root / document), "."))
datas.append((str(root / "docs/WINDOWS_INSTALLATION.md"), "docs"))

a = Analysis(
    [str(root / "run_gui.py")], pathex=[str(root / "src")],
    binaries=[], datas=datas,
    hiddenimports=["matplotlib.backends.backend_qtagg", "matplotlib.backends.backend_agg"],
    hookspath=[], runtime_hooks=[],
    hooksconfig={"matplotlib": {"backends": ["QtAgg", "Agg"]}},
    excludes=["PyQt5", "PyQt6", "PySide2", "tkinter", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name=metadata["application_id"], debug=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
    icon=str(root / "assets/app.ico"),
    version=str(root / "build/packaging/version-info.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=metadata["application_id"])
