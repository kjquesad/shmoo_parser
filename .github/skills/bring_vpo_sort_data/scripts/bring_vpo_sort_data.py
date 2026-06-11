import argparse
import gzip
import re
import shutil
import zipfile
from pathlib import Path
from typing import List, Optional


DEFAULT_SORT_ROOT = Path("X:/datalogs/1276/eng")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Copy SORT scan data by wafer. Prefer zip package per wafer when present; "
            "otherwise copy/decompress .gz scans and merge into one .itf."
        )
    )
    parser.add_argument("--mv", required=True, help="MV number, for example 43DDS0T00")
    parser.add_argument("--location", required=True, help="Location code, for example 132322")
    parser.add_argument("--wafer", help="Optional single wafer id, for example 668")
    parser.add_argument(
        "--output-dir",
        help="Local destination root. Defaults to parsing_runs/<MV> in current workspace.",
    )
    parser.add_argument(
        "--sort-root",
        default=str(DEFAULT_SORT_ROOT),
        help="SORT root path (default: X:/datalogs/1276/eng)",
    )
    return parser.parse_args()


def normalize(text: str) -> str:
    return text.strip().upper()


def resolve_scan_root(sort_root: Path, mv: str, location: str) -> Path:
    scan_root = sort_root / f"{mv}_{location}" / "Scan"
    if not scan_root.is_dir():
        raise FileNotFoundError(f"Scan folder not found: {scan_root}")
    return scan_root


def resolve_output_root(mv: str, output_dir: Optional[str]) -> Path:
    if output_dir:
        return Path(output_dir)
    return Path("parsing_runs") / mv


def resolve_wafers(scan_root: Path, wafer: Optional[str]) -> List[str]:
    if wafer:
        wafer_id = wafer.strip()
        wafer_dir = scan_root / wafer_id
        if not wafer_dir.is_dir():
            raise FileNotFoundError(f"Wafer folder not found: {wafer_dir}")
        return [wafer_id]

    wafers = sorted(p.name for p in scan_root.iterdir() if p.is_dir())
    if not wafers:
        raise FileNotFoundError(f"No wafer folders found under: {scan_root}")
    return wafers


def copy_file(src: Path, dst_dir: Path) -> Path:
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    shutil.copy2(src, dst)
    return dst


def find_zip_candidates(wafer_dir: Path, mv: str, location: str, wafer: str) -> List[Path]:
    pattern = f"I{mv}__{location}.W{wafer}R*.zip"
    return sorted(p for p in wafer_dir.glob(pattern) if p.is_file())


def extract_zip(zip_path: Path, output_dir: Path) -> None:
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(output_dir)


def normalize_extracted_to_itf(output_dir: Path) -> List[Path]:
    """Rename extracted scan files to include .itf extension.

    Primary target format from SORT zip payloads is usually:
    I<MV>__<LOCATION>.W<wafer>R<rev>
    These are renamed in place to:
    I<MV>__<LOCATION>.W<wafer>R<rev>.itf
    """
    renamed: List[Path] = []
    for file_path in output_dir.rglob("*"):
        if not file_path.is_file():
            continue
        lower_name = file_path.name.lower()

        # Never rename compressed artifacts.
        if lower_name.endswith(".zip") or lower_name.endswith(".gz"):
            continue

        # Skip files that already have .itf extension.
        if lower_name.endswith(".itf"):
            continue

        # Match extracted SORT payload names like: I43DDS0T00__132322.W668R01
        # Note: pathlib sees suffix '.W668R01', but this is still the source file
        # shape we want to normalize to '.itf'.
        if re.match(r"^I[A-Za-z0-9]+__\d+\.W\d+R\d+$", file_path.name):
            new_path = file_path.with_name(file_path.name + ".itf")
            if new_path.exists():
                new_path.unlink()
            file_path.rename(new_path)
            renamed.append(new_path)

    # Cleanup pass: if an extensionless SORT scan file still exists but the
    # corresponding .itf file is present, remove the extensionless original.
    for file_path in output_dir.rglob("*"):
        if not file_path.is_file():
            continue
        if re.match(r"^I[A-Za-z0-9]+__\d+\.W\d+R\d+$", file_path.name):
            itf_path = file_path.with_name(file_path.name + ".itf")
            if itf_path.exists():
                file_path.unlink()

    return renamed


def copy_gz_files(wafer_dir: Path, output_dir: Path) -> List[Path]:
    gz_files = sorted(p for p in wafer_dir.iterdir() if p.is_file() and p.suffix.lower() == ".gz")
    if not gz_files:
        return []
    copied: List[Path] = []
    for src in gz_files:
        copied.append(copy_file(src, output_dir))
    return copied


def merge_gz_files(gz_files: List[Path], output_itf: Path) -> None:
    output_itf.parent.mkdir(parents=True, exist_ok=True)
    with output_itf.open("wb") as out_fh:
        for gz_path in gz_files:
            with gzip.open(gz_path, "rb") as in_fh:
                shutil.copyfileobj(in_fh, out_fh)


def cleanup_files(paths: List[Path]) -> None:
    for path in paths:
        if path.exists():
            path.unlink()


def cleanup_compressed_artifacts(output_dir: Path) -> None:
    """Remove any local compressed artifacts left in output_dir.

    This keeps local parsing_runs outputs clean even across repeated runs.
    """
    for pattern in ("*.zip", "*.gz", "*.zip.itf", "*.gz.itf"):
        for file_path in output_dir.glob(pattern):
            if file_path.is_file():
                file_path.unlink()


def main() -> int:
    args = parse_args()
    mv = normalize(args.mv)
    location = args.location.strip()

    sort_root = Path(args.sort_root)
    if not sort_root.is_dir():
        raise FileNotFoundError(f"SORT root folder not found: {sort_root}")

    scan_root = resolve_scan_root(sort_root, mv, location)
    output_root = resolve_output_root(mv, args.output_dir)
    wafers = resolve_wafers(scan_root, args.wafer)

    processed = 0
    zip_used = 0
    gz_used = 0
    created_artifacts: List[Path] = []

    for wafer in wafers:
        wafer_src = scan_root / wafer
        wafer_dst = output_root / wafer
        wafer_dst.mkdir(parents=True, exist_ok=True)

        zip_candidates = find_zip_candidates(wafer_src, mv, location, wafer)
        if zip_candidates:
            chosen_zip = zip_candidates[-1]
            copied_zip = copy_file(chosen_zip, wafer_dst)
            extract_zip(copied_zip, wafer_dst)
            renamed_itf = normalize_extracted_to_itf(wafer_dst)
            cleanup_files([copied_zip])
            cleanup_compressed_artifacts(wafer_dst)

            processed += 1
            zip_used += 1
            if renamed_itf:
                created_artifacts.extend(renamed_itf)
            else:
                created_artifacts.append(wafer_dst)
            continue

        copied_gz = copy_gz_files(wafer_src, wafer_dst)
        if not copied_gz:
            print(f"[warn] No matching zip or .gz files found for wafer {wafer} in {wafer_src}")
            continue

        output_itf = wafer_dst / f"{mv}_{location}_W{wafer}.itf"
        merge_gz_files(copied_gz, output_itf)
        cleanup_files(copied_gz)
        cleanup_compressed_artifacts(wafer_dst)

        processed += 1
        gz_used += 1
        created_artifacts.append(output_itf)

    if processed == 0:
        raise RuntimeError("No wafer data was processed. Check source files and input arguments.")

    print(f"MV: {mv}")
    print(f"Location: {location}")
    print(f"Source scan folder: {scan_root}")
    print(f"Destination root: {output_root.resolve()}")
    print(f"Wafers processed: {processed}")
    print(f"Wafer mode counts: zip={zip_used}, gz-merged={gz_used}")
    print("Created outputs:")
    for artifact in created_artifacts:
        print(f"- {artifact.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
