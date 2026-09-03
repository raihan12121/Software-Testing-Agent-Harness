"""Unit tests for Embedded & IoT Adapter with real protocols and safety enforcement."""

from sentinel.adapters.iot_adapter.adapter import IoTAdapter
from sentinel.core.config import TargetConfig
from sentinel.core.schemas import TestStep


def test_iot_adapter_discovery():
    config = TargetConfig(target_type="iot", name="TelemetryBroker")
    adapter = IoTAdapter(config)
    model = adapter.discover(config)

    assert model.target_type == "iot"
    assert len(model.endpoints) >= 3
    paths = [ep["path"] for ep in model.endpoints]
    assert "mqtt://sensors/temperature" in paths
    assert "serial://COM1" in paths
    adapter.close()


def test_iot_adapter_pub_sub_and_serial_execution():
    config = TargetConfig(target_type="iot", name="DeviceBroker")
    adapter = IoTAdapter(config)

    # 1. Publish message
    pub_step = TestStep(
        action="publish",
        path="sensors/temperature",
        body={"temperature": 23.8, "sensor_id": "temp_01"},
    )
    pub_obs = adapter.execute_action(pub_step)
    assert pub_obs.raw_result["delivered"] is True
    assert len(pub_obs.artifacts) == 1

    # 2. Subscribe and verify message payload
    sub_step = TestStep(action="subscribe", path="sensors/temperature")
    sub_obs = adapter.execute_action(sub_step)
    assert sub_obs.raw_result["message_count"] == 1
    assert sub_obs.raw_result["latest_message"]["temperature"] == 23.8

    # 3. Send serial command
    serial_step = TestStep(action="send_serial", body="AT+PING\r\n")
    serial_obs = adapter.execute_action(serial_step)
    assert serial_obs.raw_result["bytes_written"] > 0

    adapter.close()


def test_iot_adapter_real_serial_loopback():
    """Verify genuine pyserial loopback execution (P2 item 11)."""
    config = TargetConfig(
        target_type="iot",
        name="SerialLoopbackTarget",
        custom_options={"allowed_ports": ["loop://test_uart"]},
    )
    adapter = IoTAdapter(config)

    write_step = TestStep(
        action="send_serial",
        path="serial://loop://test_uart",
        body="AT+STATUS=OK\r\n",
    )
    write_obs = adapter.execute_action(write_step)
    assert write_obs.error is None
    assert write_obs.raw_result["bytes_written"] == len("AT+STATUS=OK\r\n")

    read_step = TestStep(action="read_serial", path="serial://loop://test_uart")
    read_obs = adapter.execute_action(read_step)
    assert read_obs.error is None
    assert "AT+STATUS=OK" in read_obs.raw_result["data"]

    adapter.close()


def test_iot_adapter_allowlist_security_enforcement():
    """Verify strict host and port allow-list security blocks per R-SAFE-5 (P2 item 11)."""
    # 1. Unlisted MQTT broker blocked
    mqtt_config = TargetConfig(
        target_type="iot",
        name="UntrustedBroker",
        base_url="mqtt://unauthorized-remote-broker.com:1883",
        allowed_hosts=["localhost", "127.0.0.1"],
    )
    adapter = IoTAdapter(mqtt_config)
    pub_step = TestStep(action="publish", path="sensors/co2", body={"co2": 400})
    obs = adapter.execute_action(pub_step)
    assert obs.error is not None
    assert "SECURITY_BLOCK" in obs.error
    assert "R-SAFE-5" in obs.error

    # 2. Unlisted serial port blocked
    serial_config = TargetConfig(
        target_type="iot",
        name="RestrictedSerial",
        custom_options={"allowed_ports": ["COM1", "COM2"]},
    )
    adapter_serial = IoTAdapter(serial_config)
    step_unauthorized_port = TestStep(action="send_serial", path="serial://COM99", body="test")
    obs_serial = adapter_serial.execute_action(step_unauthorized_port)
    assert obs_serial.error is not None
    assert "SECURITY_BLOCK" in obs_serial.error
    assert "R-SAFE-5" in obs_serial.error


def test_iot_adapter_reset_state():
    config = TargetConfig(target_type="iot", name="ResetBroker")
    adapter = IoTAdapter(config)

    adapter.execute_action(TestStep(action="publish", path="sensors/co2", body={"co2": 450}))
    assert len(adapter._topics) > 0

    adapter.reset_state(config)
    assert len(adapter._topics) == 0
    assert len(adapter._serial_buffer) == 0
    adapter.close()
