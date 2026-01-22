"""Entry point for sqlbench."""

import sys


def check_pyqt():
    """Check if PyQt6 is available."""
    try:
        from PyQt6.QtWidgets import QApplication
        return True
    except ImportError:
        return False


def check_tkinter():
    """Check if tkinter is available and provide installation instructions if not."""
    try:
        import tkinter
        return True
    except ImportError:
        pass

    # Detect OS and provide appropriate instructions
    import platform
    system = platform.system().lower()

    print("Error: tkinter is not installed.")
    print()
    print("SQLBench requires tkinter for its graphical interface.")
    print()

    if system == "linux":
        # Try to detect the Linux distribution
        distro = ""
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("ID="):
                        distro = line.strip().split("=")[1].strip('"').lower()
                        break
                    if line.startswith("ID_LIKE="):
                        distro_like = line.strip().split("=")[1].strip('"').lower()
                        if not distro:
                            distro = distro_like
        except Exception:
            pass

        if distro in ("ubuntu", "debian", "pop", "mint", "elementary") or "debian" in distro or "ubuntu" in distro:
            print("To install on Debian/Ubuntu-based systems:")
            print("  sudo apt install python3-tk")
        elif distro in ("fedora", "rhel", "centos", "rocky", "alma") or "fedora" in distro or "rhel" in distro:
            print("To install on Fedora/RHEL-based systems:")
            print("  sudo dnf install python3-tkinter")
        elif distro in ("arch", "manjaro", "endeavouros") or "arch" in distro:
            print("To install on Arch-based systems:")
            print("  sudo pacman -S tk")
        elif distro in ("opensuse", "suse") or "suse" in distro:
            print("To install on openSUSE:")
            print("  sudo zypper install python3-tk")
        else:
            print("To install tkinter, use your distribution's package manager:")
            print("  Debian/Ubuntu: sudo apt install python3-tk")
            print("  Fedora/RHEL:   sudo dnf install python3-tkinter")
            print("  Arch Linux:    sudo pacman -S tk")
            print("  openSUSE:      sudo zypper install python3-tk")
    elif system == "darwin":
        print("To install on macOS:")
        print("  brew install python-tk")
        print()
        print("Or reinstall Python with tkinter support:")
        print("  brew reinstall python")
    elif system == "windows":
        print("On Windows, tkinter should be included with Python.")
        print("Try reinstalling Python and ensure 'tcl/tk and IDLE' is selected.")
    else:
        print("Please install tkinter for your operating system.")

    print()
    print("After installing, run sqlbench again.")
    return False


def run_pyqt():
    """Run the PyQt6 GUI."""
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QIcon
    import os

    from sqlbench.qt import MainWindow

    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("SQLBench")
    app.setOrganizationName("SQLBench")

    # Set application icon
    icon_path = os.path.join(os.path.dirname(__file__), "resources", "sqlbench.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


def run_tkinter():
    """Run the tkinter GUI."""
    from sqlbench.app import main as app_main
    app_main()


def main():
    """Main entry point with argument handling."""
    use_qt = False

    # Process arguments
    args = sys.argv[1:]
    remaining_args = []

    for arg in args:
        arg_lower = arg.lower()

        if arg_lower == "--qt":
            use_qt = True
        elif arg_lower == "--tk":
            use_qt = False
        elif arg_lower in ("--install-launcher", "--create-launcher"):
            from sqlbench.launcher import create_launcher
            success = create_launcher()
            sys.exit(0 if success else 1)
        elif arg_lower in ("--remove-launcher", "--uninstall-launcher"):
            from sqlbench.launcher import remove_launcher
            success = remove_launcher()
            sys.exit(0 if success else 1)
        elif arg_lower in ("--help", "-h"):
            print("SQLBench - Multi-database SQL Workbench")
            print()
            print("Usage: sqlbench [options]")
            print()
            print("Options:")
            print("  --qt                 Use PyQt6 interface (modern)")
            print("  --tk                 Use tkinter interface (classic)")
            print("  --install-launcher   Create a desktop launcher for this OS")
            print("  --remove-launcher    Remove the desktop launcher")
            print("  --help, -h           Show this help message")
            print()
            print("Run without arguments to start the application.")
            print()
            print("By default, uses tkinter. Use --qt for the new PyQt6 interface.")
            sys.exit(0)
        else:
            remaining_args.append(arg)

    # Update sys.argv for the GUI
    sys.argv = [sys.argv[0]] + remaining_args

    # Launch appropriate GUI
    if use_qt:
        if not check_pyqt():
            print("Error: PyQt6 is not installed.")
            print()
            print("To install PyQt6:")
            print("  pip install PyQt6")
            print()
            print("Or run with --tk to use the tkinter interface.")
            sys.exit(1)
        run_pyqt()
    else:
        if not check_tkinter():
            sys.exit(1)
        run_tkinter()


if __name__ == "__main__":
    main()
