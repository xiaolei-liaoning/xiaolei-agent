#!/usr/bin/env python3
"""屏幕图像识别与点击位置查找模块

功能：
- 屏幕截图
- 图像模板匹配查找位置
- OCR文字识别与位置查找
- 多目标查找与最近位置计算
"""

import subprocess
import os
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Union
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ClickPosition:
    """点击位置"""
    x: int
    y: int
    confidence: float = 1.0
    text: Optional[str] = None
    region: Optional[Tuple[int, int, int, int]] = None


@dataclass
class ScreenRegion:
    """屏幕区域 (x, y, width, height)"""
    x: int
    y: int
    width: int
    height: int


class ScreenLocator:
    """屏幕定位器 - 查找屏幕上的元素位置"""
    
    def __init__(self, screenshot_dir: str = None):
        self.screenshot_dir = screenshot_dir or "/tmp"
        self._last_screenshot = None
    
    def capture_screen(self, region: ScreenRegion = None, save: bool = True) -> str:
        """截取屏幕
        
        Args:
            region: 截取区域，None表示全屏
            save: 是否保存到文件
            
        Returns:
            截图文件路径
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"screen_capture_{timestamp}.png"
        filepath = os.path.join(self.screenshot_dir, filename)
        
        cmd = ['screencapture', '-x']
        
        if region:
            # 截取指定区域: -R x,y,width,height
            cmd.extend(['-R', f'{region.x},{region.y},{region.width},{region.height}'])
        
        cmd.append(filepath)
        
        try:
            subprocess.run(cmd, check=True, timeout=10)
            self._last_screenshot = filepath
            logger.info(f"屏幕截图已保存: {filepath}")
            return filepath
        except subprocess.CalledProcessError as e:
            logger.error(f"截图失败: {e}")
            raise
    
    def capture_and_locate(self, target: str, method: str = "ocr") -> Optional[ClickPosition]:
        """截屏并查找目标位置
        
        Args:
            target: 查找的目标（文字或图像路径）
            method: 查找方法 "ocr" 或 "template"
            
        Returns:
            点击位置，未找到返回None
        """
        screenshot_path = self.capture_screen()
        return self.locate_on_screen(screenshot_path, target, method)
    
    def locate_on_screen(self, image_path: str, target: str, method: str = "ocr") -> Optional[ClickPosition]:
        """在图像上查找目标位置
        
        Args:
            image_path: 图像路径
            target: 查找目标（文字或模板图像路径）
            method: 查找方法
            
        Returns:
            点击位置
        """
        if method == "ocr":
            return self._locate_by_ocr(image_path, target)
        elif method == "template":
            return self._locate_by_template(image_path, target)
        else:
            raise ValueError(f"不支持的查找方法: {method}")
    
    def _locate_by_ocr(self, image_path: str, text: str) -> Optional[ClickPosition]:
        """通过OCR查找文字位置
        
        Args:
            image_path: 图像路径
            text: 要查找的文字
            
        Returns:
            文字位置
        """
        try:
            import pytesseract
            from PIL import Image
            
            img = Image.open(image_path)
            
            # 执行OCR
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            
            # 查找匹配的文字
            texts = data.get('text', [])
            confs = data.get('conf', [])
            
            for i, (t, conf) in enumerate(zip(texts, confs)):
                if text.lower() in t.lower() and conf > 30:
                    # 找到匹配，返回中心点
                    x = data['left'][i]
                    y = data['top'][i]
                    w = data['width'][i]
                    h = data['height'][i]
                    
                    center_x = x + w // 2
                    center_y = y + h // 2
                    
                    logger.info(f"找到文字 '{text}' 位置: ({center_x}, {center_y})")
                    
                    return ClickPosition(
                        x=center_x,
                        y=center_y,
                        confidence=conf / 100.0,
                        text=t,
                        region=(x, y, w, h)
                    )
            
            logger.warning(f"未找到文字: {text}")
            return None
            
        except ImportError:
            logger.warning("pytesseract 未安装，使用备用方法")
            return self._locate_by_accessibility(image_path, text)
        except Exception as e:
            logger.error(f"OCR识别失败: {e}")
            return None
    
    def _locate_by_accessibility(self, image_path: str, text: str) -> Optional[ClickPosition]:
        """通过macOS辅助功能查找文字位置
        
        Args:
            image_path: 图像路径
            text: 要查找的文字
            
        Returns:
            文字位置
        """
        try:
            script = f'''
            tell application "System Events"
                tell process "Finder"
                    set frontmost to true
                    -- 尝试通过UI元素查找
                    try
                        set uiElems to every UI element
                        repeat with uiElem in uiElems
                            if description of uiElem contains "{text}" then
                                set elemPos to position of uiElem
                                set elemSize to size of uiElem
                                return (item 1 of elemPos) & "," & (item 2 of elemPos) & "," & (item 1 of elemSize) & "," & (item 2 of elemSize)
                            end if
                        end repeat
                    end try
                end tell
            end tell
            return "NOT_FOUND"
            '''
            
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            output = result.stdout.strip()
            if output and output != "NOT_FOUND":
                parts = output.split(',')
                if len(parts) == 4:
                    x, y, w, h = map(int, parts)
                    center_x = x + w // 2
                    center_y = y + h // 2
                    
                    logger.info(f"通过辅助功能找到 '{text}' 位置: ({center_x}, {center_y})")
                    
                    return ClickPosition(
                        x=center_x,
                        y=center_y,
                        confidence=0.8,
                        text=text,
                        region=(x, y, w, h)
                    )
            
            return None
            
        except Exception as e:
            logger.error(f"辅助功能查找失败: {e}")
            return None
    
    def _locate_by_template(self, image_path: str, template_path: str) -> Optional[ClickPosition]:
        """通过模板匹配查找图像位置
        
        Args:
            image_path: 截图路径
            template_path: 模板图像路径
            
        Returns:
            匹配位置
        """
        try:
            import cv2
            import numpy as np
            
            img = cv2.imread(image_path)
            template = cv2.imread(template_path)
            
            if img is None or template is None:
                logger.error("无法读取图像文件")
                return None
            
            # 模板匹配
            result = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            
            if max_val > 0.7:
                # 找到匹配，返回中心点
                h, w = template.shape[:2]
                center_x = max_loc[0] + w // 2
                center_y = max_loc[1] + h // 2
                
                logger.info(f"模板匹配成功，位置: ({center_x}, {center_y}), 置信度: {max_val}")
                
                return ClickPosition(
                    x=center_x,
                    y=center_y,
                    confidence=max_val,
                    region=(max_loc[0], max_loc[1], w, h)
                )
            
            logger.warning(f"模板匹配未找到，置信度: {max_val}")
            return None
            
        except ImportError:
            logger.warning("OpenCV 未安装，无法使用模板匹配")
            return None
        except Exception as e:
            logger.error(f"模板匹配失败: {e}")
            return None
    
    def find_all_matches(self, image_path: str, target: str, method: str = "ocr") -> List[ClickPosition]:
        """查找所有匹配位置
        
        Args:
            image_path: 图像路径
            target: 查找目标
            method: 查找方法
            
        Returns:
            所有匹配位置列表
        """
        matches = []
        
        try:
            if method == "ocr":
                import pytesseract
                from PIL import Image
                
                img = Image.open(image_path)
                data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
                
                texts = data.get('text', [])
                
                for i, t in enumerate(texts):
                    if target.lower() in t.lower():
                        x = data['left'][i]
                        y = data['top'][i]
                        w = data['width'][i]
                        h = data['height'][i]
                        conf = data['conf'][i]
                        
                        if conf > 30:
                            matches.append(ClickPosition(
                                x=x + w // 2,
                                y=y + h // 2,
                                confidence=conf / 100.0,
                                text=t,
                                region=(x, y, w, h)
                            ))
            
            logger.info(f"找到 {len(matches)} 个匹配")
            return matches
            
        except Exception as e:
            logger.error(f"查找所有匹配失败: {e}")
            return matches
    
    def click_at_position(self, x: int, y: int, clicks: int = 1) -> Dict[str, Any]:
        """点击指定位置
        
        Args:
            x: X坐标
            y: Y坐标
            clicks: 点击次数
            
        Returns:
            操作结果
        """
        try:
            # 使用osascript模拟点击
            script = f'''
            tell application "System Events"
                set frontmost of first process whose frontmost is true to true
                do shell script "cliclick c:{x},{y}"
            end tell
            '''
            
            # 执行点击
            for _ in range(clicks):
                subprocess.run(
                    ['osascript', '-e', script],
                    check=True,
                    timeout=2
                )
                time.sleep(0.1)
            
            logger.info(f"点击位置: ({x}, {y}), 次数: {clicks}")
            return {
                'success': True,
                'action': 'click_at',
                'x': x,
                'y': y,
                'clicks': clicks,
                'reply': f'已点击位置 ({x}, {y})'
            }
            
        except Exception as e:
            logger.error(f"点击失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_screen_size(self) -> Tuple[int, int]:
        """获取屏幕尺寸
        
        Returns:
            (width, height)
        """
        try:
            script = '''
            tell application "System Events"
                set screenSize to size of first desktop
                return item 1 of screenSize & "," & item 2 of screenSize
            end tell
            '''
            
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            output = result.stdout.strip()
            if output and ',' in output:
                width, height = map(int, output.split(','))
                return (width, height)
            
            return (1920, 1080)
            
        except Exception as e:
            logger.warning(f"获取屏幕尺寸失败: {e}，使用默认值")
            return (1920, 1080)


# 全局单例
_screen_locator = None

def get_screen_locator() -> ScreenLocator:
    """获取屏幕定位器单例"""
    global _screen_locator
    if _screen_locator is None:
        _screen_locator = ScreenLocator()
    return _screen_locator


async def locate_and_click(target: str, method: str = "ocr", clicks: int = 1) -> Dict[str, Any]:
    """查找并点击（异步接口）
    
    Args:
        target: 查找目标
        method: 查找方法
        clicks: 点击次数
        
    Returns:
        操作结果
    """
    locator = get_screen_locator()
    
    # 截屏并查找
    position = locator.capture_and_locate(target, method)
    
    if position:
        return locator.click_at_position(position.x, position.y, clicks)
    else:
        return {
            'success': False,
            'error': f'未找到目标: {target}'
        }


if __name__ == "__main__":
    # 测试代码
    locator = ScreenLocator()
    
    print("=" * 50)
    print("🖥️  屏幕定位器测试")
    print("=" * 50)
    
    # 获取屏幕尺寸
    width, height = locator.get_screen_size()
    print(f"📐 屏幕尺寸: {width} x {height}")
    
    # 截取屏幕
    print("\n📸 截取屏幕...")
    screenshot = locator.capture_screen()
    print(f"   截图保存: {screenshot}")
    
    # 查找文字（示例）
    print("\n🔍 查找苹果菜单...")
    # position = locator.locate_on_screen(screenshot, "Apple")
    # if position:
    #     print(f"   找到位置: ({position.x}, {position.y})")
    #     print(f"   置信度: {position.confidence}")
    # else:
    #     print("   未找到")
    
    print("\n✅ 测试完成")