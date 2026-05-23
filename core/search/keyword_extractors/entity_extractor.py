"""实体提取器 - 从文本中提取人名、地名、时间、数字等实体"""

import logging
import re
from typing import List

from .base import ExtractedEntities

logger = logging.getLogger(__name__)


class EntityExtractor:
    """实体提取器"""

    # 常见城市/地点列表
    LOCATION_KEYWORDS = [
        '北京', '上海', '广州', '深圳', '杭州', '成都', '重庆',
        '南京', '武汉', '西安', '天津', '苏州', '青岛', '大连'
    ]

    # 时间表达式模式
    TIME_PATTERNS = [
        r'\d{4}年\d{1,2}月\d{1,2}日',
        r'\d{1,2}月\d{1,2}日',
        r'今天|明天|后天|昨天|前天',
        r'早上|上午|中午|下午|晚上|凌晨',
        r'\d{1,2}点\d{0,2}',
        r'本周|下周|上周|本月|下月|上月',
        r'今年|明年|去年'
    ]

    def extract(self, text: str) -> ExtractedEntities:
        """提取实体信息

        Args:
            text: 文本

        Returns:
            实体信息
        """
        entities = ExtractedEntities(
            persons=[],
            locations=[],
            times=[],
            numbers=[],
            organizations=[],
            urls=[],
            emails=[]
        )

        # 提取URL
        url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
        entities.urls = re.findall(url_pattern, text)

        # 提取邮箱
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        entities.emails = re.findall(email_pattern, text)

        # 提取数字（包括小数、百分比）
        number_pattern = r'\d+\.?\d*%?'
        entities.numbers = re.findall(number_pattern, text)

        # 提取时间表达式
        for pattern in self.TIME_PATTERNS:
            matches = re.findall(pattern, text)
            entities.times.extend(matches)

        # 提取地点
        for loc in self.LOCATION_KEYWORDS:
            if loc in text:
                entities.locations.append(loc)

        # 提取组织名（简化版，基于常见后缀）
        org_patterns = [
            r'[一-鿿]{2,10}(公司|集团|企业|学校|医院|银行)',
            r'[一-鿿]{2,10}(大学|学院|中学|小学)'
        ]
        for pattern in org_patterns:
            matches = re.findall(pattern, text)
            entities.organizations.extend(matches)

        return entities
