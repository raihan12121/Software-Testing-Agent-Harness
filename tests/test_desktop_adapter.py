"""Unit tests for DesktopAdapter multi-OS platform architecture."""

import pytest

from sentinel.adapters.desktop_adapter.adapter import (
    DesktopAdapter,
    LinuxDesktopAdapter,
    MacOSDesktopAdapter,
    WindowsDesktopAdapter,
    get_desktop_adapter,
)
from sentinel.core.config import TargetConfig
from sentinel.core.schemas import TestStep


def test_desktop_adapter_discovery():
    config = TargetConfig(target_type="desktop", name="NotepadClone")
    adapter = DesktopAdapter(config)
    model = adapter.discover(config)

    assert model.target_type == "desktop"
    assert len(model.endpoints) >= 1
    assert model.endpoints[0]["path"] == "window://main_window"
    assert model.metadata["app_name"] == "NotepadClone"
    adapter.close()


def test_desktop_adapter_actions_and_artifact_capture():
    config = TargetConfig(target_type="desktop", name="EditorApp")
    adapter = DesktopAdapter(config)

    # 1. Type text into text area
    type_step = TestStep(action="type_text", path="edit_text_editor", body="Hello Sentinel!")
    type_obs = adapter.execute_action(type_step)
    assert type_obs.error is None
    assert type_obs.raw_result["status_code"] == 200
    assert type_obs.raw_result["state"]["text_edit_text_editor"] == "Hello Sentinel!"

    # 2. Click button
    click_step = TestStep(action="click_element", path="btn_file_new")
    click_obs = adapter.execute_action(click_step)
    assert click_obs.error is None
    assert click_obs.raw_result["state"]["last_clicked"] == "btn_file_new"
    assert len(click_obs.artifacts) == 1
    assert click_obs.artifacts[0].mime_type == "image/png"

    # 3. Read text back
    read_step = TestStep(action="read_text", path="edit_text_editor")
    read_obs = adapter.execute_action(read_step)
    assert read_obs.raw_result["text"] == "Hello Sentinel!"

    adapter.close()


def test_desktop_adapter_reset_state_isolation():
    """Verify R-EXEC-1: Desktop windows and states are cleared between tests."""
    config = TargetConfig(target_type="desktop", name="WindowApp")
    adapter = DesktopAdapter(config)

    adapter.execute_action(TestStep(action="click_element", path="btn_action"))
    assert adapter._active_window == "main_window"
    assert len(adapter._controls_state) > 0

    # Reset
    adapter.reset_state(config)
    assert adapter._active_window is None
    assert len(adapter._controls_state) == 0
    adapter.close()


def test_desktop_multi_os_factory_and_exceptions(monkeypatch):
    """Verify platform detection and honest NotImplementedError on un-implemented platforms (P2 item 10)."""
    # 1. Windows platform returns WindowsDesktopAdapter
    monkeypatch.setattr("sys.platform", "win32")
    win_adapter = get_desktop_adapter()
    assert isinstance(win_adapter, WindowsDesktopAdapter)

    # 2. Linux platform returns LinuxDesktopAdapter and raises NotImplementedError when real execution requested
    monkeypatch.setattr("sys.platform", "linux")
    linux_adapter = get_desktop_adapter()
    assert isinstance(linux_adapter, LinuxDesktopAdapter)
    with pytest.raises(NotImplementedError) as exc_linux:
        linux_adapter.discover(TargetConfig(target_type="desktop", name="LinuxApp"))
    assert "AT-SPI" in str(exc_linux.value)

    # 3. macOS platform returns MacOSDesktopAdapter and raises NotImplementedError
    monkeypatch.setattr("sys.platform", "darwin")
    mac_adapter = get_desktop_adapter()
    assert isinstance(mac_adapter, MacOSDesktopAdapter)
    with pytest.raises(NotImplementedError) as exc_mac:
        mac_adapter.execute_action(TestStep(action="click"))
    assert "pyobjc" in str(exc_mac.value)
