"""Unit tests for Enhanced Dual-Grounded Computer Use and Recorder."""

from pathlib import Path
from PIL import Image

from sentinel.computer_use.dual_grounding import ActionResolver
from sentinel.computer_use.recorder import ActionRecorder
from sentinel.computer_use.som import InteractiveElement, SetOfMarksAnnotator
from sentinel.core.config import TargetConfig


def test_som_image_annotation():
    img = Image.new("RGB", (300, 200), color="white")
    el = InteractiveElement(
        index=1,
        tag="button",
        element_id="submit-btn",
        selector="#submit-btn",
        role="button",
        text="Submit Order",
        bbox={"x": 50, "y": 60, "width": 80, "height": 30},
    )
    annotated = SetOfMarksAnnotator.annotate_image_bboxes(img, [el])
    assert annotated.size == (300, 200)
    assert el.center_point == (90, 75)


def test_action_resolver_badge_and_self_healing():
    el1 = InteractiveElement(index=1, tag="button", selector="#login-btn", text="Log In", bbox={"x": 10, "y": 20, "width": 40, "height": 20})
    el2 = InteractiveElement(index=2, tag="input", selector="input#email", text="Email Address", bbox={"x": 10, "y": 50, "width": 100, "height": 20})
    elements = [el1, el2]

    # 1. Resolve by badge index "1"
    act1 = ActionResolver.resolve({"type": "click", "target": 1}, elements)
    assert act1.action_type == "click"
    assert act1.target_index == 1
    assert act1.selector == "#login-btn"
    assert act1.x == 30 and act1.y == 30

    # 2. Resolve by selector
    act2 = ActionResolver.resolve({"type": "fill", "target": "input#email", "value": "test@domain.com"}, elements)
    assert act2.target_index == 2
    assert act2.value == "test@domain.com"

    # 3. Self-healing resolution (selector changed slightly or user typed "login")
    act3 = ActionResolver.resolve({"type": "click", "target": "Log In Button"}, elements)
    assert act3.is_self_healed is True
    assert act3.target_index == 1


def test_action_recorder_and_code_synthesis(tmp_path):
    recorder = ActionRecorder("Test Checkout Recording")

    el = InteractiveElement(index=1, tag="button", selector="#checkout-btn", bbox={"x": 100, "y": 150, "width": 50, "height": 20})
    act = ActionResolver.resolve({"type": "click", "target": 1}, [el])
    recorder.record(act)
    recorder.add_assertion("status_code == 200")

    # Compile TestCase
    tc = recorder.to_test_case()
    assert tc.target_type == "web"
    assert len(tc.steps) == 1
    assert tc.steps[0].action == "click"
    assert tc.steps[0].path == "#checkout-btn"
    assert "status_code == 200" in tc.expected.assertions

    # Export YAML
    yaml_file = tmp_path / "recorded_test.yaml"
    yaml_content = recorder.export_yaml(yaml_file)
    assert yaml_file.exists()
    assert "test_cases" in yaml_content

    # Export Python Playwright script
    py_file = tmp_path / "test_recorded.py"
    py_code = recorder.export_playwright_python(py_file)
    assert py_file.exists()
    assert 'page.locator("#checkout-btn").click()' in py_code


def test_agent_copilot_mode_approval_gate():
    import threading
    import time
    from unittest.mock import MagicMock
    from sentinel.computer_use.agent import ComputerUseQAAgent
    from sentinel.llm.provider import MockLLMProvider

    target_cfg = TargetConfig(name="test", target_type="web", base_url="http://localhost:8899")
    mock_llm = MockLLMProvider()
    mock_llm.generate = MagicMock(return_value='{"thought": "Click checkout", "action": "click", "target": 1}')

    events = []
    agent = ComputerUseQAAgent(
        target_config=target_cfg,
        goal="Test checkout flow",
        llm_provider=mock_llm,
        event_callback=lambda evt: events.append(evt),
        mode="copilot",
    )

    el = InteractiveElement(index=1, tag="button", selector="#checkout-btn", bbox={"x": 50, "y": 50, "width": 40, "height": 20})
    agent.adapter._ensure_browser = MagicMock()
    SetOfMarksAnnotator.annotate_playwright_page = MagicMock(return_value=(b"fake_png", [el]))
    agent.execute_single_action = MagicMock()

    def _approve_after_delay():
        time.sleep(0.05)
        agent.submit_copilot_decision("approve")

    th = threading.Thread(target=_approve_after_delay)
    th.start()

    res = agent.run_step(1)
    th.join()

    assert res["step"] == 1
    event_types = [e["type"] for e in events]
    assert "copilot_approval_requested" in event_types


def test_agent_copilot_mode_skip():
    import threading
    import time
    from unittest.mock import MagicMock
    from sentinel.computer_use.agent import ComputerUseQAAgent
    from sentinel.llm.provider import MockLLMProvider

    target_cfg = TargetConfig(name="test", target_type="web", base_url="http://localhost:8899")
    mock_llm = MockLLMProvider()
    mock_llm.generate = MagicMock(return_value='{"thought": "Risky operation", "action": "click", "target": 99}')

    events = []
    agent = ComputerUseQAAgent(
        target_config=target_cfg,
        goal="Test safety skip",
        llm_provider=mock_llm,
        event_callback=lambda evt: events.append(evt),
        mode="copilot",
    )

    el = InteractiveElement(index=99, tag="button", selector="#delete-btn", bbox={"x": 50, "y": 50, "width": 40, "height": 20})
    agent.adapter._ensure_browser = MagicMock()
    SetOfMarksAnnotator.annotate_playwright_page = MagicMock(return_value=(b"fake_png", [el]))
    agent.execute_single_action = MagicMock()

    def _skip_after_delay():
        time.sleep(0.05)
        agent.submit_copilot_decision("skip")

    th = threading.Thread(target=_skip_after_delay)
    th.start()

    res = agent.run_step(1)
    th.join()

    assert res.get("skipped") is True
    agent.execute_single_action.assert_not_called()
