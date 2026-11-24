"""Export known published source files and fingerprints for installed variants."""

import hashlib
import json
from pathlib import Path
import sys
import zipfile

LIMIT = 1024 * 1024
CATALOG = Path(__file__).with_name("mira-review-catalog.json")


def export(installation, destination):
    installation = installation.resolve(strict=True)
    if installation.name.lower() in {"windows", "shared"}:
        installation = installation.parent
    if not (installation / "Shared" / "FastChatUI.html").is_file():
        raise ValueError("Select the installed Mira folder containing Shared and Windows.")
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    report = {}
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, known_hashes in catalog.items():
            relative = Path(filename)
            if relative.anchor or ".." in relative.parts or relative.parts[0] not in {"Shared", "Windows"}:
                raise ValueError("Invalid review catalog path.")
            path = installation / relative
            if not path.is_file():
                report[filename] = {"status": "missing"}
                continue
            if path != path.resolve() or path.stat().st_size > LIMIT:
                report[filename] = {"status": "excluded"}
                continue
            with path.open("rb") as source:
                content = source.read(LIMIT + 1)
            if len(content) > LIMIT:
                report[filename] = {"status": "excluded"}
                continue
            if relative.suffix != ".png":
                content = content.replace(b"\r\n", b"\n")
            digest = hashlib.sha256(content).hexdigest()
            known = digest in known_hashes
            report[filename] = {"status": "included" if known else "unrecognized", "sha256": digest}
            if known:
                archive.writestr("source/" + relative.as_posix(), content)
        archive.writestr("mira-review.json", json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


if __name__ == "__main__":
    try:
        result = export(Path(sys.argv[1]), Path(sys.argv[2]))
    except (IndexError, OSError, ValueError) as error:
        print(f"Export failed: {error}", file=sys.stderr)
        sys.exit(1)
    included = sum(entry["status"] == "included" for entry in result.values())
    print(f"Review ZIP saved: {sys.argv[2]}")
    print(f"Published source files included: {included}")
    print("Unknown or changed files are recorded by fingerprint only.")
