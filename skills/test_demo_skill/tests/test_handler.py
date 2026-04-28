"""Tests for test_demo_skill"""

import pytest


@pytest.mark.asyncio
async def test_execute():
    """Test skill execution"""
    from skills.test_demo_skill.handler import handler
    
    result = await handler.execute()
    assert result['success'] is True
