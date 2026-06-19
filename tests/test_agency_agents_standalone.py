"""测试 Agency Agents 角色匹配系统（独立版本）"""
import os
import re

import yaml

CONFIG_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "core", "skills", "agency_agents", "agents_config.yaml"
))

def load_agents():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    agents = []
    for category, agents_list in config.items():
        if isinstance(agents_list, list):
            for agent in agents_list:
                agent["category"] = category
                agents.append(agent)
    return agents

def match(agents, task, top_k=3):
    task_lower = task.lower()
    scores = []
    for agent in agents:
        score = 0.0
        for kw in agent.get("keywords", []):
            if kw.lower() in task_lower:
                score += 1.0
        for pattern in agent.get("match_patterns", []):
            try:
                if re.search(pattern, task_lower):
                    score += 2.0
            except re.error:
                pass
        if score > 0:
            scores.append((score, agent))
    scores.sort(key=lambda x: x[0], reverse=True)
    return scores[:top_k]

if __name__ == "__main__":
    print("=" * 60)
    print("Agency Agents 角色匹配系统测试")
    print("=" * 60)
    
    agents = load_agents()
    print("已加载 %d 个专家角色\n" % len(agents))
    
    test_cases = [
        ("帮我设计一个高并发的后端系统", "后端架构"),
        ("写一篇小红书种草笔记", "小红书运营"),
        ("优化 React 前端性能", "前端开发"),
        ("搭建 CI/CD 流水线", "DevOps"),
        ("分析财务报表", "财务分析"),
        ("设计游戏关卡", "游戏设计"),
    ]
    
    for task, expected in test_cases:
        matched = match(agents, task, top_k=1)
        if matched:
            best = matched[0][1]
            print("OK 任务: %s" % task[:30])
            print("   匹配: %s %s (分数: %.1f)" % (best.get("emoji", "?"), best.get("name", "?"), matched[0][0]))
            print("   期望: %s\n" % expected)
        else:
            print("FAIL 任务: %s" % task[:30])
            print("   未匹配到角色\n")
    
    print("=" * 60)
    print("测试完成")
    print("=" * 60)    print("=" * 60)
    print("测试完成")
    print("=" * 60)