"""Tkinter GUI.

Fixes vs v1: worker threads never touch Tk widgets directly (they post to a
queue that the UI thread drains), no blocking ``input()`` call, no
``subprocess.run(["python", ...])`` (which broke in the frozen .exe), and
configs are edited as validated JSON instead of line-patching Python files.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog, ttk

from .autoconfig import autoconfigure, guess_search_url, suggest_fixes
from .config import ConfigError, SiteConfig, list_sites, load_config, parse_config, save_config
from .parser import NA, parse_html
from .scraper import check_config, fetch_html, scrape_site
from .security import SecurityError


class ScraperGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("WebScraper Pro")
        self.root.geometry("720x560")
        self.ui_queue: queue.Queue = queue.Queue()  # str = log line, callable = run on UI thread
        self._build()
        self.root.after(100, self._drain_logs)

    # ---- UI ---------------------------------------------------------------
    def _build(self) -> None:
        tk.Label(self.root, text="Select site:").pack(pady=(10, 0))
        self.site_var = tk.StringVar()
        self.site_menu = ttk.Combobox(self.root, textvariable=self.site_var, state="readonly")
        self.site_menu.pack(pady=5)
        self.refresh_sites()

        tk.Label(self.root, text="Keyword:").pack()
        self.keyword_entry = tk.Entry(self.root, width=40)
        self.keyword_entry.pack(pady=5)

        opts = tk.Frame(self.root)
        opts.pack()
        self.headless_var = tk.BooleanVar(value=True)
        self.images_var = tk.BooleanVar(value=True)
        self.robots_var = tk.BooleanVar(value=True)
        tk.Checkbutton(opts, text="Headless", variable=self.headless_var).pack(side="left", padx=4)
        tk.Checkbutton(opts, text="Embed images", variable=self.images_var).pack(side="left", padx=4)
        tk.Checkbutton(opts, text="Obey robots.txt", variable=self.robots_var).pack(side="left", padx=4)

        bar = tk.Frame(self.root)
        bar.pack(pady=8)
        self.buttons = [
            tk.Button(bar, text="Start scraping", command=self.start),
            tk.Button(bar, text="Generate config", command=self.generate_config),
            tk.Button(bar, text="Preview selectors", command=self.preview),
            tk.Button(bar, text="Test all configs", command=self.test_all),
        ]
        for b in self.buttons:
            b.pack(side="left", padx=4)

        self.log_box = scrolledtext.ScrolledText(self.root, height=22, width=90, state="disabled")
        self.log_box.pack(padx=8, pady=8, fill="both", expand=True)

    def refresh_sites(self) -> None:
        sites = list_sites()
        self.site_menu["values"] = sites
        if sites and not self.site_var.get():
            self.site_menu.current(0)

    # ---- thread-safe logging ---------------------------------------------
    def log(self, message: str) -> None:
        """Safe to call from any thread."""
        self.ui_queue.put(str(message))

    def call_ui(self, fn) -> None:
        """Run ``fn`` on the UI thread (safe to call from any thread)."""
        self.ui_queue.put(fn)

    def _drain_logs(self) -> None:
        try:
            while True:
                item = self.ui_queue.get_nowait()
                if callable(item):
                    item()
                    continue
                self.log_box.config(state="normal")
                self.log_box.insert(tk.END, item + "\n")
                self.log_box.yview(tk.END)
                self.log_box.config(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self._drain_logs)

    def _busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.call_ui(lambda: [b.config(state=state) for b in self.buttons])

    def _run_bg(self, fn) -> None:
        def wrapper():
            self._busy(True)
            try:
                fn()
            except (ConfigError, SecurityError, PermissionError) as exc:
                self.log(f"Error: {exc}")
            except Exception as exc:  # noqa: BLE001 - show any failure in the log, never crash the UI
                self.log(f"Unexpected error: {exc!r}")
            finally:
                self._busy(False)

        threading.Thread(target=wrapper, daemon=True).start()

    # ---- actions ------------------------------------------------------------
    def _inputs(self) -> tuple[str, str] | None:
        site, keyword = self.site_var.get().strip(), self.keyword_entry.get().strip()
        if not site or not keyword:
            messagebox.showwarning("Input error", "Please select a site and enter a keyword.")
            return None
        return site, keyword

    def start(self) -> None:
        inputs = self._inputs()
        if not inputs:
            return
        site, keyword = inputs
        headless, images, robots = self.headless_var.get(), self.images_var.get(), self.robots_var.get()

        def task():
            cfg = load_config(site)
            self.log(f"Scraping '{site}' for '{keyword}'...")
            res = scrape_site(
                cfg, keyword, headless=headless, images=images, respect_robots=robots, log=self.log
            )
            self.log(f"Done: {len(res.rows)} products.\n")

        self._run_bg(task)

    def generate_config(self) -> None:
        domain = simpledialog.askstring(
            "New config", "Site URL (https://www.site.com) or a search URL with {query}:"
        )
        if not domain:
            return
        site = simpledialog.askstring("New config", "Short site name (a-z, 0-9, - _):")
        if not site:
            return

        def task():
            self.log(f"Generating config for '{site}'...")
            target = domain.strip()
            if "{query}" not in target and guess_search_url(target) is None:
                self.log("Could not detect the search URL. Re-run with a full URL containing {query}.")
                return
            path = autoconfigure(target, site.strip().lower())
            self.call_ui(self.refresh_sites)
            self.log(f"Config written: {path}\n")

        self._run_bg(task)

    def preview(self) -> None:
        inputs = self._inputs()
        if not inputs:
            return
        site, keyword = inputs

        def task():
            from bs4 import BeautifulSoup

            cfg = load_config(site)
            html = fetch_html(
                cfg, keyword, headless=False, respect_robots=self.robots_var.get(), log=self.log
            )
            rows = parse_html(html, cfg)
            soup = BeautifulSoup(html, "html.parser")
            items = soup.select(cfg.selectors["item"])
            self.log(f"{len(items)} blocks match '{cfg.selectors['item']}'")
            if not items:
                return
            self.log("Sample: " + (str(rows[0]) if rows else "nothing parsed"))
            fixes = suggest_fixes(items[0])
            missing = {
                k: v
                for k, v in fixes.items()
                if (rows[0].get(k, NA) if rows else NA) == NA and k not in cfg.selectors
            }
            for key, sel in missing.items():
                self.log(f"Missing '{key}' -> suggestion: {sel}")
            if missing:
                self.call_ui(lambda: self._offer_fixes(cfg, missing))

        self._run_bg(task)

    def _offer_fixes(self, cfg: SiteConfig, fixes: dict[str, str]) -> None:
        if not messagebox.askyesno("Update config?", f"Apply {len(fixes)} suggested selector(s)?"):
            return
        try:
            new = parse_config({**cfg.to_dict(), "selectors": {**cfg.selectors, **fixes}})
            save_config(new, overwrite=True)
            self.log("Config updated.")
        except ConfigError as exc:
            self.log(f"Could not apply fixes: {exc}")

    def test_all(self) -> None:
        keyword = self.keyword_entry.get().strip() or "laptop"

        def task():
            self.log("Testing all configs...")
            for site in list_sites():
                try:
                    score = check_config(load_config(site), keyword, log=self.log)
                    self.log(f"{site}: {score:.0%} of fields parsed")
                except Exception as exc:  # noqa: BLE001 - continue with the next config
                    self.log(f"{site}: ERROR {exc}")

        self._run_bg(task)


def main() -> None:
    root = tk.Tk()
    ScraperGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
