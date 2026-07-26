#!/usr/bin/env python3
"""
CHD Conversion Utility for RomM

Automates converting disc-based games (.7z, .zip, .cue, .bin, .gdi, .iso) to compressed .CHD format
for emulators (PSX, PS2, Dreamcast, Saturn, etc.).
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def find_executable(name: str, fallback_paths: list[str]) -> str | None:
    """Find executable in system PATH or fallback locations."""
    found = shutil.which(name)
    if found:
        return found

    for path in fallback_paths:
        if os.path.exists(path):
            return path
    return None


def get_tools(custom_chdman: str | None = None, custom_7z: str | None = None):
    """Locate chdman and 7-Zip binaries across Windows, macOS, and Linux."""
    home_dir = Path.home()
    chdman_fallbacks = [
        # macOS Homebrew (Apple Silicon & Intel)
        "/opt/homebrew/bin/chdman",
        "/usr/local/bin/chdman",
        "/usr/bin/chdman",
        # Windows paths
        r"C:\Program Files\MAME\chdman.exe",
        r"C:\MAME\chdman.exe",
        str(home_dir / "Desktop" / "ROM-Librarian-v1.3.0-Windows" / "ROM Librarian" / "_internal" / "chdman.exe"),
    ]
    sevenzip_fallbacks = [
        # macOS Homebrew / Linux
        "/opt/homebrew/bin/7z",
        "/opt/homebrew/bin/7za",
        "/usr/local/bin/7z",
        "/usr/local/bin/7za",
        "/usr/bin/7z",
        "/usr/bin/7za",
        # Windows paths
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ]

    chdman = custom_chdman or find_executable("chdman", chdman_fallbacks)
    sevenzip = custom_7z or find_executable("7z", sevenzip_fallbacks) or find_executable("7za", sevenzip_fallbacks)

    return chdman, sevenzip


def convert_cue_to_chd(chdman_bin: str, input_file: Path, output_chd: Path) -> bool:
    """Run chdman createcd / createdvd to convert input disc descriptor to .chd."""
    cmd = [chdman_bin, "createcd", "-i", str(input_file), "-o", str(output_chd)]
    
    # Use createdvd for DVD ISOs if needed
    if input_file.suffix.lower() == ".iso":
        cmd[1] = "createdvd"

    print(f"--> Converting '{input_file.name}' to '{output_chd.name}'...")
    try:
        res = subprocess.run(cmd, check=True)
        return res.returncode == 0 and output_chd.exists() and output_chd.stat().st_size > 0
    except subprocess.CalledProcessError as e:
        print(f"Error running chdman: {e}", file=sys.stderr)
        return False


def process_directory(
    target_dir: Path,
    chdman_bin: str,
    sevenzip_bin: str | None,
    keep_originals: bool = False,
):
    """Process all archives and cue/bin folders in the target directory."""
    target_dir = target_dir.resolve()
    if not target_dir.exists():
        print(f"Directory not found: {target_dir}")
        return

    print("=" * 60)
    print("                CHD CONVERSION UTILITY")
    print("=" * 60)
    print(f"Target Directory: {target_dir}")
    print(f"CHDMAN Binary:    {chdman_bin}")
    print(f"7-Zip Binary:     {sevenzip_bin or 'Not found (archives will be skipped)'}")
    print(f"Keep Originals:   {keep_originals}")
    print("=" * 60 + "\n")

    # 1. Process subdirectories containing .cue / .gdi / .iso
    for entry in list(target_dir.iterdir()):
        if entry.is_dir() and entry.name != "assets":
            cue_files = list(entry.glob("*.cue")) + list(entry.glob("*.gdi")) + list(entry.glob("*.iso"))
            if not cue_files:
                continue

            cue_file = cue_files[0]
            out_chd = target_dir / f"{entry.name}.chd"

            if out_chd.exists():
                print(f"[SKIP] CHD already exists: '{out_chd.name}'")
                continue

            if convert_cue_to_chd(chdman_bin, cue_file, out_chd):
                print(f"[SUCCESS] Created '{out_chd.name}'")
                if not keep_originals:
                    print(f"[CLEANUP] Removing source folder '{entry.name}'")
                    shutil.rmtree(entry)
                    # Remove matching .7z / .zip if present
                    for ext in [".7z", ".zip", ".rar"]:
                        arch = target_dir / f"{entry.name}{ext}"
                        if arch.exists():
                            arch.unlink()
            else:
                print(f"[FAILED] Could not convert '{cue_file.name}'")

    # 2. Process archives (.7z, .zip)
    if sevenzip_bin:
        archives = list(target_dir.glob("*.7z")) + list(target_dir.glob("*.zip"))
        for archive in archives:
            out_chd = target_dir / f"{archive.stem}.chd"
            if out_chd.exists():
                print(f"[SKIP] CHD already exists for '{archive.name}'")
                if not keep_originals:
                    print(f"[CLEANUP] Removing archive '{archive.name}'")
                    archive.unlink()
                continue

            # Extract archive to temp folder
            with tempfile.TemporaryDirectory(dir=target_dir, prefix="_temp_") as temp_dir:
                temp_path = Path(temp_dir)
                print(f"Extracting '{archive.name}'...")
                extract_cmd = [sevenzip_bin, "x", str(archive), f"-o{temp_path}", "-y"]
                try:
                    subprocess.run(extract_cmd, check=True, stdout=subprocess.DEVNULL)
                except subprocess.CalledProcessError:
                    print(f"[ERROR] Failed to extract archive '{archive.name}'", file=sys.stderr)
                    continue

                # Find descriptor file
                desc_files = list(temp_path.rglob("*.cue")) + list(temp_path.rglob("*.gdi")) + list(temp_path.rglob("*.iso"))
                if not desc_files:
                    print(f"[WARN] No .cue/.gdi/.iso found inside '{archive.name}'")
                    continue

                desc_file = desc_files[0]
                if convert_cue_to_chd(chdman_bin, desc_file, out_chd):
                    print(f"[SUCCESS] Created '{out_chd.name}'")
                    if not keep_originals:
                        print(f"[CLEANUP] Removing original archive '{archive.name}'")
                        archive.unlink()
                else:
                    print(f"[FAILED] Could not convert '{archive.name}'")

    print("\n" + "=" * 60)
    print("Conversion process finished!")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Convert disc-based game archives to .CHD format.")
    parser.add_argument(
        "directory",
        nargs="?",
        default=None,
        help="Path to the ROMs directory or platform subfolder (e.g. romm_data/library/roms/psx or romm_data/library/roms)",
    )
    parser.add_argument(
        "--keep-originals",
        action="store_true",
        help="Keep original archives (.7z/.zip) and folders after conversion",
    )
    parser.add_argument("--chdman", help="Custom path to chdman executable")
    parser.add_argument("--sevenzip", help="Custom path to 7z executable")

    args = parser.parse_args()

    chdman_bin, sevenzip_bin = get_tools(args.chdman, args.sevenzip)

    if not chdman_bin:
        print(
            "Error: 'chdman' executable not found in PATH or standard paths.\n"
            "Please install chdman / MAME tools or specify path with --chdman.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Determine target directory
    if args.directory:
        target_path = Path(args.directory)
    else:
        # Check if romm_data/library/roms/psx or romm_data/library/roms exists
        if Path("romm_data/library/roms/psx").exists():
            target_path = Path("romm_data/library/roms/psx")
        elif Path("romm_data/library/roms").exists():
            target_path = Path("romm_data/library/roms")
        else:
            target_path = Path(".")

    target_path = target_path.resolve()

    # Check if target_path is a root roms directory containing platform folders (like psx, ps2, dc)
    subdirs = [d for d in target_path.iterdir() if d.is_dir() and d.name != "assets"] if target_path.exists() else []
    disc_platforms = {"psx", "ps2", "dc", "saturn", "segacd", "pcenginecd", "arcade", "3ds", "ngc", "wii"}
    
    # If the directory passed is the parent 'roms' folder containing platform folders, process each disc platform
    if any(d.name.lower() in disc_platforms for d in subdirs):
        print(f"Detected root ROMs directory with multiple platforms at '{target_path}'. Processing disc platforms...")
        for platform_dir in subdirs:
            if platform_dir.name.lower() in disc_platforms or any(platform_dir.glob("*.7z")) or any(platform_dir.glob("*.zip")):
                process_directory(platform_dir, chdman_bin, sevenzip_bin, args.keep_originals)
    else:
        process_directory(target_path, chdman_bin, sevenzip_bin, args.keep_originals)


if __name__ == "__main__":
    main()
