"""工作流管理 API"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflow", tags=["工作流"])


class CreateWorkflowRequest(BaseModel):
    """创建工作流请求"""
    xml_content: str
    name: Optional[str] = None


class ExecuteWorkflowRequest(BaseModel):
    """执行工作流请求"""
    workflow_id: str
    input_data: Dict[str, Any] = {}


class ExecuteWorkflowDataRequest(BaseModel):
    """直接执行工作流数据请求"""
    workflow: Dict[str, Any]
    input_data: Dict[str, Any] = {}


@router.post("/create")
async def create_workflow(req: CreateWorkflowRequest):
    """从XML创建工作流"""
    from skills.workflow_engine import workflow_engine
    
    result = workflow_engine.create_from_xml(req.xml_content)
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "创建失败"))
    
    return result


@router.post("/execute")
async def execute_workflow(req: ExecuteWorkflowRequest):
    """执行工作流"""
    from skills.workflow_engine import workflow_engine
    
    result = await workflow_engine.execute(req.workflow_id, req.input_data)
    
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "执行失败"))
    
    return result


@router.post("/execute-data")
async def execute_workflow_data(req: ExecuteWorkflowDataRequest):
    """直接执行工作流数据"""
    from skills.workflow_engine import WorkflowEngine
    
    try:
        # 创建临时工作流引擎实例
        engine = WorkflowEngine()
        
        # 为工作流生成临时ID
        import uuid
        workflow_id = f"temp_{uuid.uuid4().hex}"
        
        # 保存临时工作流
        engine.workflows[workflow_id] = req.workflow
        
        # 执行工作流
        result = await engine.execute(workflow_id, req.input_data)
        
        # 清理临时工作流
        if workflow_id in engine.workflows:
            del engine.workflows[workflow_id]
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "执行失败"))
        
        return result
    except Exception as e:
        logger.error(f"执行工作流数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_workflows():
    """列出所有工作流"""
    from skills.workflow_engine import workflow_engine
    
    return {"workflows": workflow_engine.list_workflows()}


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str):
    """删除工作流"""
    from skills.workflow_engine import workflow_engine
    
    result = workflow_engine.delete_workflow(workflow_id)
    
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "删除失败"))
    
    return result


class AIGenerateRequest(BaseModel):
    """AI生成工作流请求"""
    prompt: str


@router.post("/ai-generate")
async def ai_generate_workflow(req: AIGenerateRequest):
    """AI自动生成工作流（根据描述生成XML）"""
    try:
        from core.llm_backend import get_llm_router
        
        client = get_llm_router()
        
        prompt = req.prompt
        
        system_prompt = """你是一个工作流设计专家。根据用户需求，生成符合以下格式的XML工作流定义：

<workflow name="工作流名称" description="描述">
  <node id="start" type="start">
    <config>
      <input>用户输入</input>
    </config>
  </node>
  
  <node id="llm1" type="llm">
    <config>
      <prompt>你的提示词，使用{{variable}}引用变量</prompt>
      <model>gpt-4</model>
    </config>
  </node>
  
  <node id="tool1" type="tool">
    <config>
      <tool>工具名称(如web_scraper/weather)</tool>
      <params>
        <param1>{{variable}}</param1>
      </params>
    </config>
  </node>
  
  <node id="end" type="end">
    <config>
      <output>最终输出模板</output>
    </config>
  </node>
  
  <edge source="start" target="llm1"/>
  <edge source="llm1" target="tool1"/>
  <edge source="tool1" target="end"/>
</workflow>

只返回XML，不要其他解释。"""
        
        response = await client.simple_chat(f"{system_prompt}\n\n用户需求: {prompt}")
        
        # 提取XML
        xml_start = response.find("<workflow")
        xml_end = response.rfind("</workflow>") + len("</workflow>")
        
        if xml_start != -1 and xml_end != -1:
            xml_content = response[xml_start:xml_end]
            
            # 自动创建
            from skills.workflow_engine import workflow_engine
            result = workflow_engine.create_from_xml(xml_content)
            
            return {
                "success": True,
                "xml": xml_content,
                "workflow": result,
            }
        else:
            return {"success": False, "error": "AI生成的XML格式错误"}
            
    except Exception as e:
        logger.error(f"AI生成工作流失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))