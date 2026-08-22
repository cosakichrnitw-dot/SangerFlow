"""Prevent a third-party ``workflow`` hook from matching SangerFlow's package.

The contrib hook targets an unrelated PyPI distribution named ``workflow`` and
attempts to copy its package metadata. SangerFlow's local package has the same
module name but no such distribution. Its imports are discovered normally by
PyInstaller's analysis, so this intentionally empty local hook is the correct
packaging-only override.
"""
