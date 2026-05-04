import pytest
import asyncio
from unittest.mock import Mock, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def mock_db_session():
    mock = Mock()
    mock.query.return_value.filter.return_value.first.return_value = None
    mock.add = Mock()
    mock.commit = Mock()
    mock.close = Mock()
    return mock

@pytest.fixture
def mock_llm_backend():
    mock = Mock()
    mock.generate_response.return_value = "Test response"
    mock.generate_stream.return_value = iter(["Test", "response"])
    return mock

@pytest.fixture
def mock_skill_dispatcher():
    mock = Mock()
    mock.dispatch.return_value = {"success": True, "result": "test result"}
    return mock

@pytest.fixture
def mock_request():
    mock = Mock()
    mock.method = "POST"
    mock.url.path = "/api/test"
    mock.headers = {}
    return mock