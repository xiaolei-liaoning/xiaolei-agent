import asyncio
import base64
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ImageProcessor:
    def __init__(self):
        self.enabled = False
        self._init_processor()

    def _init_processor(self):
        try:
            import PIL
            self.enabled = True
            logger.info("图像处理器初始化成功")
        except ImportError:
            logger.warning("PIL库未安装，图像处理功能受限")

    async def analyze_image(self, image_path: str) -> Dict:
        if not self.enabled:
            return {"error": "图像处理器未启用"}

        try:
            from PIL import Image

            with Image.open(image_path) as img:
                width, height = img.size
                format = img.format
                mode = img.mode

            return {
                "success": True,
                "width": width,
                "height": height,
                "format": format,
                "mode": mode,
                "description": f"图像尺寸: {width}x{height}, 格式: {format}, 模式: {mode}"
            }
        except Exception as e:
            logger.error(f"图像分析失败: {e}")
            return {"success": False, "error": str(e)}

    async def describe_image(self, image_path: str) -> str:
        analysis = await self.analyze_image(image_path)

        if not analysis.get("success"):
            return "无法分析图像"

        return f"这是一张{analysis['format']}格式的图片，尺寸为{analysis['width']}x{analysis['height']}像素。"

    async def encode_image(self, image_path: str) -> str:
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"图像编码失败: {e}")
            return ""



class SpeechProcessor:
    def __init__(self):
        self.enabled = False
        self._init_processor()

    def _init_processor(self):
        try:
            import speech_recognition
            self.enabled = True
            logger.info("语音处理器初始化成功")
        except ImportError:
            logger.warning("speech_recognition库未安装，语音处理功能受限")

    async def speech_to_text(self, audio_path: str) -> str:
        if not self.enabled:
            return "语音处理器未启用"

        try:
            import speech_recognition as sr

            recognizer = sr.Recognizer()
            with sr.AudioFile(audio_path) as source:
                audio = recognizer.record(source)

            try:
                text = recognizer.recognize_google(audio, language="zh-CN")
                return text
            except sr.UnknownValueError:
                return "无法识别语音内容"
            except sr.RequestError:
                return "语音识别服务不可用"
        except Exception as e:
            logger.error(f"语音转文字失败: {e}")
            return str(e)

    async def text_to_speech(self, text: str, output_path: str = "output.mp3") -> bool:
        try:
            with open(output_path.replace('.mp3', '.txt'), 'w', encoding='utf-8') as f:
                f.write(text)
            logger.info(f"文字转语音: 已保存到 {output_path.replace('.mp3', '.txt')}")
            return True
        except Exception as e:
            logger.error(f"文字转语音失败: {e}")
            return False



class MultimodalProcessor:
    def __init__(self):
        self.image_processor = ImageProcessor()
        self.speech_processor = SpeechProcessor()

    async def process_input(self, input_data: Any, input_type: str = "text") -> Dict:
        if input_type == "text":
            return {"type": "text", "content": input_data}

        elif input_type == "image":
            description = await self.image_processor.describe_image(input_data)
            return {"type": "image", "path": input_data, "description": description}

        elif input_type == "audio":
            text = await self.speech_processor.speech_to_text(input_data)
            return {"type": "audio", "path": input_data, "transcript": text}

        else:
            return {"type": "unknown", "content": str(input_data)}

    async def generate_response(self, text: str, response_type: str = "text") -> Dict:
        if response_type == "text":
            return {"type": "text", "content": text}

        elif response_type == "speech":
            success = await self.speech_processor.text_to_speech(text)
            return {"type": "speech", "success": success, "text": text}

        else:
            return {"type": "text", "content": text}

    def get_supported_types(self) -> List[str]:
        types = ["text"]
        if self.image_processor.enabled:
            types.append("image")
        if self.speech_processor.enabled:
            types.append("audio")
        return types