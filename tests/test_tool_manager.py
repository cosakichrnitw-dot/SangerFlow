"""Tests for optional external-tool management and the MAFFT adapter."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import SimpleNamespace
import unittest

from core.tool_manager import ToolInfo, ToolManager, ToolStatus
from tools.mafft_tool import (
    MAFFT_TOOL_NAME,
    MafftExecutableNotFoundError,
    build_mafft_command,
    detect_mafft,
    resolve_mafft_executable,
)


class ToolManagerTests(unittest.TestCase):
    def test_register_list_and_get_immutable_tool_info(self) -> None:
        manager = ToolManager()
        info = ToolInfo("IQ-TREE", status=ToolStatus.UNKNOWN, metadata={"future": True})
        manager.register_tool(info)

        self.assertEqual(manager.get_tool("IQ-TREE"), info)
        self.assertEqual(manager.list_tools(), (info,))
        with self.assertRaises(FrozenInstanceError):
            info.name = "changed"  # type: ignore[misc]
        with self.assertRaises(TypeError):
            info.metadata["future"] = False  # type: ignore[index]
        with self.assertRaisesRegex(ValueError, "already registered"):
            manager.register_tool(info)

    def test_detects_missing_and_available_mafft_using_mocked_adapter(self) -> None:
        missing = detect_mafft(which=lambda _name: None)
        self.assertEqual(missing.status, ToolStatus.MISSING)

        available = detect_mafft(
            which=lambda _name: "/opt/bin/mafft",
            runner=lambda *_args, **_kwargs: SimpleNamespace(
                returncode=0, stdout="v7.520", stderr=""
            ),
        )
        self.assertEqual(available.name, MAFFT_TOOL_NAME)
        self.assertEqual(available.status, ToolStatus.AVAILABLE)
        self.assertEqual(available.version, "v7.520")
        self.assertEqual(available.executable_path, "/opt/bin/mafft")

    def test_manager_runs_registered_detector_and_isolates_adapter_failures(self) -> None:
        manager = ToolManager()
        manager.register_tool(
            ToolInfo(MAFFT_TOOL_NAME),
            detector=lambda: ToolInfo(
                MAFFT_TOOL_NAME,
                version="7.520",
                executable_path="/opt/bin/mafft",
                status=ToolStatus.AVAILABLE,
            ),
        )
        manager.register_tool(ToolInfo("RAxML-NG"), detector=lambda: (_ for _ in ()).throw(RuntimeError("missing")))

        tools = manager.detect_tools()
        self.assertEqual(tools[0].status, ToolStatus.AVAILABLE)
        self.assertEqual(manager.get_tool("RAxML-NG").status, ToolStatus.INVALID)
        self.assertEqual(manager.get_tool("RAxML-NG").metadata["detection_error"], "missing")

    def test_mafft_command_generation_and_invalid_tool_lookup(self) -> None:
        self.assertEqual(
            build_mafft_command("/opt/bin/mafft"),
            ("/opt/bin/mafft", "--auto", "-"),
        )
        self.assertEqual(build_mafft_command("mafft", input_path="input.fasta", auto=False), ("mafft", "input.fasta"))
        with self.assertRaises(KeyError):
            ToolManager().get_tool("missing")

    def test_resolution_prefers_configured_path_then_native_path(self) -> None:
        self.assertEqual(
            resolve_mafft_executable(
                r"C:\Tools\mafft.bat",
                which=lambda value: r"C:\Tools\mafft.bat" if value.endswith(".bat") else None,
            ),
            r"C:\Tools\mafft.bat",
        )
        self.assertEqual(
            resolve_mafft_executable(None, which=lambda _value: "/usr/local/bin/mafft"),
            "/usr/local/bin/mafft",
        )
        with self.assertRaises(MafftExecutableNotFoundError):
            resolve_mafft_executable(None, which=lambda _value: None)


if __name__ == "__main__":
    unittest.main()
