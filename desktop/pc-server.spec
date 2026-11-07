# PyInstaller-Beschreibung für den Server der Desktop-App.
# Bauen: desktop/build.sh (baut zuerst die Oberfläche und ruft dann PyInstaller auf).
from PyInstaller.utils.hooks import collect_submodules, copy_metadata

datas = [("../web/dist", "web_dist"), ("../docs", "procurator/docs")]
# Die Liste der Lizenzen («Über das Programm») liest die Metadaten der installierten Pakete.
datas += copy_metadata("procurator-capsularum", recursive=True)
try:
    datas += copy_metadata("anthropic", recursive=True)  # optional: Claude-Anbindung
except Exception:
    pass

for extra in ("uvloop", "httptools", "watchfiles", "python-dotenv", "PyYAML"):  # uvicorn[standard]
    try:
        datas += copy_metadata(extra)
    except Exception:
        pass
# Die Lizenzen der Oberfläche («Über das Programm») stehen in diesen Dateien.
datas += [("../web/package.json", "web")]
for name in ("react", "react-dom"):
    datas += [(f"../web/node_modules/{name}/package.json", f"web/node_modules/{name}")]

hiddenimports = collect_submodules("uvicorn") + collect_submodules("procurator") + ["pillow_heif", "pypdf"]

a = Analysis(
    ["entry.py"],
    pathex=["../src"],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "PyInstaller", "pytest", "setuptools"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="pc-server", console=True)
coll = COLLECT(exe, a.binaries, a.datas, name="pc-server")
