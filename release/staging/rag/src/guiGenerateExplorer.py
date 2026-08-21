from __future__ import annotations

import ctypes
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import ttk, messagebox


# Make Tkinter sharper on Windows high-DPI displays.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


REPO_ROOT = Path(r"C:\GitHub\metastock-RAG-LLM")


class MetaStockLLMGui:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.tk.call("tk", "scaling", 1.25)

        self.root.title("MetaStock LLM Automator")
        self.root.geometry("980x760")
        self.root.minsize(820, 620)

        self.base_width = 980
        self.base_height = 760
        self.current_scale = 1.0
        self._configure_after_id: str | None = None

        self.font_title = tkfont.Font(family="Segoe UI", size=16, weight="bold")
        self.font_base = tkfont.Font(family="Segoe UI", size=10)
        self.font_small = tkfont.Font(family="Segoe UI", size=9)
        self.font_log = tkfont.Font(family="Consolas", size=10)

        self.style = ttk.Style(self.root)
        self._apply_font_scale(force=True)
        self.root.bind("<Configure>", self._on_root_configure)

        self.output_queue: queue.Queue[str] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.process: subprocess.Popen | None = None

        self.prompt_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")
        self.spinner_var = tk.StringVar(value="")
        self.elapsed_var = tk.StringVar(value="")
        self._run_started_at: float | None = None
        self._spinner_running = False
        self._spinner_index = 0
        self._spinner_frames = ["◐", "◓", "◑", "◒"]

        # LLM / storage options
        self.save_excel_var = tk.BooleanVar(value=True)
        self.save_supabase_var = tk.BooleanVar(value=True)
        self.use_supabase_cache_var = tk.BooleanVar(value=True)
        self.cache_any_model_var = tk.BooleanVar(value=False)

        # Automator options
        self.run_automator_var = tk.BooleanVar(value=False)
        self.automator_dry_run_var = tk.BooleanVar(value=True)
        self.instruments_var = tk.StringVar(value="all")

        self._build_ui()
        self._poll_output_queue()

    def run(self) -> None:
        self.root.mainloop()

    # ============================================================
    # Responsive font scaling
    # ============================================================

    def _on_root_configure(self, event: tk.Event) -> None:
        if event.widget is not self.root:
            return

        if self._configure_after_id is not None:
            self.root.after_cancel(self._configure_after_id)

        self._configure_after_id = self.root.after(80, self._apply_font_scale)

    def _apply_font_scale(self, force: bool = False) -> None:
        self._configure_after_id = None

        raw_width = self.root.winfo_width()
        raw_height = self.root.winfo_height()

        # Before the first draw, Tk may report width/height as 1.
        # Use the design size so the initial font size is not incorrectly shrunk.
        width = self.base_width if raw_width <= 1 else max(raw_width, self.root.minsize()[0])
        height = self.base_height if raw_height <= 1 else max(raw_height, self.root.minsize()[1])

        scale = min(width / self.base_width, height / self.base_height)
        scale = max(0.85, min(scale, 1.65))

        if not force and abs(scale - self.current_scale) < 0.03:
            return

        self.current_scale = scale
        self.root.tk.call("tk", "scaling", 1.25 * scale)

        self.font_title.configure(size=max(12, round(16 * scale)))
        self.font_base.configure(size=max(8, round(10 * scale)))
        self.font_small.configure(size=max(7, round(9 * scale)))
        self.font_log.configure(size=max(8, round(10 * scale)))

        self.style.configure("TLabel", font=self.font_base)
        self.style.configure("TButton", font=self.font_base)
        self.style.configure("TCheckbutton", font=self.font_base)
        self.style.configure("TEntry", font=self.font_base)
        self.style.configure("TLabelframe.Label", font=self.font_base)

    # ============================================================
    # Running indicator
    # ============================================================

    def _set_running_state(self, status_text: str) -> None:
        self.status_var.set(status_text)
        self.elapsed_var.set("00:00")
        self._run_started_at = time.monotonic()
        self._spinner_running = True
        self._spinner_index = 0
        self._animate_running_indicator()

    def _finish_run_status(self, status_text: str) -> None:
        self._spinner_running = False
        self.spinner_var.set("")
        self.elapsed_var.set("")
        self.status_var.set(status_text)
        self._run_started_at = None

    def _animate_running_indicator(self) -> None:
        if not self._spinner_running:
            return

        frame = self._spinner_frames[self._spinner_index % len(self._spinner_frames)]
        self._spinner_index += 1
        self.spinner_var.set(frame)

        if self._run_started_at is not None:
            elapsed_seconds = int(time.monotonic() - self._run_started_at)
            minutes, seconds = divmod(elapsed_seconds, 60)
            self.elapsed_var.set(f"{minutes:02d}:{seconds:02d}")

        self.root.after(200, self._animate_running_indicator)

    # ============================================================
    # UI
    # ============================================================

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill="both", expand=True)

        title = ttk.Label(
            main,
            text="MetaStock LLM Automator",
            font=self.font_title,
        )
        title.pack(anchor="w", pady=(0, 12))

        # ------------------------------------------------------------
        # Prompt
        # ------------------------------------------------------------

        prompt_frame = ttk.LabelFrame(main, text="Prompt", padding=10)
        prompt_frame.pack(fill="x", pady=(0, 12))

        self.prompt_entry = ttk.Entry(prompt_frame, textvariable=self.prompt_var)
        self.prompt_entry.pack(fill="x", pady=(0, 8))
        self.prompt_entry.bind("<Return>", lambda _event: self._on_start_clicked())

        hint = ttk.Label(
            prompt_frame,
            text=(
                "Example: Find stocks where RSI is below 30 and close is above "
                "50 day moving average"
            ),
            foreground="#555555",
        )
        hint.pack(anchor="w")

        # ------------------------------------------------------------
        # Storage / cache options
        # ------------------------------------------------------------

        storage_frame = ttk.LabelFrame(main, text="Storage and Cache", padding=10)
        storage_frame.pack(fill="x", pady=(0, 12))

        ttk.Checkbutton(
            storage_frame,
            text="Save to Excel",
            variable=self.save_excel_var,
        ).pack(side="left", padx=(0, 18))

        ttk.Checkbutton(
            storage_frame,
            text="Save to Supabase",
            variable=self.save_supabase_var,
        ).pack(side="left", padx=(0, 18))

        ttk.Checkbutton(
            storage_frame,
            text="Use Supabase cache",
            variable=self.use_supabase_cache_var,
        ).pack(side="left", padx=(0, 18))

        ttk.Checkbutton(
            storage_frame,
            text="Cache any model",
            variable=self.cache_any_model_var,
        ).pack(side="left")

        # ------------------------------------------------------------
        # Automator options
        # ------------------------------------------------------------

        automator_frame = ttk.LabelFrame(main, text="Automator", padding=10)
        automator_frame.pack(fill="x", pady=(0, 12))

        ttk.Checkbutton(
            automator_frame,
            text="Run automator after generation",
            variable=self.run_automator_var,
        ).pack(side="left", padx=(0, 18))

        ttk.Checkbutton(
            automator_frame,
            text="Automator dry run",
            variable=self.automator_dry_run_var,
        ).pack(side="left", padx=(0, 18))

        ttk.Label(automator_frame, text="Instruments:").pack(side="left")

        ttk.Entry(
            automator_frame,
            textvariable=self.instruments_var,
            width=20,
        ).pack(side="left", padx=(6, 0))

        # ------------------------------------------------------------
        # Buttons
        # ------------------------------------------------------------

        buttons = ttk.Frame(main)
        buttons.pack(fill="x", pady=(0, 10))

        self.start_button = ttk.Button(
            buttons,
            text="Generate",
            command=self._on_start_clicked,
        )
        self.start_button.pack(side="left")

        self.stop_button = ttk.Button(
            buttons,
            text="Stop",
            command=self._on_stop_clicked,
            state="disabled",
        )
        self.stop_button.pack(side="left", padx=(8, 0))

        ttk.Button(
            buttons,
            text="Clear Log",
            command=self._clear_log,
        ).pack(side="left", padx=(8, 0))

        status_frame = ttk.Frame(main)
        status_frame.pack(fill="x", pady=(0, 6))

        ttk.Label(status_frame, text="Status:").pack(side="left")
        ttk.Label(status_frame, textvariable=self.spinner_var, width=2).pack(
            side="left", padx=(6, 2)
        )
        ttk.Label(status_frame, textvariable=self.status_var).pack(side="left")
        ttk.Label(status_frame, textvariable=self.elapsed_var).pack(
            side="left", padx=(8, 0)
        )

        # ------------------------------------------------------------
        # Log box
        # ------------------------------------------------------------

        log_frame = ttk.LabelFrame(main, text="Process Log", padding=8)
        log_frame.pack(fill="both", expand=True)

        self.log_box = tk.Text(log_frame, wrap="word", height=28, font=self.font_log)
        self.log_box.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(log_frame, command=self.log_box.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_box.configure(yscrollcommand=scrollbar.set)

    # ============================================================
    # Command construction
    # ============================================================

    def _build_command(self, prompt: str) -> list[str]:
        cmd = [
            sys.executable,
            "-m",
            "src.generate_explorer",
            prompt,
        ]

        # Excel saving
        if not self.save_excel_var.get():
            cmd.append("--no-save")

        # Supabase saving
        if self.save_supabase_var.get():
            cmd.append("--save-supabase")

        # Supabase cache
        if self.use_supabase_cache_var.get():
            cmd.append("--use-supabase-cache")

        if self.cache_any_model_var.get():
            cmd.append("--cache-any-model")

        # Automator
        if self.run_automator_var.get():
            cmd.append("--run-automator")

        if self.automator_dry_run_var.get():
            cmd.append("--automator-dry-run")

        instruments = self.instruments_var.get().strip() or "all"
        cmd.extend(["--instruments", instruments])

        return cmd
    
    def _clean_prompt(self, prompt: str) -> str:
        """
        Remove accidental wrapping quotes from GUI input.

        Examples:
            "Find stocks..."  -> Find stocks...
            'Find stocks...'  -> Find stocks...
            ""Find stocks..."" -> Find stocks...
        """
        text = (prompt or "").strip()

        changed = True
        while changed and len(text) >= 2:
            changed = False

            if text.startswith('"') and text.endswith('"'):
                text = text[1:-1].strip()
                changed = True

            if text.startswith("'") and text.endswith("'"):
                text = text[1:-1].strip()
                changed = True

        return text

    # ============================================================
    # Event handlers
    # ============================================================

    def _on_start_clicked(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("MetaStock LLM Automator", "A run is already active.")
            return

        prompt = self._clean_prompt(self.prompt_var.get())

        if not prompt:
            messagebox.showerror("Missing prompt", "Please enter a prompt.")
            return

        if self.run_automator_var.get() and not self.save_excel_var.get():
            messagebox.showerror(
                "Invalid option combination",
                (
                    "The current automator bridge still reads from Excel. "
                    "Keep 'Save to Excel' enabled when running automator.\n\n"
                    "Later, after the Supabase API bridge is implemented, this restriction can be removed."
                ),
            )
            return

        cmd = self._build_command(prompt)

        self._append_log("\n=== Starting MetaStock LLM workflow ===\n")
        self._append_log(f"Prompt: {prompt}\n")
        self._append_log(f"Command: {self._format_command(cmd)}\n\n")

        self._set_running_state("Running")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")

        self.worker = threading.Thread(
            target=self._run_subprocess,
            args=(cmd,),
            daemon=True,
        )
        self.worker.start()

    def _on_stop_clicked(self) -> None:
        if self.process and self.process.poll() is None:
            self._append_log("\n[GUI] Stopping process...\n")
            self.process.terminate()
            self.status_var.set("Stopping")

    # ============================================================
    # Subprocess / log streaming
    # ============================================================

    def _run_subprocess(self, cmd: list[str]) -> None:
        try:
            self.process = subprocess.Popen(
                cmd,
                cwd=str(REPO_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            assert self.process.stdout is not None

            for line in self.process.stdout:
                self.output_queue.put(line)

            return_code = self.process.wait()

            if return_code == 0:
                self.output_queue.put("\n=== Workflow completed successfully ===\n")
                self.output_queue.put("__STATUS_READY__")
            else:
                self.output_queue.put(
                    f"\n=== Workflow failed with exit code {return_code} ===\n"
                )
                self.output_queue.put("__STATUS_FAILED__")

        except Exception as e:
            self.output_queue.put(f"\n[GUI ERROR] {e}\n")
            self.output_queue.put("__STATUS_FAILED__")

    def _poll_output_queue(self) -> None:
        try:
            while True:
                text = self.output_queue.get_nowait()

                if text == "__STATUS_READY__":
                    self._finish_run_status("Ready")
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    continue

                if text == "__STATUS_FAILED__":
                    self._finish_run_status("Failed")
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    continue

                self._append_log(text)

        except queue.Empty:
            pass

        self.root.after(100, self._poll_output_queue)

    def _append_log(self, text: str) -> None:
        self.log_box.insert("end", text)
        self.log_box.see("end")

    def _clear_log(self) -> None:
        self.log_box.delete("1.0", "end")

    @staticmethod
    def _format_command(cmd: list[str]) -> str:
        return " ".join(f'"{part}"' if " " in part else part for part in cmd)


def main() -> None:
    app = MetaStockLLMGui()
    app.run()


if __name__ == "__main__":
    main()