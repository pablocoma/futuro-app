"""CLI de `cv-builder`.

    cv-builder build --master PATH --bullet-bank PATH --role-content PATH \\
      --variants-config PATH --output-dir PATH
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .build import BuildError, build_all, load_sources
from .claim_rules import ClaimRuleViolation


def _build_command(args: argparse.Namespace) -> int:
    try:
        sources = load_sources(
            master_template_path=args.master,
            bullet_bank_path=args.bullet_bank,
            role_content_path=args.role_content,
            variants_config_path=args.variants_config,
        )
        built = build_all(sources, args.output_dir)
    except (BuildError, ClaimRuleViolation) as exc:
        print(f"cv-builder: {exc}", file=sys.stderr)
        return 1

    for variant_id in built:
        print(args.output_dir / variant_id)
    return 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="cv-builder")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser(
        "build", help="Genera el .tex y el README.md de cada variante base"
    )
    build_parser.add_argument("--master", type=Path, required=True)
    build_parser.add_argument("--bullet-bank", type=Path, required=True)
    build_parser.add_argument("--role-content", type=Path, required=True)
    build_parser.add_argument("--variants-config", type=Path, required=True)
    build_parser.add_argument("--output-dir", type=Path, required=True)
    build_parser.set_defaults(func=_build_command)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
