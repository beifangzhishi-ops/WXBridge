"""Windows subprocess defaults for the headless read-only Reader chain."""

import subprocess


# Python API/Reader processes have no console. A console-subsystem child (for
# example git.exe) would otherwise create a transient visible CMD window.
NO_CONSOLE_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)
