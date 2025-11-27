"""AI-powered regex builder dialog using Ollama, OpenAI, or Anthropic."""

import os
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import urllib.request
import urllib.error
import json


class RegexBuilderDialog:
    """Dialog for building regex patterns from natural language using AI."""

    OLLAMA_URL = "http://localhost:11434/api/generate"
    OPENAI_URL = "https://api.openai.com/v1/chat/completions"
    ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

    SYSTEM_PROMPT = """You are a regex expert. Generate a regex pattern based on the user's description.
Rules:
- Output ONLY the regex pattern, nothing else
- No explanation, no markdown, no quotes
- The regex will be used with Python's re.search() with IGNORECASE flag
- Keep patterns simple and efficient
- For "contains X but not Y" patterns, use: ^(?!.*Y).*X
- For "contains X and Y" patterns, use: ^(?=.*X)(?=.*Y)
- For "starts with X" patterns, use: ^X
- For "ends with X" patterns, use: X$
- Negative lookahead (?!.*pattern) must check the ENTIRE string, not just one position"""

    def __init__(self, parent, callback=None):
        """Initialize the dialog.

        Args:
            parent: Parent window
            callback: Function to call with the generated regex when "Use" is clicked
        """
        self.callback = callback
        self.top = tk.Toplevel(parent)
        self.top.title("AI Regex Builder")
        self.top.geometry("520x400")
        self.top.transient(parent)
        self.top.grab_set()

        # Detect available AI backends
        self.openai_key = self._find_api_key("OPENAI_API_KEY", ["~/.openai/key", "~/.config/openai/key"])
        self.anthropic_key = self._find_api_key("ANTHROPIC_API_KEY", ["~/.anthropic/key", "~/.config/anthropic/key"])
        self.backend = self._detect_backend()

        self._create_widgets()
        self.description_entry.focus()

        # ESC to close
        self.top.bind("<Escape>", lambda e: self.top.destroy())

    def _find_api_key(self, env_var, file_paths):
        """Find API key from environment variable or config files."""
        # Check environment variable first
        key = os.environ.get(env_var)
        if key:
            return key

        # Check common config file locations
        for path in file_paths:
            expanded = os.path.expanduser(path)
            if os.path.exists(expanded):
                try:
                    with open(expanded, "r") as f:
                        key = f.read().strip()
                        if key:
                            return key
                except Exception:
                    pass
        return None

    def _check_claude_cli(self):
        """Check if Claude CLI is installed."""
        try:
            result = subprocess.run(["which", "claude"], capture_output=True, timeout=5)
            return result.returncode == 0
        except Exception:
            return False

    def _detect_backend(self):
        """Detect which AI backend to use."""
        # Prefer Claude CLI if available (free, fast)
        if self._check_claude_cli():
            return "claude"
        # Then web APIs if keys are set
        if self.anthropic_key:
            return "anthropic"
        if self.openai_key:
            return "openai"
        return "ollama"

    def _check_ollama_installed(self):
        """Check if Ollama is installed."""
        try:
            result = subprocess.run(["which", "ollama"], capture_output=True, timeout=5)
            return result.returncode == 0
        except Exception:
            return False

    def _check_ollama_running(self):
        """Check if Ollama is running."""
        try:
            req = urllib.request.Request(
                "http://localhost:11434/api/tags",
                method="GET"
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                return True
        except Exception:
            return False

    def _check_ollama_model(self, model="mistral"):
        """Check if a model is downloaded."""
        try:
            result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
            return model in result.stdout
        except Exception:
            return False

    def _get_ollama_status(self):
        """Get Ollama status: 'not_installed', 'no_model', 'not_running', 'ready'."""
        if not self._check_ollama_installed():
            return "not_installed"
        if not self._check_ollama_model():
            return "no_model"
        if not self._check_ollama_running():
            return "not_running"
        return "ready"

    def _install_ollama(self):
        """Install Ollama."""
        if messagebox.askyesno("Install Ollama",
                "This will download and install Ollama (~500MB).\n\n"
                "Continue?", parent=self.top):
            self.status_label.config(text="Installing Ollama...", foreground="black")
            self.top.update()

            def install():
                try:
                    # Run the install script
                    result = subprocess.run(
                        ["bash", "-c", "curl -fsSL https://ollama.ai/install.sh | sh"],
                        capture_output=True, text=True, timeout=300
                    )
                    if result.returncode == 0:
                        self.top.after(0, lambda: self._on_ollama_installed())
                    else:
                        self.top.after(0, lambda: self._on_setup_error(f"Install failed: {result.stderr[:100]}"))
                except Exception as e:
                    self.top.after(0, lambda: self._on_setup_error(str(e)))

            threading.Thread(target=install, daemon=True).start()

    def _download_model(self):
        """Download the Ollama model."""
        self.status_label.config(text="Downloading model (~4GB)...", foreground="black")
        self.top.update()

        def download():
            try:
                result = subprocess.run(
                    ["ollama", "pull", "mistral"],
                    capture_output=True, text=True, timeout=600
                )
                if result.returncode == 0:
                    self.top.after(0, lambda: self._on_model_downloaded())
                else:
                    self.top.after(0, lambda: self._on_setup_error(f"Download failed: {result.stderr[:100]}"))
            except Exception as e:
                self.top.after(0, lambda: self._on_setup_error(str(e)))

        threading.Thread(target=download, daemon=True).start()

    def _start_ollama(self):
        """Start the Ollama server."""
        self.status_label.config(text="Starting Ollama...", foreground="black")
        self.top.update()

        def start():
            try:
                # Start ollama serve in background
                subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                # Wait a moment for it to start
                import time
                time.sleep(2)

                if self._check_ollama_running():
                    self.top.after(0, lambda: self._on_ollama_ready())
                else:
                    self.top.after(0, lambda: self._on_setup_error("Failed to start Ollama"))
            except Exception as e:
                self.top.after(0, lambda: self._on_setup_error(str(e)))

        threading.Thread(target=start, daemon=True).start()

    def _on_ollama_installed(self):
        """Called after Ollama is installed."""
        self.status_label.config(text="Installed! Downloading model...", foreground="green")
        self._download_model()

    def _on_model_downloaded(self):
        """Called after model is downloaded."""
        self.status_label.config(text="Model ready! Starting...", foreground="green")
        self._start_ollama()

    def _on_ollama_ready(self):
        """Called when Ollama is ready to use."""
        self.status_label.config(text="Ollama ready!", foreground="green")
        self._update_ollama_status()

    def _on_setup_error(self, error):
        """Called on setup error."""
        self.status_label.config(text=error[:50], foreground="red")
        self._update_ollama_status()

    def _create_widgets(self):
        main_frame = ttk.Frame(self.top, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Description input
        ttk.Label(main_frame, text="Describe what you want to match:").pack(anchor=tk.W)

        self.description_entry = ttk.Entry(main_frame, width=60)
        self.description_entry.pack(fill=tk.X, pady=(5, 10))
        self.description_entry.bind("<Return>", lambda e: self._generate())

        # Examples
        examples_text = "Examples: 'tables starting with user', 'contains order or invoice', 'ends with _log'"
        ttk.Label(main_frame, text=examples_text, foreground="gray").pack(anchor=tk.W)

        # Backend selector
        backend_frame = ttk.Frame(main_frame)
        backend_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(backend_frame, text="AI Backend:").pack(side=tk.LEFT)

        self.backend_var = tk.StringVar(value=self.backend)
        backends = ["claude", "anthropic", "openai", "ollama"]

        self.backend_combo = ttk.Combobox(backend_frame, textvariable=self.backend_var,
                                          values=backends, state="readonly", width=12)
        self.backend_combo.pack(side=tk.LEFT, padx=(5, 10))

        backend_hint = {"claude": "(CLI)", "anthropic": "(API)", "openai": "(GPT)", "ollama": "(Local)"}
        self.backend_hint_label = ttk.Label(backend_frame, text=backend_hint.get(self.backend, ""), foreground="gray")
        self.backend_hint_label.pack(side=tk.LEFT)
        self.backend_combo.bind("<<ComboboxSelected>>", self._on_backend_change)

        # API Key input (for web backends)
        self.key_frame = ttk.Frame(main_frame)
        self.key_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Label(self.key_frame, text="API Key:").pack(side=tk.LEFT)
        self.api_key_var = tk.StringVar(value=self.anthropic_key or self.openai_key or "")
        self.api_key_entry = ttk.Entry(self.key_frame, textvariable=self.api_key_var, width=40, show="*")
        self.api_key_entry.pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)

        # Ollama setup frame (for local backend)
        self.ollama_frame = ttk.Frame(main_frame)
        self.ollama_frame.pack(fill=tk.X, pady=(5, 0))
        self.ollama_status_label = ttk.Label(self.ollama_frame, text="")
        self.ollama_status_label.pack(side=tk.LEFT)
        self.ollama_setup_btn = ttk.Button(self.ollama_frame, text="Setup", command=self._setup_ollama)
        self.ollama_setup_btn.pack(side=tk.LEFT, padx=(10, 0))

        self._update_backend_ui()

        # Generate button
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)

        self.generate_btn = ttk.Button(btn_frame, text="Generate", command=self._generate)
        self.generate_btn.pack(side=tk.LEFT)

        self.status_label = ttk.Label(btn_frame, text="")
        self.status_label.pack(side=tk.LEFT, padx=10)

        # Result display
        ttk.Label(main_frame, text="Generated regex:").pack(anchor=tk.W, pady=(10, 5))

        result_frame = ttk.Frame(main_frame)
        result_frame.pack(fill=tk.X)

        self.result_var = tk.StringVar()
        self.result_entry = ttk.Entry(result_frame, textvariable=self.result_var, width=50, font=("monospace", 11))
        self.result_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Button(result_frame, text="Copy", width=6, command=self._copy).pack(side=tk.LEFT, padx=(5, 0))

        # Bottom buttons
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X, pady=(20, 0))

        ttk.Button(bottom_frame, text="Use", command=self._use).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(bottom_frame, text="Close", command=self.top.destroy).pack(side=tk.RIGHT)

    def _on_backend_change(self, event=None):
        """Handle backend selection change."""
        backend = self.backend_var.get()
        hint = {"claude": "(CLI)", "anthropic": "(API)", "openai": "(GPT)", "ollama": "(Local)"}
        self.backend_hint_label.config(text=hint.get(backend, ""))
        self._update_backend_ui()

    def _update_backend_ui(self):
        """Show/hide API key or Ollama setup based on backend."""
        backend = self.backend_var.get()
        if backend == "claude":
            # Claude CLI needs no setup
            self.key_frame.pack_forget()
            self.ollama_frame.pack_forget()
        elif backend == "ollama":
            self.key_frame.pack_forget()
            self.ollama_frame.pack(fill=tk.X, pady=(5, 0), after=self.backend_combo.master)
            self._update_ollama_status()
        else:
            self.ollama_frame.pack_forget()
            self.key_frame.pack(fill=tk.X, pady=(5, 0), after=self.backend_combo.master)

    def _update_ollama_status(self):
        """Update Ollama status display."""
        status = self._get_ollama_status()
        status_text = {
            "not_installed": "Not installed",
            "no_model": "Model not downloaded",
            "not_running": "Not running",
            "ready": "Ready"
        }
        status_color = "green" if status == "ready" else "orange"
        self.ollama_status_label.config(text=status_text.get(status, ""), foreground=status_color)

        # Update button text and visibility
        if status == "ready":
            self.ollama_setup_btn.pack_forget()
        else:
            btn_text = {
                "not_installed": "Install Ollama",
                "no_model": "Download Model",
                "not_running": "Start Ollama"
            }
            self.ollama_setup_btn.config(text=btn_text.get(status, "Setup"))
            self.ollama_setup_btn.pack(side=tk.LEFT, padx=(10, 0))

    def _setup_ollama(self):
        """Handle Ollama setup based on current status."""
        status = self._get_ollama_status()
        if status == "not_installed":
            self._install_ollama()
        elif status == "no_model":
            self._download_model()
        elif status == "not_running":
            self._start_ollama()

    def _generate(self):
        """Generate regex from description using selected AI backend."""
        description = self.description_entry.get().strip()
        if not description:
            self.status_label.config(text="Enter a description", foreground="red")
            return

        self.generate_btn.config(state=tk.DISABLED)
        self.status_label.config(text="Generating...", foreground="black")
        self.result_var.set("")

        backend = self.backend_var.get()

        # Run in background thread
        thread = threading.Thread(target=self._call_ai, args=(description, backend), daemon=True)
        thread.start()

    def _call_ai(self, description, backend):
        """Call the selected AI backend."""
        try:
            # Get API key from entry field
            api_key = self.api_key_var.get().strip()

            if backend == "claude":
                regex = self._call_claude_cli(description)
            elif backend == "anthropic":
                if not api_key:
                    raise Exception("API key required for Anthropic")
                regex = self._call_anthropic(description, api_key)
            elif backend == "openai":
                if not api_key:
                    raise Exception("API key required for OpenAI")
                regex = self._call_openai(description, api_key)
            else:
                regex = self._call_ollama(description)

            self.top.after(0, lambda: self._on_result(regex))
        except Exception as e:
            self.top.after(0, lambda: self._on_error(str(e)))

    def _clean_regex(self, regex):
        """Clean up the regex response."""
        regex = regex.strip()
        regex = regex.strip("`").strip('"').strip("'").strip()
        # Remove markdown code block markers
        if regex.startswith("```"):
            regex = regex.split("\n", 1)[-1]
        if regex.endswith("```"):
            regex = regex.rsplit("```", 1)[0]
        regex = regex.strip()
        # Take first line if multiple
        if "\n" in regex:
            regex = regex.split("\n")[0].strip()
        return regex

    def _call_claude_cli(self, description):
        """Call Claude CLI in print mode."""
        prompt = f"{self.SYSTEM_PROMPT}\n\nUser request: {description}"

        try:
            result = subprocess.run(
                ["claude", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                raise Exception(f"Claude CLI error: {result.stderr[:100]}")

            return self._clean_regex(result.stdout)

        except subprocess.TimeoutExpired:
            raise Exception("Claude CLI timed out")
        except FileNotFoundError:
            raise Exception("Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code")

    def _call_anthropic(self, description, api_key):
        """Call Anthropic Claude API."""
        payload = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 100,
            "messages": [
                {"role": "user", "content": f"{self.SYSTEM_PROMPT}\n\nUser request: {description}"}
            ]
        }

        req = urllib.request.Request(
            self.ANTHROPIC_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            }
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            regex = result["content"][0]["text"]
            return self._clean_regex(regex)

    def _call_openai(self, description, api_key):
        """Call OpenAI API."""
        payload = {
            "model": "gpt-4o-mini",
            "max_tokens": 100,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": description}
            ]
        }

        req = urllib.request.Request(
            self.OPENAI_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            regex = result["choices"][0]["message"]["content"]
            return self._clean_regex(regex)

    def _call_ollama(self, description):
        """Call Ollama API."""
        prompt = f"{self.SYSTEM_PROMPT}\n\nUser request: {description}\n\nRegex pattern:"

        payload = {
            "model": "mistral",
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 100
            }
        }

        try:
            req = urllib.request.Request(
                self.OLLAMA_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )

            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
                regex = result.get("response", "")
                return self._clean_regex(regex)

        except urllib.error.URLError:
            raise Exception("Ollama not running. Run: make ollama-start")

    def _on_result(self, regex):
        """Handle successful result."""
        self.generate_btn.config(state=tk.NORMAL)
        self.status_label.config(text="Done", foreground="green")
        self.result_var.set(regex)
        self.result_entry.select_range(0, tk.END)

    def _on_error(self, error):
        """Handle error."""
        self.generate_btn.config(state=tk.NORMAL)
        self.status_label.config(text=error[:50], foreground="red")

    def _copy(self):
        """Copy result to clipboard."""
        regex = self.result_var.get()
        if regex:
            self.top.clipboard_clear()
            self.top.clipboard_append(regex)
            self.status_label.config(text="Copied!", foreground="green")

    def _use(self):
        """Use the generated regex."""
        regex = self.result_var.get()
        if regex and self.callback:
            self.callback(regex)
        self.top.destroy()
