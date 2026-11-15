"""Create a submission ZIP without data, keys, UI or local databases."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parent.parent
target = root / "output" / "submission.zip"
target.parent.mkdir(exist_ok=True)
with ZipFile(target, "w", ZIP_DEFLATED) as archive:
    for name in ("solution.py", "requirements.txt", "energytool/__init__.py", "energytool/core.py"):
        archive.write(root / name, name)
print(target)
