import argparse
import gzip
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple


DEFAULT_PROD_ROOT = Path("I:/hdmxdata/prod")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Copy VPO .gz files from production, merge decompressed files by step token, "
            "and remove local .gz copies."
        )
    )
    parser.add_argument("--vpo", required=True, help="VPO number, for example J623173MV")
    parser.add_argument("--location", help="Location code, for example 6248")
    parser.add_argument(
        "--output-dir",
        help="Local destination folder. Defaults to parsing_runs/<VPO> in current workspace.",
    )
    parser.add_argument(
        "--prod-root",
        default=str(DEFAULT_PROD_ROOT),
        help="Production root path (default: I:/hdmxdata/prod)",
    )
    return parser.parse_args()


def normalize_vpo(vpo: str) -> str:
    return vpo.strip().upper()


def resolve_source_folder(prod_root: Path, vpo: str, location: Optional[str]) -> Tuple[Path, str]:
    if location:
        source = prod_root / f"{vpo}_{location}"
        if not source.is_dir():
            raise FileNotFoundError(f"Source folder not found: {source}")
        return source, location

    candidates = sorted(p for p in prod_root.glob(f"{vpo}_*") if p.is_dir())
    if not candidates:
        raise FileNotFoundError(f"No source folders found for VPO {vpo} under {prod_root}")

    if len(candidates) == 1:
        only = candidates[0]
        resolved_location = only.name.split("_", 1)[1] if "_" in only.name else "UNKNOWN"
        return only, resolved_location

    locations = []
    for candidate in candidates:
        if "_" in candidate.name:
            locations.append(candidate.name.split("_", 1)[1])

    options = ", ".join(locations) if locations else ", ".join(c.name for c in candidates)
    raise ValueError(
        "Multiple locations found for VPO "
        f"{vpo}. Please specify --location. Options: {options}"
    )


def resolve_output_dir(vpo: str, output_dir: Optional[str]) -> Path:
    if output_dir:
        return Path(output_dir)
    return Path("parsing_runs") / vpo


def copy_gz_files(source: Path, destination: Path) -> List[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    source_gz = sorted(p for p in source.iterdir() if p.is_file() and p.suffix.lower() == ".gz")
    if not source_gz:
        raise FileNotFoundError(f"No .gz files found in source folder: {source}")

    copied: List[Path] = []
    for src in source_gz:
        dst = destination / src.name
        shutil.copy2(src, dst)
        copied.append(dst)
    return copied


def extract_step_token(gz_path: Path) -> str:
    base = gz_path.name
    if base.lower().endswith(".gz"):
        base = base[:-3]

    stem = Path(base).stem
    if "_" in stem:
        return stem.rsplit("_", 1)[-1].upper()
    return "UNKNOWN"


def group_by_step(gz_files: List[Path]) -> Dict[str, List[Path]]:
    grouped: Dict[str, List[Path]] = {}
    for gz_file in gz_files:
        step = extract_step_token(gz_file)
        grouped.setdefault(step, []).append(gz_file)

    for step in grouped:
        grouped[step] = sorted(grouped[step], key=lambda p: p.name)
    return grouped


def merge_group_to_itf(group_files: List[Path], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as out_fh:
        for gz_file in group_files:
            with gzip.open(gz_file, "rb") as in_fh:
                shutil.copyfileobj(in_fh, out_fh)


def cleanup_local_gz(gz_files: List[Path]) -> None:
    for gz_file in gz_files:
        if gz_file.exists():
            gz_file.unlink()


def main() -> int:
    args = parse_args()
    vpo = normalize_vpo(args.vpo)
    prod_root = Path(args.prod_root)

    if not prod_root.is_dir():
        raise FileNotFoundError(f"Production root folder not found: {prod_root}")

    source_folder, resolved_location = resolve_source_folder(prod_root, vpo, args.location)
    output_dir = resolve_output_dir(vpo, args.output_dir)

    copied_gz = copy_gz_files(source_folder, output_dir)
    grouped = group_by_step(copied_gz)

    created_outputs: List[Path] = []
    for step, files in sorted(grouped.items()):
        out_name = f"{vpo}_{resolved_location}_{step}.itf"
        out_path = output_dir / out_name
        merge_group_to_itf(files, out_path)
        created_outputs.append(out_path)

    cleanup_local_gz(copied_gz)

    print(f"VPO: {vpo}")
    print(f"Location: {resolved_location}")
    print(f"Source folder: {source_folder}")
    print(f"Destination folder: {output_dir.resolve()}")
    print(f"Copied .gz files: {len(copied_gz)}")
    print(f"Step groups: {len(grouped)}")
    print("Output .itf files:")
    for output_file in created_outputs:
        print(f"- {output_file.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())