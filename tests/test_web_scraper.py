#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试所有爬虫功能
"""

import pytest
import asyncio
import os
from core.multi_agent_system import agent_scheduler

class TestWebScraper:
    """测试网页爬虫功能"""
    
    @pytest.mark.asyncio
    async def test_scraper_agent_initialization(self):
        """测试爬虫Agent初始化"""
        await agent_scheduler.start()
        
        # 检查爬虫Agent是否存在
        assert "SCRAPER" in [agent_type.value for agent_type in agent_scheduler.agents]
        
        await agent_scheduler.stop()
    
    @pytest.mark.asyncio
    async def test_bilibili_hot(self):
        """测试哔哩哔哩热门视频爬取"""
        await agent_scheduler.start()
        
        try:
            # 提交B站热门视频爬取任务
            result = await agent_scheduler.submit_task("scrape", {
                "type": "search",
                "query": "哔哩哔哩热门视频"
            })
            
            assert result is not None
            assert "task_id" in result
            assert "agent_type" in result
            assert result["agent_type"] == "SCRAPER"
            
            # 等待任务完成
            await asyncio.sleep(5)
            
            # 检查任务状态
            task = await agent_scheduler.get_task_status(result["task_id"])
            assert task is not None
            assert task.status == "completed"
        finally:
            await agent_scheduler.stop()
    
    @pytest.mark.asyncio
    async def test_baidu_hot(self):
        """测试百度热搜爬取"""
        await agent_scheduler.start()
        
        try:
            # 提交百度热搜爬取任务
            result = await agent_scheduler.submit_task("scrape", {
                "type": "search",
                "query": "百度热搜"
            })
            
            assert result is not None
            assert "task_id" in result
            assert "agent_type" in result
            assert result["agent_type"] == "SCRAPER"
            
            # 等待任务完成
            await asyncio.sleep(5)
            
            # 检查任务状态
            task = await agent_scheduler.get_task_status(result["task_id"])
            assert task is not None
            assert task.status == "completed"
        finally:
            await agent_scheduler.stop()
    
    @pytest.mark.asyncio
    async def test_weibo_hot(self):
        """测试微博热搜爬取"""
        await agent_scheduler.start()
        
        try:
            # 提交微博热搜爬取任务
            result = await agent_scheduler.submit_task("scrape", {
                "type": "search",
                "query": "微博热搜"
            })
            
            assert result is not None
            assert "task_id" in result
            assert "agent_type" in result
            assert result["agent_type"] == "SCRAPER"
            
            # 等待任务完成
            await asyncio.sleep(5)
            
            # 检查任务状态
            task = await agent_scheduler.get_task_status(result["task_id"])
            assert task is not None
            assert task.status == "completed"
        finally:
            await agent_scheduler.stop()
    
    @pytest.mark.asyncio
    async def test_zhihu_hot(self):
        """测试知乎热榜爬取"""
        await agent_scheduler.start()
        
        try:
            # 提交知乎热榜爬取任务
            result = await agent_scheduler.submit_task("scrape", {
                "type": "search",
                "query": "知乎热榜"
            })
            
            assert result is not None
            assert "task_id" in result
            assert "agent_type" in result
            assert result["agent_type"] == "SCRAPER"
            
            # 等待任务完成
            await asyncio.sleep(5)
            
            # 检查任务状态
            task = await agent_scheduler.get_task_status(result["task_id"])
            assert task is not None
            assert task.status == "completed"
        finally:
            await agent_scheduler.stop()
    
    @pytest.mark.asyncio
    async def test_douyin_hot(self):
        """测试抖音热榜爬取"""
        await agent_scheduler.start()
        
        try:
            # 提交抖音热榜爬取任务
            result = await agent_scheduler.submit_task("scrape", {
                "type": "search",
                "query": "抖音热榜"
            })
            
            assert result is not None
            assert "task_id" in result
            assert "agent_type" in result
            assert result["agent_type"] == "SCRAPER"
            
            # 等待任务完成
            await asyncio.sleep(5)
            
            # 检查任务状态
            task = await agent_scheduler.get_task_status(result["task_id"])
            assert task is not None
            assert task.status == "completed"
        finally:
            await agent_scheduler.stop()
    
    @pytest.mark.asyncio
    async def test_github_trending(self):
        """测试GitHub趋势爬取"""
        await agent_scheduler.start()
        
        try:
            # 提交GitHub趋势爬取任务
            result = await agent_scheduler.submit_task("scrape", {
                "type": "search",
                "query": "GitHub趋势"
            })
            
            assert result is not None
            assert "task_id" in result
            assert "agent_type" in result
            assert result["agent_type"] == "SCRAPER"
            
            # 等待任务完成
            await asyncio.sleep(5)
            
            # 检查任务状态
            task = await agent_scheduler.get_task_status(result["task_id"])
            assert task is not None
            assert task.status == "completed"
        finally:
            await agent_scheduler.stop()
    
    @pytest.mark.asyncio
    async def test_file_saving(self):
        """测试爬虫结果文件保存"""
        await agent_scheduler.start()
        
        try:
            # 提交B站热门视频爬取任务
            result = await agent_scheduler.submit_task("scrape", {
                "type": "search",
                "query": "哔哩哔哩热门视频"
            })
            
            # 等待任务完成
            await asyncio.sleep(5)
            
            # 检查桌面是否生成文件
            desktop_path = os.path.expanduser("~/Desktop")
            files = os.listdir(desktop_path)
            bilibili_files = [f for f in files if "bilibili" in f.lower() or "B站" in f]
            
            # 检查是否生成了文件
            assert len(bilibili_files) > 0
            
            # 检查是否生成了md文件
            md_files = [f for f in bilibili_files if f.endswith(".md")]
            assert len(md_files) > 0
            
        finally:
            await agent_scheduler.stop()

if __name__ == "__main__":
    # 运行所有测试
    asyncio.run(TestWebScraper().test_scraper_agent_initialization())
    asyncio.run(TestWebScraper().test_bilibili_hot())
    asyncio.run(TestWebScraper().test_baidu_hot())
    asyncio.run(TestWebScraper().test_weibo_hot())
    asyncio.run(TestWebScraper().test_zhihu_hot())
    asyncio.run(TestWebScraper().test_douyin_hot())
    asyncio.run(TestWebScraper().test_github_trending())
    asyncio.run(TestWebScraper().test_file_saving())