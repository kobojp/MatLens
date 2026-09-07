"""Test-only frozen entry point simulating a 0.3.0 updater; never distribute."""
from desktop import updater

updater.VERSION = "0.3.0"

if __name__ == "__main__":
    raise SystemExit(updater.main())
