"""
AI Regex Builder Dialog for SQLBench PyQt6 GUI.

Provides interface for generating regex patterns using AI.
"""

import os
import subprocess
import shutil
from typing import Optional
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QWidget,
    QLineEdit,
    QComboBox,
    QPushButton,
    QLabel,
    QGroupBox,
    QTextEdit,
)


class GenerateWorker(QThread):
    """Background thread for AI regex generation."""

    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    SYSTEM_PROMPT = """You are a regex pattern generator. Generate ONLY a regex pattern, nothing else.
Rules:
- Output ONLY the regex pattern, no explanation, no markdown, no quotes
- Pattern should work with Python's re.search()
- Use (?i) for case-insensitive matching if appropriate
- For "starts with X", use ^X
- For "ends with X", use X$
- For "contains X", just use X
"""

    def __init__(self, backend: str, description: str, api_key: str = ""):
        super().__init__()
        self.backend = backend
        self.description = description
        self.api_key = api_key

    def run(self) -> None:
        """Generate regex in background."""
        try:
            if self.backend == "claude":
                result = self._generate_claude_cli()
            elif self.backend == "anthropic":
                result = self._generate_anthropic()
            elif self.backend == "openai":
                result = self._generate_openai()
            elif self.backend == "ollama":
                result = self._generate_ollama()
            else:
                raise ValueError(f"Unknown backend: {self.backend}")

            # Clean up result
            result = result.strip().strip('"\'`')
            self.finished.emit(result)

        except Exception as e:
            self.error.emit(str(e))

    def _generate_claude_cli(self) -> str:
        """Generate using Claude CLI."""
        prompt = f"{self.SYSTEM_PROMPT}\n\nGenerate regex for: {self.description}"
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr)
        return result.stdout.strip()

    def _generate_anthropic(self) -> str:
        """Generate using Anthropic API."""
        import anthropic
        client = anthropic.Anthropic(api_key=self.api_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            system=self.SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": f"Generate regex for: {self.description}"}
            ]
        )
        return message.content[0].text.strip()

    def _generate_openai(self) -> str:
        """Generate using OpenAI API."""
        import openai
        client = openai.OpenAI(api_key=self.api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=100,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": f"Generate regex for: {self.description}"}
            ]
        )
        return response.choices[0].message.content.strip()

    def _generate_ollama(self) -> str:
        """Generate using Ollama (local)."""
        import requests
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "mistral",
                "prompt": f"{self.SYSTEM_PROMPT}\n\nGenerate regex for: {self.description}",
                "stream": False,
                "options": {"temperature": 0.1}
            },
            timeout=60
        )
        response.raise_for_status()
        return response.json()["response"].strip()


class RegexBuilderDialog(QDialog):
    """Dialog for AI-powered regex generation."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.setWindowTitle("AI Regex Builder")
        self.setMinimumWidth(500)
        self.setModal(True)

        self._regex = ""
        self._worker: Optional[GenerateWorker] = None

        self._setup_ui()
        self._detect_backends()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Description input
        desc_group = QGroupBox("Describe what you want to match")
        desc_layout = QVBoxLayout(desc_group)

        self.txt_description = QLineEdit()
        self.txt_description.setPlaceholderText(
            "e.g., 'tables starting with CUST' or 'names containing ORDER'"
        )
        self.txt_description.returnPressed.connect(self._generate)
        desc_layout.addWidget(self.txt_description)

        examples = QLabel(
            "Examples: 'starts with INV', 'ends with _HIST', "
            "'contains CUSTOMER or ORDER'"
        )
        examples.setProperty("subheading", True)
        examples.setWordWrap(True)
        desc_layout.addWidget(examples)

        layout.addWidget(desc_group)

        # Backend selection
        backend_group = QGroupBox("AI Backend")
        backend_layout = QFormLayout(backend_group)

        self.cmb_backend = QComboBox()
        self.cmb_backend.addItem("Claude CLI", "claude")
        self.cmb_backend.addItem("Anthropic API", "anthropic")
        self.cmb_backend.addItem("OpenAI API", "openai")
        self.cmb_backend.addItem("Ollama (Local)", "ollama")
        self.cmb_backend.currentIndexChanged.connect(self._on_backend_changed)
        backend_layout.addRow("Backend:", self.cmb_backend)

        self.txt_api_key = QLineEdit()
        self.txt_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_api_key.setPlaceholderText("API key (if required)")
        backend_layout.addRow("API Key:", self.txt_api_key)

        self.lbl_backend_status = QLabel("")
        self.lbl_backend_status.setProperty("subheading", True)
        backend_layout.addRow("", self.lbl_backend_status)

        layout.addWidget(backend_group)

        # Generate button
        self.btn_generate = QPushButton("Generate Regex")
        self.btn_generate.setProperty("primary", True)
        self.btn_generate.clicked.connect(self._generate)
        layout.addWidget(self.btn_generate)

        # Result
        result_group = QGroupBox("Generated Regex")
        result_layout = QHBoxLayout(result_group)

        self.txt_result = QLineEdit()
        self.txt_result.setReadOnly(True)
        self.txt_result.setPlaceholderText("Regex will appear here...")
        result_layout.addWidget(self.txt_result)

        self.btn_copy = QPushButton("Copy")
        self.btn_copy.clicked.connect(self._copy_result)
        result_layout.addWidget(self.btn_copy)

        layout.addWidget(result_group)

        # Dialog buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_use = QPushButton("Use")
        self.btn_use.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_use)

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    def _detect_backends(self) -> None:
        """Detect available AI backends."""
        # Check Claude CLI
        if shutil.which("claude"):
            self.cmb_backend.setCurrentIndex(0)
            self.lbl_backend_status.setText("Claude CLI detected")
            self.txt_api_key.setVisible(False)
            return

        # Check for API keys
        anthropic_key = self._find_api_key("anthropic")
        if anthropic_key:
            self.cmb_backend.setCurrentIndex(1)
            self.txt_api_key.setText(anthropic_key)
            self.lbl_backend_status.setText("Anthropic API key found")
            return

        openai_key = self._find_api_key("openai")
        if openai_key:
            self.cmb_backend.setCurrentIndex(2)
            self.txt_api_key.setText(openai_key)
            self.lbl_backend_status.setText("OpenAI API key found")
            return

        # Default to Ollama
        self.cmb_backend.setCurrentIndex(3)
        self.txt_api_key.setVisible(False)
        self.lbl_backend_status.setText("Using local Ollama")

    def _find_api_key(self, provider: str) -> str:
        """Find API key for provider."""
        # Check environment
        env_var = f"{provider.upper()}_API_KEY"
        key = os.environ.get(env_var, "")
        if key:
            return key

        # Check config files
        config_paths = [
            os.path.expanduser(f"~/.{provider}/key"),
            os.path.expanduser(f"~/.config/{provider}/key"),
        ]
        for path in config_paths:
            if os.path.exists(path):
                try:
                    with open(path) as f:
                        return f.read().strip()
                except Exception:
                    pass

        return ""

    def _on_backend_changed(self) -> None:
        """Handle backend selection change."""
        backend = self.cmb_backend.currentData()

        # Show/hide API key field
        needs_key = backend in ("anthropic", "openai")
        self.txt_api_key.setVisible(needs_key)

        # Update status
        if backend == "claude":
            if shutil.which("claude"):
                self.lbl_backend_status.setText("Claude CLI available")
            else:
                self.lbl_backend_status.setText("Claude CLI not found")
        elif backend == "ollama":
            self.lbl_backend_status.setText("Requires Ollama running locally")
        else:
            self.lbl_backend_status.setText("")

    def _generate(self) -> None:
        """Generate regex pattern."""
        description = self.txt_description.text().strip()
        if not description:
            return

        backend = self.cmb_backend.currentData()
        api_key = self.txt_api_key.text()

        # Validate
        if backend in ("anthropic", "openai") and not api_key:
            self.lbl_backend_status.setText("API key required")
            return

        # Start generation
        self.btn_generate.setEnabled(False)
        self.btn_generate.setText("Generating...")
        self.lbl_backend_status.setText("Working...")

        self._worker = GenerateWorker(backend, description, api_key)
        self._worker.finished.connect(self._on_generated)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_generated(self, regex: str) -> None:
        """Handle successful generation."""
        self._regex = regex
        self.txt_result.setText(regex)
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("Generate Regex")
        self.lbl_backend_status.setText("Done!")

    def _on_error(self, error: str) -> None:
        """Handle generation error."""
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("Generate Regex")
        self.lbl_backend_status.setText(f"Error: {error[:50]}")

    def _copy_result(self) -> None:
        """Copy result to clipboard."""
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.txt_result.text())

    def get_regex(self) -> str:
        """Get the generated regex."""
        return self.txt_result.text()
