"""Command line interface:  python -m webscraper_pro <command> ..."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .autoconfig import autoconfigure
from .config import ConfigError, list_sites, load_config
from .scraper import check_config, scrape_site
from .security import SecurityError


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="webscraper-pro", description="Config-driven product scraper.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp):
        sp.add_argument("--config-dir", type=Path, default=None, help="Directory with <site>.json configs")
        sp.add_argument(
            "--allow-private",
            action="store_true",
            help="Allow private/loopback addresses (disables SSRF protection)",
        )

    s = sub.add_parser("scrape", help="Scrape a site for a keyword")
    common(s)
    s.add_argument("--site", required=True)
    s.add_argument("--keyword", required=True)
    s.add_argument("--out", type=Path, default=Path("output"))
    s.add_argument("--formats", default="json,csv,xlsx", help="Comma separated: json,csv,xlsx")
    s.add_argument("--no-images", action="store_true", help="Do not embed images in the Excel file")
    s.add_argument("--max-images", type=int, default=50)
    s.add_argument("--headful", action="store_true", help="Show the browser window")
    s.add_argument("--no-sandbox", action="store_true", help="Disable Chrome sandbox (Docker/root only)")
    s.add_argument("--ignore-robots", action="store_true", help="Do not obey robots.txt (need permission!)")

    a = sub.add_parser("autoconfig", help="Generate a config for a new site")
    common(a)
    a.add_argument("--url", required=True, help="Domain, or a search URL containing {query}")
    a.add_argument("--site", required=True)
    a.add_argument("--overwrite", action="store_true")

    t = sub.add_parser("test", help="Live-test every config")
    common(t)
    t.add_argument("--keyword", default="laptop")

    lst = sub.add_parser("list", help="List available site configs")
    lst.add_argument("--config-dir", type=Path, default=None)
    sub.add_parser("gui", help="Launch the Tk GUI")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "list":
            print("\n".join(list_sites(args.config_dir)) or "(no configs)")
        elif args.command == "scrape":
            formats = tuple(f.strip() for f in args.formats.split(",") if f.strip())
            cfg = load_config(args.site, args.config_dir)
            res = scrape_site(
                cfg,
                args.keyword,
                out_dir=args.out,
                formats=formats,
                images=not args.no_images,
                max_images=args.max_images,
                headless=not args.headful,
                no_sandbox=args.no_sandbox or None,
                allow_private=args.allow_private,
                respect_robots=not args.ignore_robots,
            )
            return 0 if res.rows else 1
        elif args.command == "autoconfig":
            path = autoconfigure(
                args.url,
                args.site,
                config_dir=args.config_dir,
                allow_private=args.allow_private,
                overwrite=args.overwrite,
            )
            print(f"Config written to {path}")
        elif args.command == "test":
            for site in list_sites(args.config_dir):
                try:
                    score = check_config(
                        load_config(site, args.config_dir), args.keyword, allow_private=args.allow_private
                    )
                    print(f"{site}: {score:.0%} of fields parsed")
                except Exception as exc:  # noqa: BLE001 - report and continue with next site
                    print(f"{site}: ERROR {exc}")
        elif args.command == "gui":
            from .gui import main as gui_main

            gui_main()
    except (ConfigError, SecurityError, PermissionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
