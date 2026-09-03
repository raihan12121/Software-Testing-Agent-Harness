"""Unit tests for MobileAdapter (iOS & Android)."""

from unittest.mock import MagicMock

from sentinel.adapters.mobile_adapter.adapter import MobileAdapter
from sentinel.core.config import TargetConfig
from sentinel.core.schemas import TestStep


def test_mobile_adapter_discovery():
    config = TargetConfig(
        target_type="mobile",
        name="PilotApp",
        custom_options={"platformName": "Android", "appPackage": "com.sentinel.pilot"},
    )
    adapter = MobileAdapter(config)
    model = adapter.discover(config)

    assert model.target_type == "mobile"
    assert len(model.endpoints) >= 1
    assert model.endpoints[0]["path"] == "view://main_activity"
    assert model.metadata["platform"] == "Android"
    adapter.close()


def test_mobile_adapter_actions_and_artifact_capture():
    config = TargetConfig(target_type="mobile", name="TestApp")
    adapter = MobileAdapter(config)

    # 1. Fill username
    fill_step = TestStep(action="fill", path="input_username", body="tester_01")
    fill_obs = adapter.execute_action(fill_step)
    assert fill_obs.error is None
    assert fill_obs.raw_result["status_code"] == 200
    assert fill_obs.raw_result["state"]["text_input_username"] == "tester_01"

    # 2. Tap button
    tap_step = TestStep(action="tap", path="btn_login")
    tap_obs = adapter.execute_action(tap_step)
    assert tap_obs.error is None
    assert tap_obs.raw_result["state"]["last_tapped"] == "btn_login"
    assert len(tap_obs.artifacts) == 1
    assert tap_obs.artifacts[0].mime_type == "image/png"

    # 3. Swipe down
    swipe_step = TestStep(action="swipe", params={"direction": "down"})
    swipe_obs = adapter.execute_action(swipe_step)
    assert swipe_obs.raw_result["state"]["scroll_position"] == "down"

    adapter.close()


def test_mobile_adapter_session_reset_isolation():
    """Verify R-EXEC-1: Session state is reset cleanly between tests."""
    config = TargetConfig(target_type="mobile", name="ResetApp")
    adapter = MobileAdapter(config)

    adapter.execute_action(TestStep(action="tap", path="btn_checkout"))
    assert adapter._session_active is True
    assert "last_tapped" in adapter._current_state

    # Reset
    adapter.reset_state(config)
    assert adapter._session_active is False
    assert len(adapter._current_state) == 0
    adapter.close()


def test_mobile_adapter_appium_driver_integration():
    """Verify MobileAdapter introspects accessibility tree and dispatches actions through Appium driver."""
    config = TargetConfig(
        target_type="mobile",
        name="LiveApp",
        custom_options={"platformName": "Android", "appPackage": "com.example.app"},
    )
    adapter = MobileAdapter(config)

    # Mock real Appium remote driver
    mock_driver = MagicMock()
    mock_driver.page_source = """
    <hierarchy rotation="0">
        <android.widget.FrameLayout id="content">
            <android.widget.Button resource-id="com.example:id/submit_btn" text="Submit" clickable="true" />
            <android.widget.EditText resource-id="com.example:id/name_box" text="" />
        </android.widget.FrameLayout>
    </hierarchy>
    """
    mock_element = MagicMock()
    mock_driver.find_element.return_value = mock_element
    adapter._driver = mock_driver

    # 1. Discover introspects live XML hierarchy
    model = adapter.discover(config)
    assert model.metadata["live_appium"] is True
    discovered_elements = model.endpoints[0]["metadata"]["elements"]
    assert any("submit_btn" in el["id"] for el in discovered_elements)

    # 2. Execute tap on button
    tap_step = TestStep(action="tap", path="submit_btn")
    obs = adapter.execute_action(tap_step)
    assert obs.raw_result["status_code"] == 200
    mock_element.click.assert_called_once()

    # 3. Execute fill
    fill_step = TestStep(action="fill", path="name_box", body="Ada Lovelace")
    obs_fill = adapter.execute_action(fill_step)
    assert obs_fill.raw_result["status_code"] == 200
    mock_element.send_keys.assert_called_with("Ada Lovelace")

    # 4. Session teardown / terminate app (R-EXEC-1)
    adapter.reset_state(config)
    mock_driver.terminate_app.assert_called_with("com.example.app")

    adapter.close()
    mock_driver.quit.assert_called_once()
