"""The ``briochette`` command."""

import argparse
import sys
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(prog="briochette")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="build the app for a phone")
    build.add_argument("--target", choices=["android", "ios"], required=True)
    build.add_argument("--abi", choices=["x86_64", "arm64"], default="arm64", help="Android ABI")
    build.add_argument("--ios", choices=["sim", "device"], default="device", help="iOS simulator or device")
    build.add_argument("--release", action="store_true", help="Android: a signed release build")
    build.add_argument("--project", type=Path, default=Path.cwd(), help="the app's project (pyproject.toml)")
    build.add_argument("--host", type=Path, required=True, help="briochette's host crate (host/briochette_host)")
    build.add_argument("--out", type=Path, default=Path("dist"))
    build.add_argument("--levain-pack", default="levain-pack")
    args = parser.parse_args(argv)

    from briochette import build as builder

    if args.target == "android":
        product = builder.android(
            args.project, args.abi, args.host, args.out, levain_pack=args.levain_pack, release=args.release
        )
    else:
        product = builder.ios(args.project, args.ios, args.host, args.out, levain_pack=args.levain_pack)
    print(f"built {product}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
