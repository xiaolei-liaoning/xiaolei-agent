"""OCR文字识别 - 委托给 data_analysis 模块处理"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class OCRRecognitionHandler:
    """OCR识别处理器"""

    async def handle(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from mcp._impl.data_analysis.handler import DataAnalysisHandler
            handler = DataAnalysisHandler()
            return await handler.aexecute(action="ocr", **params)
        except Exception as e:
            logger.error("OCR识别失败: %s", e)
            return {"success": False, "error": str(e)}


handler = OCRRecognitionHandler()
