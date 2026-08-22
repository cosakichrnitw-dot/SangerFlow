# SangerFlow v1.0 supported platforms

## Primary release targets

- macOS 13 or later on Apple Silicon (`arm64`)
- Windows 10/11 (`x86_64`)

Windows support is not claimed until Windows CI and a native smoke test have
completed for the release candidate.

## Best effort

- macOS 13 or later on Intel (`x86_64`)

macOS Intel builds are produced and validated separately from Apple Silicon.
They are not assumed to be universal binaries.

## External tools

MAFFT is a machine-local dependency. Its executable path is stored in the
user's Studio settings, never in Project data. A Project can therefore move
between platforms without inheriting an invalid executable path.
