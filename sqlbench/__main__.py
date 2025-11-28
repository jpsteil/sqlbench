"""Entry point for sqlbench."""

import sys


def main():
    """Main entry point with argument handling."""
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()

        if arg in ("--install-launcher", "--create-launcher"):
            from sqlbench.launcher import create_launcher
            success = create_launcher()
            sys.exit(0 if success else 1)

        elif arg in ("--remove-launcher", "--uninstall-launcher"):
            from sqlbench.launcher import remove_launcher
            success = remove_launcher()
            sys.exit(0 if success else 1)

        elif arg in ("--help", "-h"):
            print("SQLBench - Multi-database SQL Workbench")
            print()
            print("Usage: sqlbench [options]")
            print()
            print("Options:")
            print("  --install-launcher   Create a desktop launcher for this OS")
            print("  --remove-launcher    Remove the desktop launcher")
            print("  --help, -h           Show this help message")
            print()
            print("Run without arguments to start the application.")
            sys.exit(0)

    # Start the GUI application
    from sqlbench.app import main as app_main
    app_main()


if __name__ == "__main__":
    main()
