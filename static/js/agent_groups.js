/**
 * Agent小组管理模块
 * 
 * 支持真正的Agent小组功能：
 * - 小组包含多个Agent
 * - 每个Agent有自己的角色和技能
 * - 支持混合Agent（人物Agent + 功能Agent）
 */

// Agent小组管理器
const _apiBase = window.location.port === '5500' ? 'http://localhost:8001' : '';
class AgentGroupManager {
    constructor() {
        this.groups = [];
        this.availableAgents = {
            character_agents: [],
            tool_agents: []
        };
        this.selectedAgents = [];
        this.currentModal = null;
    }

    async init() {
        try {
            await this.loadAvailableAgents();
            await this.loadGroups();
            console.log('✅ Agent小组管理器初始化完成');
        } catch (error) {
            console.error('❌ Agent小组管理器初始化失败:', error);
        }
    }

    async loadAvailableAgents() {
        const response = await fetch(`${_apiBase}/api/agent-groups/available-agents`);
        const data = await response.json();
        this.availableAgents = data;
        console.log('📋 加载可用Agent完成:', data);
        return data;
    }

    async loadGroups() {
        const response = await fetch(`${_apiBase}/api/agent-groups`);
        this.groups = await response.json();
        console.log('📋 加载Agent小组完成:', this.groups);
        return this.groups;
    }

    async createGroup(name, description, agents, options = {}) {
        const {
            strategy = 'pipeline',
            failure_strategy = 'retry',
            circuit_strategy = 'count_based',
            timeout = 30,
            circuit_breaker = true
        } = options;

        const response = await fetch(`${_apiBase}/api/agent-groups`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name,
                description,
                agents,
                strategy,
                failure_strategy,
                circuit_strategy,
                timeout,
                circuit_breaker,
                elastic_scaling: false
            })
        });

        const group = await response.json();
        await this.loadGroups();
        return group;
    }

    async updateGroup(groupId, updateData) {
        const response = await fetch(`${_apiBase}/api/agent-groups/${groupId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(updateData)
        });

        const group = await response.json();
        await this.loadGroups();
        return group;
    }

    async deleteGroup(groupId) {
        await fetch(`${_apiBase}/api/agent-groups/${groupId}`, {
            method: 'DELETE'
        });
        await this.loadGroups();
    }

    async activateGroup(groupId) {
        await fetch(`${_apiBase}/api/agent-groups/${groupId}/activate`, {
            method: 'POST'
        });
        await this.loadGroups();
    }

    async deactivateGroup(groupId) {
        await fetch(`${_apiBase}/api/agent-groups/${groupId}/deactivate`, {
            method: 'POST'
        });
        await this.loadGroups();
    }
}

// 全局实例
let agentGroupManager = null;

// 初始化
function initAgentGroupModule() {
    if (!agentGroupManager) {
        agentGroupManager = new AgentGroupManager();
    }
    return agentGroupManager.init();
}

// HTML转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 格式化日期
function formatDate(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleDateString('zh-CN');
}

// 显示提示
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    const colors = {
        success: 'bg-green-500',
        error: 'bg-red-500',
        info: 'bg-blue-500',
        warning: 'bg-yellow-500'
    };
    
    toast.className = `fixed top-4 right-4 ${colors[type]} text-white px-6 py-3 rounded-lg shadow-lg z-50 animate-fadeIn`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => toast.remove(), 3000);
}

// 关闭模态框
function closeModal(element) {
    const modal = element.closest('.fixed.inset-0');
    if (modal) {
        modal.remove();
    }
}

// 渲染小组列表
function renderGroupList() {
    const container = document.getElementById('agent-groups-list');
    if (!container) return;

    const groups = agentGroupManager.groups;

    if (groups.length === 0) {
        container.innerHTML = `
            <div class="text-center py-12 text-gray-500">
                <div class="text-6xl mb-4">👥</div>
                <p class="text-lg mb-4">暂无Agent小组</p>
                <button onclick="showCreateGroupModal()" class="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition">
                    创建第一个小组
                </button>
            </div>
        `;
        return;
    }

    container.innerHTML = groups.map(group => `
        <div class="group-card bg-white rounded-xl shadow-md p-6 mb-4 hover:shadow-lg transition cursor-pointer border-2 ${group.status === 'active' ? 'border-green-300' : 'border-gray-200'}"
             onclick="selectGroup('${group.group_id}')">
            <div class="flex items-start justify-between mb-4">
                <div class="flex-1">
                    <h4 class="font-bold text-gray-800 text-lg mb-1">
                        ${group.status === 'active' ? '🟢' : '⚪'} ${escapeHtml(group.name)}
                    </h4>
                    <p class="text-sm text-gray-600">${escapeHtml(group.description)}</p>
                </div>
            </div>
            
            <div class="flex items-center justify-between text-xs text-gray-500 mb-3">
                <span>👥 ${group.agents.length} 个Agent</span>
                <span>📋 ${group.task_count} 次任务</span>
                <span>✅ ${(group.success_rate * 100).toFixed(1)}% 成功率</span>
            </div>
            
            <div class="member-tags flex flex-wrap gap-2 mb-4">
                ${group.agents.slice(0, 5).map(agent => `
                    <span class="px-3 py-1 rounded-full text-xs ${agent.agent_type === 'character' ? 'bg-purple-100 text-purple-700' : 'bg-blue-100 text-blue-700'}">
                        ${agent.agent_type === 'character' ? '🎭' : '🛠️'} ${escapeHtml(agent.agent_name)}
                    </span>
                `).join('')}
                ${group.agents.length > 5 ? `<span class="px-3 py-1 rounded-full text-xs bg-gray-100 text-gray-700">+${group.agents.length - 5}</span>` : ''}
            </div>
            
            <div class="flex items-center justify-between">
                <span class="text-xs text-gray-400">创建于 ${formatDate(group.created_at)}</span>
                <div class="flex space-x-2" onclick="event.stopPropagation()">
                    ${group.status === 'active' ? `
                        <button onclick="deactivateGroup('${group.group_id}')" class="text-yellow-600 hover:text-yellow-800 text-xs">
                            ⏸️ 停用
                        </button>
                    ` : `
                        <button onclick="activateGroup('${group.group_id}')" class="text-green-600 hover:text-green-800 text-xs">
                            ▶️ 激活
                        </button>
                    `}
                    <button onclick="deleteGroup('${group.group_id}')" class="text-red-600 hover:text-red-800 text-xs">
                        🗑️ 删除
                    </button>
                </div>
            </div>
        </div>
    `).join('');
}

// 显示创建小组模态框
function showCreateGroupModal() {
    const { character_agents, tool_agents } = agentGroupManager.availableAgents;

    const modal = document.createElement('div');
    modal.className = 'fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4 animate-fadeIn';
    modal.innerHTML = `
        <div class="bg-white rounded-2xl shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
            <div class="sticky top-0 bg-white border-b px-6 py-4 flex justify-between items-center">
                <h2 class="text-xl font-bold text-gray-800">
                    <span class="mr-2">👥</span>创建Agent小组
                </h2>
                <button onclick="closeModal(this)" class="text-gray-400 hover:text-gray-600 transition text-2xl">
                    ×
                </button>
            </div>
            
            <div class="p-6 space-y-6">
                <!-- 小组基本信息 -->
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-2">小组名称</label>
                    <input type="text" id="group-name" placeholder="输入小组名称..."
                           class="w-full p-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500">
                </div>
                
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-2">小组描述</label>
                    <textarea id="group-description" placeholder="描述小组的用途和目标..." rows="2"
                              class="w-full p-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"></textarea>
                </div>
                
                <!-- 协作模式选择 -->
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-3">
                        <span class="text-blue-600 mr-1">🔄</span>协作模式
                    </label>
                    <select id="dispatch-strategy" class="w-full p-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500">
                        <option value="pipeline">流水线模式 (推荐)</option>
                        <option value="master_slave">主从协作模式</option>
                        <option value="parallel_review">并行评审模式</option>
                        <option value="dynamic_auction">动态拍卖模式</option>
                    </select>
                    <p class="text-xs text-gray-500 mt-1">
                        <strong>流水线模式</strong>: 按任务步骤顺序执行，前一个Agent的输出是后一个的输入，适合有明确流程的任务<br>
                        <strong>主从协作模式</strong>: 主Agent拆解任务，从Agent分工执行，适合复杂任务<br>
                        <strong>并行评审模式</strong>: 多个Agent同时处理同一任务，对比结果取最优，适合需要多方验证的任务<br>
                        <strong>动态拍卖模式</strong>: Agent通过"出价"竞争任务，调度器选择最优解，适合灵活分配场景
                    </p>
                </div>
                
                <!-- 失败处理策略选择 -->
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-3">
                        <span class="text-orange-600 mr-1">⚠️</span>失败处理策略
                    </label>
                    <select id="failure-strategy" class="w-full p-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500">
                        <option value="retry">重试 (推荐)</option>
                        <option value="fast_fail">快速失败</option>
                        <option value="degrade">降级处理</option>
                        <option value="fallback">备用方案</option>
                    </select>
                    <p class="text-xs text-gray-500 mt-1">
                        <strong>重试</strong>: 失败后重试最多3次<br>
                        <strong>快速失败</strong>: 立即返回错误<br>
                        <strong>降级处理</strong>: 返回降级响应<br>
                        <strong>备用方案</strong>: 使用备用处理器
                    </p>
                </div>
                
                <!-- 熔断策略选择 -->
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-3">
                        <span class="text-red-600 mr-1">🔒</span>熔断策略
                    </label>
                    <select id="circuit-strategy" class="w-full p-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500">
                        <option value="count_based">基于失败次数 (推荐)</option>
                        <option value="rate_based">基于失败率</option>
                        <option value="time_based">基于时间窗口</option>
                    </select>
                    <p class="text-xs text-gray-500 mt-1">
                        <strong>基于失败次数</strong>: 连续失败5次触发熔断<br>
                        <strong>基于失败率</strong>: 失败率超过50%触发熔断<br>
                        <strong>基于时间窗口</strong>: 60秒内多次失败触发熔断
                    </p>
                </div>
                
                <!-- 超时时间设置 -->
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-3">
                        <span class="text-green-600 mr-1">⏱️</span>超时时间（秒）
                    </label>
                    <input type="number" id="timeout-value" value="30" min="5" max="300"
                           class="w-full p-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500">
                    <p class="text-xs text-gray-500 mt-1">单个Agent执行的最大时间限制，建议30-60秒</p>
                </div>
                
                <!-- 是否启用熔断 -->
                <div>
                    <label class="flex items-center p-4 bg-gray-50 rounded-lg cursor-pointer">
                        <input type="checkbox" id="enable-circuit-breaker" checked
                               class="w-5 h-5 mr-3">
                        <div>
                            <div class="font-medium text-gray-800">启用熔断机制</div>
                            <div class="text-xs text-gray-500">自动保护系统免受异常Agent影响</div>
                        </div>
                    </label>
                </div>
                
                <!-- 人物Agent选择 -->
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-3">
                        <span class="text-purple-600 mr-1">🎭</span>选择人物Agent（可选）
                    </label>
                    <div class="grid grid-cols-2 md:grid-cols-3 gap-3">
                        ${character_agents.map(agent => `
                            <label class="flex items-center p-4 border-2 rounded-lg cursor-pointer hover:bg-purple-50 hover:border-purple-300 transition" data-agent-id="${agent.agent_id}">
                                <input type="checkbox" class="mr-3 agent-checkbox w-5 h-5" value="${agent.agent_id}">
                                <div>
                                    <div class="font-medium text-gray-800">${escapeHtml(agent.agent_name)}</div>
                                    <div class="text-xs text-gray-500">${escapeHtml(agent.description)}</div>
                                </div>
                            </label>
                        `).join('')}
                    </div>
                </div>
                
                <!-- 工具Agent选择 -->
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-3">
                        <span class="text-blue-600 mr-1">🛠️</span>选择工具Agent（可选）
                    </label>
                    <div class="grid grid-cols-2 md:grid-cols-3 gap-3">
                        ${tool_agents.map(agent => `
                            <label class="flex items-center p-4 border-2 rounded-lg cursor-pointer hover:bg-blue-50 hover:border-blue-300 transition" data-agent-id="${agent.agent_id}">
                                <input type="checkbox" class="mr-3 agent-checkbox w-5 h-5" value="${agent.agent_id}">
                                <div>
                                    <div class="font-medium text-gray-800">${escapeHtml(agent.agent_name)}</div>
                                    <div class="text-xs text-gray-500">${escapeHtml(agent.description)}</div>
                                </div>
                            </label>
                        `).join('')}
                    </div>
                </div>
            </div>
            
            <div class="border-t px-6 py-4 flex justify-end space-x-3">
                <button onclick="closeModal(this)" class="px-6 py-2 text-gray-600 hover:text-gray-800 transition border border-gray-300 rounded-lg">
                    取消
                </button>
                <button onclick="createGroupFromModal()" class="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition">
                    创建
                </button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);
    agentGroupManager.currentModal = modal;
}

// 从模态框创建小组
async function createGroupFromModal() {
    const nameInput = document.getElementById('group-name');
    const descInput = document.getElementById('group-description');
    const checkboxes = document.querySelectorAll('.agent-checkbox:checked');
    
    // 获取策略选择
    const dispatchStrategy = document.getElementById('dispatch-strategy').value;
    const failureStrategy = document.getElementById('failure-strategy').value;
    const circuitStrategy = document.getElementById('circuit-strategy').value;
    const timeoutValue = parseInt(document.getElementById('timeout-value').value);
    const enableCircuitBreaker = document.getElementById('enable-circuit-breaker').checked;

    const name = nameInput.value.trim();
    const description = descInput.value.trim();

    if (!name) {
        showToast('请输入小组名称', 'error');
        return;
    }

    if (checkboxes.length === 0) {
        showToast('请至少选择1个Agent', 'error');
        return;
    }

    // 收集选中的Agent
    const selectedAgentIds = Array.from(checkboxes).map(cb => cb.value);
    const allAgents = [
        ...agentGroupManager.availableAgents.character_agents,
        ...agentGroupManager.availableAgents.tool_agents
    ];

    const selectedAgents = selectedAgentIds.map(agentId => {
        const agent = allAgents.find(a => a.agent_id === agentId);
        const agentSkills = (agent.skills || []).map(skill => ({
            skill_id: skill.skill_id || skill.skill_name || '',
            skill_name: skill.skill_name || skill.skill_id || '',
            enabled: skill.enabled !== false
        }));
        return {
            agent_id: agent.agent_id,
            agent_type: agent.agent_type,
            agent_name: agent.agent_name,
            description: agent.description || '',
            skills: agentSkills,
            priority: agent.priority || 1.0,
            enabled: true
        };
    });

    // 创建选项对象
    const options = {
        strategy: dispatchStrategy,
        failure_strategy: failureStrategy,
        circuit_strategy: circuitStrategy,
        timeout: timeoutValue,
        circuit_breaker: enableCircuitBreaker
    };

    try {
        await agentGroupManager.createGroup(name, description, selectedAgents, options);
        closeModal(agentGroupManager.currentModal);
        renderGroupList();
        updateGroupStats();
        showToast('小组创建成功！', 'success');
    } catch (error) {
        console.error('创建小组失败:', error);
        showToast('创建小组失败，请重试', 'error');
    }
}

// 选择小组
function selectGroup(groupId) {
    const group = agentGroupManager.groups.find(g => g.group_id === groupId);
    if (group) {
        showToast(`已选择小组: ${group.name}`, 'success');
    }
}

// 删除小组
async function deleteGroup(groupId) {
    if (!confirm('确定要删除这个小组吗？')) return;
    
    try {
        await agentGroupManager.deleteGroup(groupId);
        renderGroupList();
        updateGroupStats();
        showToast('小组已删除', 'success');
    } catch (error) {
        console.error('删除小组失败:', error);
        showToast('删除小组失败，请重试', 'error');
    }
}

// 激活小组
async function activateGroup(groupId) {
    try {
        await agentGroupManager.activateGroup(groupId);
        renderGroupList();
        updateGroupStats();
        showToast('小组已激活', 'success');
    } catch (error) {
        console.error('激活小组失败:', error);
        showToast('激活小组失败，请重试', 'error');
    }
}

// 停用小组
async function deactivateGroup(groupId) {
    try {
        await agentGroupManager.deactivateGroup(groupId);
        renderGroupList();
        updateGroupStats();
        showToast('小组已停用', 'info');
    } catch (error) {
        console.error('停用小组失败:', error);
        showToast('停用小组失败，请重试', 'error');
    }
}

// 更新小组统计
function updateGroupStats() {
    const statsEl = document.getElementById('group-stats');
    if (!statsEl) return;

    const groups = agentGroupManager.groups;
    const activeGroups = groups.filter(g => g.status === 'active');
    const totalAgents = groups.reduce((sum, g) => sum + g.agents.length, 0);

    const avgSuccessRate = groups.length > 0
        ? (groups.reduce((sum, g) => sum + g.success_rate, 0) / groups.length * 100).toFixed(1)
        : 0;

    statsEl.innerHTML = `
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div class="bg-white rounded-xl shadow-md p-4">
                <div class="text-3xl font-bold text-blue-600">${groups.length}</div>
                <div class="text-sm text-gray-500">总小组数</div>
            </div>
            <div class="bg-white rounded-xl shadow-md p-4">
                <div class="text-3xl font-bold text-green-600">${activeGroups.length}</div>
                <div class="text-sm text-gray-500">活跃小组</div>
            </div>
            <div class="bg-white rounded-xl shadow-md p-4">
                <div class="text-3xl font-bold text-purple-600">${totalAgents}</div>
                <div class="text-sm text-gray-500">总Agent数</div>
            </div>
            <div class="bg-white rounded-xl shadow-md p-4">
                <div class="text-3xl font-bold text-orange-600">${avgSuccessRate}%</div>
                <div class="text-sm text-gray-500">平均成功率</div>
            </div>
        </div>
    `;
}

// 导出为全局函数
window.initAgentGroupModule = initAgentGroupModule;
window.agentGroupManager = null;
window.renderGroupList = renderGroupList;
window.showCreateGroupModal = showCreateGroupModal;
window.createGroupFromModal = createGroupFromModal;
window.selectGroup = selectGroup;
window.deleteGroup = deleteGroup;
window.activateGroup = activateGroup;
window.deactivateGroup = deactivateGroup;
window.updateGroupStats = updateGroupStats;
window.showToast = showToast;
window.closeModal = closeModal;
window.escapeHtml = escapeHtml;
window.formatDate = formatDate;
window.showCreateGroupModal = showCreateGroupModal;

// 页面加载后自动初始化
document.addEventListener('DOMContentLoaded', function() {
    // 等待一下，确保所有模块加载完成
    setTimeout(async () => {
        if (!window.agentGroupManager) {
            window.agentGroupManager = new AgentGroupManager();
        }
        await initAgentGroupModule();
        renderGroupList();
        updateGroupStats();
    }, 500);
});
