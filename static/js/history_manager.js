/**
 * 聊天历史管理模块（方案A：完整持久化 + 智能检索）
 * 支持本地存储和后端API同步
 * 核心特性：
 * - 所有历史记录永久保存到MySQL
 * - 支持点赞功能，点赞消息永不删除
 * - 未点赞消息默认1天后自动清理
 * - 支持语义搜索、关键词检索
 * - 动态权重系统，影响检索优先级
 */

class ChatHistoryManager {
    constructor() {
        this.storageKey = 'chat_history';
        this.maxHistorySize = 1000;
        this.history = this.loadHistory();
        this.apiBase = '/api';
        this.defaultUserId = 1;
    }

    /**
     * 加载本地历史记录
     */
    loadHistory() {
        try {
            const saved = localStorage.getItem(this.storageKey);
            return saved ? JSON.parse(saved) : [];
        } catch (e) {
            console.error('加载历史记录失败:', e);
            return [];
        }
    }

    /**
     * 保存历史记录到本地存储
     */
    saveHistory() {
        try {
            if (this.history.length > this.maxHistorySize) {
                this.history = this.history.slice(-this.maxHistorySize);
            }
            localStorage.setItem(this.storageKey, JSON.stringify(this.history));
        } catch (e) {
            console.error('保存历史记录失败:', e);
            if (e.name === 'QuotaExceededError') {
                this.history = this.history.slice(-500);
                localStorage.setItem(this.storageKey, JSON.stringify(this.history));
            }
        }
    }

    /**
     * 添加消息到历史记录（本地）
     */
    addMessage(message) {
        const record = {
            id: Date.now(),
            role: message.role || 'user',
            content: message.content || '',
            character_id: message.character_id || 'default',
            timestamp: new Date().toISOString(),
            metadata: message.metadata || {}
        };
        this.history.push(record);
        this.saveHistory();
        return record;
    }

    /**
     * 获取本地历史记录
     */
    getHistory(options = {}) {
        let filtered = [...this.history];
        
        if (options.role) {
            filtered = filtered.filter(h => h.role === options.role);
        }
        
        if (options.character_id) {
            filtered = filtered.filter(h => h.character_id === options.character_id);
        }
        
        if (options.search) {
            const searchTerm = options.search.toLowerCase();
            filtered = filtered.filter(h => 
                h.content.toLowerCase().includes(searchTerm)
            );
        }
        
        if (options.start_date) {
            const startDate = new Date(options.start_date);
            filtered = filtered.filter(h => new Date(h.timestamp) >= startDate);
        }
        
        if (options.end_date) {
            const endDate = new Date(options.end_date);
            filtered = filtered.filter(h => new Date(h.timestamp) <= endDate);
        }
        
        const sortOrder = options.order === 'asc' ? 1 : -1;
        filtered.sort((a, b) => {
            return sortOrder * (new Date(a.timestamp) - new Date(b.timestamp));
        });
        
        if (options.limit) {
            const start = options.offset || 0;
            filtered = filtered.slice(start, start + options.limit);
        }
        
        return filtered;
    }

    /**
     * 按会话分组（本地）
     */
    groupBySession() {
        const sessions = {};
        
        this.history.forEach(record => {
            const sessionId = record.character_id || 'default';
            
            if (!sessions[sessionId]) {
                sessions[sessionId] = {
                    session_id: sessionId,
                    character_id: sessionId,
                    message_count: 0,
                    last_message_time: null,
                    preview: '',
                    messages: []
                };
            }
            
            sessions[sessionId].message_count++;
            sessions[sessionId].last_message_time = record.timestamp;
            sessions[sessionId].messages.push(record);
            
            if (record.role === 'user') {
                sessions[sessionId].preview = record.content.substring(0, 50);
            }
        });
        
        return Object.values(sessions).sort((a, b) => {
            return new Date(b.last_message_time) - new Date(a.last_message_time);
        });
    }

    /**
     * 删除指定会话的历史（本地）
     */
    deleteSession(character_id) {
        const beforeCount = this.history.length;
        this.history = this.history.filter(h => h.character_id !== character_id);
        this.saveHistory();
        return beforeCount - this.history.length;
    }

    /**
     * 清空所有历史记录（本地）
     */
    clearAll() {
        this.history = [];
        this.saveHistory();
    }

    /**
     * 导出历史记录为JSON
     */
    exportHistory() {
        const dataStr = JSON.stringify(this.history, null, 2);
        const dataBlob = new Blob([dataStr], { type: 'application/json' });
        const url = URL.createObjectURL(dataBlob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `chat_history_${new Date().toISOString().split('T')[0]}.json`;
        link.click();
        URL.revokeObjectURL(url);
    }

    /**
     * 导入历史记录
     */
    importHistory(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = (e) => {
                try {
                    const imported = JSON.parse(e.target.result);
                    if (Array.isArray(imported)) {
                        this.history = [...this.history, ...imported];
                        this.saveHistory();
                        resolve(imported.length);
                    } else {
                        reject(new Error('无效的历史记录格式'));
                    }
                } catch (error) {
                    reject(error);
                }
            };
            reader.onerror = () => reject(new Error('文件读取失败'));
            reader.readAsText(file);
        });
    }

    /**
     * 获取本地统计信息
     */
    getStats() {
        const totalMessages = this.history.length;
        const userMessages = this.history.filter(h => h.role === 'user').length;
        const assistantMessages = this.history.filter(h => h.role === 'assistant').length;
        const uniqueCharacters = new Set(this.history.map(h => h.character_id)).size;
        
        let earliestTime = null;
        let latestTime = null;
        if (this.history.length > 0) {
            const timestamps = this.history.map(h => new Date(h.timestamp));
            earliestTime = new Date(Math.min(...timestamps));
            latestTime = new Date(Math.max(...timestamps));
        }
        
        return {
            total_messages: totalMessages,
            user_messages: userMessages,
            assistant_messages: assistantMessages,
            unique_characters: uniqueCharacters,
            earliest_message: earliestTime,
            latest_message: latestTime
        };
    }

    // ==================== 后端 API 方法 ====================

    /**
     * 从后端获取聊天历史
     */
    async fetchHistoryFromServer(options = {}) {
        try {
            const params = new URLSearchParams();
            
            if (options.character_id) params.append('character_id', options.character_id);
            if (options.limit) params.append('limit', options.limit);
            if (options.offset) params.append('offset', options.offset);
            if (options.search) params.append('search', options.search);
            if (options.start_date) params.append('start_date', options.start_date);
            if (options.end_date) params.append('end_date', options.end_date);
            if (options.group_by_session) params.append('group_by_session', 'true');
            
            const response = await fetch(`${this.apiBase}/history?${params.toString()}`);
            return await response.json();
        } catch (error) {
            console.error('从后端获取历史失败:', error);
            throw error;
        }
    }

    /**
     * 从后端获取会话历史
     */
    async fetchSessionFromServer(sessionId, userId = 1) {
        try {
            const response = await fetch(`${this.apiBase}/history/session/${sessionId}?user_id=${userId}`);
            return await response.json();
        } catch (error) {
            console.error('从后端获取会话失败:', error);
            throw error;
        }
    }

    /**
     * 获取单条历史记录详情
     */
    async fetchHistoryDetail(historyId, userId = 1) {
        try {
            const response = await fetch(`${this.apiBase}/history/${historyId}?user_id=${userId}`);
            return await response.json();
        } catch (error) {
            console.error('获取历史详情失败:', error);
            throw error;
        }
    }

    /**
     * 删除单条历史记录
     */
    async deleteHistoryItem(historyId, userId = 1) {
        try {
            const response = await fetch(`${this.apiBase}/history/${historyId}?user_id=${userId}`, {
                method: 'DELETE'
            });
            return await response.json();
        } catch (error) {
            console.error('删除历史记录失败:', error);
            throw error;
        }
    }

    /**
     * 清空聊天历史
     */
    async clearHistoryFromServer(userId = 1, characterId = null) {
        try {
            const params = new URLSearchParams();
            params.append('user_id', userId);
            if (characterId) params.append('character_id', characterId);
            
            const response = await fetch(`${this.apiBase}/history?${params.toString()}`, {
                method: 'DELETE'
            });
            return await response.json();
        } catch (error) {
            console.error('清空历史失败:', error);
            throw error;
        }
    }

    /**
     * 获取聊天历史统计
     */
    async fetchStatsFromServer(userId = 1) {
        try {
            const response = await fetch(`${this.apiBase}/history/stats?user_id=${userId}`);
            return await response.json();
        } catch (error) {
            console.error('获取统计失败:', error);
            throw error;
        }
    }

    /**
     * 点赞/取消点赞消息
     */
    async toggleLike(historyId, userId = 1) {
        try {
            const response = await fetch(`${this.apiBase}/history/${historyId}/like?user_id=${userId}`, {
                method: 'POST'
            });
            return await response.json();
        } catch (error) {
            console.error('点赞操作失败:', error);
            throw error;
        }
    }

    /**
     * 设置消息权重
     */
    async setMessageWeight(historyId, weight, userId = 1) {
        try {
            const response = await fetch(`${this.apiBase}/history/${historyId}/weight?user_id=${userId}&weight=${weight}`, {
                method: 'POST'
            });
            return await response.json();
        } catch (error) {
            console.error('设置权重失败:', error);
            throw error;
        }
    }

    /**
     * 智能检索获取上下文
     */
    async fetchIntelligentContext(options = {}) {
        try {
            const params = new URLSearchParams();
            params.append('user_id', options.user_id || this.defaultUserId);
            
            if (options.query) params.append('query', options.query);
            if (options.character_id) params.append('character_id', options.character_id);
            if (options.max_tokens) params.append('max_tokens', options.max_tokens);
            if (options.prefer_liked !== undefined) params.append('prefer_liked', options.prefer_liked);
            if (options.include_recent !== undefined) params.append('include_recent', options.include_recent);
            if (options.max_messages) params.append('max_messages', options.max_messages);
            
            const response = await fetch(`${this.apiBase}/history/context?${params.toString()}`);
            return await response.json();
        } catch (error) {
            console.error('智能检索失败:', error);
            throw error;
        }
    }

    /**
     * 清理过期消息（未点赞且超过指定天数）
     */
    async cleanupExpiredMessages(userId = 1, expireDays = 1) {
        try {
            const response = await fetch(`${this.apiBase}/history/cleanup?user_id=${userId}&expire_days=${expireDays}`, {
                method: 'DELETE'
            });
            return await response.json();
        } catch (error) {
            console.error('清理过期消息失败:', error);
            throw error;
        }
    }
}

const chatHistoryManager = new ChatHistoryManager();

/**
 * 渲染历史记录列表（本地）
 */
function renderHistoryList(options = {}) {
    const historyContainer = document.getElementById('history-list');
    if (!historyContainer) return;
    
    const history = chatHistoryManager.getHistory(options);
    
    if (history.length === 0) {
        historyContainer.innerHTML = `
            <div class="text-center py-8 text-gray-500">
                <i class="fa fa-inbox text-4xl mb-3"></i>
                <p>暂无历史记录</p>
            </div>
        `;
        return;
    }
    
    historyContainer.innerHTML = history.map(record => `
        <div class="history-item bg-white rounded-lg shadow-sm p-4 mb-3 hover:shadow-md transition cursor-pointer"
             onclick="loadHistoryMessage('${record.id}')">
            <div class="flex items-start justify-between">
                <div class="flex-1">
                    <div class="flex items-center mb-2">
                        <span class="text-xs font-medium ${record.role === 'user' ? 'text-blue-600' : 'text-green-600'} mr-2">
                            ${record.role === 'user' ? '👤 用户' : '🤖 AI'}
                        </span>
                        <span class="text-xs text-gray-500">
                            ${formatTime(record.timestamp)}
                        </span>
                    </div>
                    <p class="text-sm text-gray-700 line-clamp-2">${escapeHtml(record.content)}</p>
                </div>
                <button onclick="deleteHistoryItem('${record.id}', event)" 
                        class="ml-3 text-gray-400 hover:text-red-600 transition">
                    <i class="fa fa-trash-o"></i>
                </button>
            </div>
        </div>
    `).join('');
}

/**
 * 渲染会话列表（本地）
 */
function renderSessionList() {
    const sessionContainer = document.getElementById('session-list');
    if (!sessionContainer) return;
    
    const sessions = chatHistoryManager.groupBySession();
    
    if (sessions.length === 0) {
        sessionContainer.innerHTML = `
            <div class="text-center py-8 text-gray-500">
                <i class="fa fa-comments text-4xl mb-3"></i>
                <p>暂无会话</p>
            </div>
        `;
        return;
    }
    
    sessionContainer.innerHTML = sessions.map(session => `
        <div class="session-item bg-white rounded-lg shadow-sm p-4 mb-3 hover:shadow-md transition cursor-pointer"
             onclick="loadSession('${session.session_id}')">
            <div class="flex items-center justify-between">
                <div class="flex-1">
                    <h4 class="font-medium text-gray-800 mb-1">
                        ${getCharacterName(session.character_id)}
                    </h4>
                    <p class="text-sm text-gray-600 line-clamp-1">${escapeHtml(session.preview)}</p>
                    <div class="flex items-center mt-2 text-xs text-gray-500">
                        <span class="mr-3">💬 ${session.message_count} 条消息</span>
                        <span>🕐 ${formatTime(session.last_message_time)}</span>
                    </div>
                </div>
                <button onclick="deleteSession('${session.session_id}', event)" 
                        class="ml-3 text-gray-400 hover:text-red-600 transition">
                    <i class="fa fa-trash-o"></i>
                </button>
            </div>
        </div>
    `).join('');
}

/**
 * 从后端加载并渲染会话列表
 */
async function loadAndRenderSessionsFromServer(options = {}) {
    const sessionContainer = document.getElementById('session-list');
    if (!sessionContainer) return;
    
    try {
        const data = await chatHistoryManager.fetchHistoryFromServer({
            group_by_session: true,
            limit: options.limit || 20,
            offset: options.offset || 0,
            search: options.search,
            start_date: options.start_date,
            end_date: options.end_date
        });
        
        const sessions = data.sessions || [];
        
        if (sessions.length === 0) {
            sessionContainer.innerHTML = `
                <div class="text-center py-8 text-gray-500">
                    <i class="fa fa-comments text-4xl mb-3"></i>
                    <p>暂无会话</p>
                </div>
            `;
            return;
        }
        
        sessionContainer.innerHTML = sessions.map(session => `
            <div class="session-item bg-white rounded-lg shadow-sm p-4 mb-3 hover:shadow-md transition cursor-pointer"
                 onclick="loadSessionFromServer('${session.session_id}', '${session.character_id}')">
                <div class="flex items-center justify-between">
                    <div class="flex-1">
                        <div class="flex items-center gap-2 mb-1">
                            <h4 class="font-medium text-gray-800">
                                ${getCharacterName(session.character_id)}
                            </h4>
                            ${session.liked_count > 0 ? `
                                <span class="text-xs bg-pink-100 text-pink-600 px-2 py-0.5 rounded-full">
                                    ❤️ ${session.liked_count}
                                </span>
                            ` : ''}
                        </div>
                        <p class="text-sm text-gray-600 line-clamp-1">${escapeHtml(session.preview || '')}</p>
                        <div class="flex items-center mt-2 text-xs text-gray-500">
                            <span class="mr-3">💬 ${session.message_count} 条消息</span>
                            <span>🕐 ${formatTime(session.last_message_time)}</span>
                        </div>
                    </div>
                    <button onclick="deleteSessionFromServer('${session.character_id}', event)" 
                            class="ml-3 text-gray-400 hover:text-red-600 transition">
                        <i class="fa fa-trash-o"></i>
                    </button>
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('加载会话失败:', error);
        sessionContainer.innerHTML = `
            <div class="text-center py-8 text-red-500">
                <i class="fa fa-exclamation-circle text-4xl mb-3"></i>
                <p>加载会话失败</p>
            </div>
        `;
    }
}

/**
 * 格式化时间
 */
function formatTime(timestamp) {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now - date;
    
    if (diff < 60000) return '刚刚';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`;
    if (diff < 604800000) return `${Math.floor(diff / 86400000)}天前`;
    
    return date.toLocaleDateString('zh-CN');
}

/**
 * 获取角色名称
 */
function getCharacterName(characterId) {
    const names = {
        'default': '小龙虾助手',
        'bestfriend': '知心闺蜜',
        'first_love': '温柔初恋',
        'goddess': '高冷女神',
        'john_carmack': 'John Carmack',
        'libai': '诗仙李白',
        'linus_torvalds': 'Linus Torvalds'
    };
    return names[characterId] || characterId;
}

/**
 * HTML转义
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * 加载本地历史消息
 */
function loadHistoryMessage(messageId) {
    const message = chatHistoryManager.history.find(h => h.id == messageId);
    if (message) {
        showToast('已加载历史消息', 'success');
        console.log('加载消息:', message);
    }
}

/**
 * 从后端加载会话到聊天界面
 */
async function loadSessionFromServer(sessionId, characterId) {
    try {
        const data = await chatHistoryManager.fetchSessionFromServer(sessionId);
        
        if (!data.messages || data.messages.length === 0) {
            alert('会话为空或不存在');
            return;
        }
        
        const chatMessages = document.getElementById('chat-messages');
        if (chatMessages) {
            chatMessages.innerHTML = '';
        }
        
        if (characterId) {
            switchCharacter(characterId);
        }
        
        data.messages.forEach(msg => {
            addMessage(msg.role, msg.content, false, msg.is_liked, msg.id);
        });
        
        if (chatMessages) {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
        
    } catch (error) {
        console.error('加载会话失败:', error);
        alert('加载会话失败');
    }
}

/**
 * 点赞/取消点赞消息
 */
async function toggleMessageLike(messageId, event) {
    event.stopPropagation();
    
    try {
        const result = await chatHistoryManager.toggleLike(messageId);
        
        if (result.success) {
            // 更新UI显示
            const likeBtn = event.currentTarget;
            if (result.is_liked) {
                likeBtn.classList.remove('text-gray-300');
                likeBtn.classList.add('text-pink-500');
                likeBtn.innerHTML = '<i class="fa fa-heart"></i>';
                showToast('已点赞（消息将永久保存）', 'success');
            } else {
                likeBtn.classList.remove('text-pink-500');
                likeBtn.classList.add('text-gray-300');
                likeBtn.innerHTML = '<i class="fa fa-heart-o"></i>';
                showToast('已取消点赞', 'info');
            }
        } else {
            showToast('操作失败: ' + (result.detail || '未知错误'), 'error');
        }
    } catch (error) {
        console.error('点赞操作失败:', error);
        showToast('操作失败', 'error');
    }
}

/**
 * 清理过期消息
 */
async function cleanupExpiredMessages() {
    if (!confirm('确定要清理未点赞的过期消息吗？（超过1天的普通消息将被删除）')) {
        return;
    }
    
    try {
        const result = await chatHistoryManager.cleanupExpiredMessages(1, 1);
        
        if (result.success) {
            showToast(`已清理 ${result.deleted_count} 条过期消息`, 'success');
            loadAndRenderSessionsFromServer();
        } else {
            showToast('清理失败: ' + (result.detail || '未知错误'), 'error');
        }
    } catch (error) {
        console.error('清理失败:', error);
        showToast('清理失败', 'error');
    }
}

/**
 * 切换角色
 */
function switchCharacter(characterId) {
    const charBtn = document.querySelector(`[data-character="${characterId}"]`);
    if (charBtn) {
        charBtn.click();
    }
}

/**
 * 本地加载会话
 */
function loadSession(sessionId) {
    showToast(`加载会话: ${sessionId}`, 'info');
}

/**
 * 删除本地历史项
 */
function deleteHistoryItem(messageId, event) {
    event.stopPropagation();
    if (confirm('确定要删除这条消息吗？')) {
        chatHistoryManager.history = chatHistoryManager.history.filter(h => h.id != messageId);
        chatHistoryManager.saveHistory();
        renderHistoryList();
        showToast('已删除', 'success');
    }
}

/**
 * 从后端删除会话
 */
async function deleteSessionFromServer(characterId, event) {
    event.stopPropagation();
    if (confirm('确定要删除这个会话的所有消息吗？')) {
        try {
            const result = await chatHistoryManager.clearHistoryFromServer(1, characterId);
            if (result.success) {
                showToast(`已删除 ${result.deleted} 条消息`, 'success');
                loadAndRenderSessionsFromServer();
            } else {
                showToast('删除失败: ' + (result.detail || '未知错误'), 'error');
            }
        } catch (error) {
            console.error('删除会话失败:', error);
            showToast('删除失败', 'error');
        }
    }
}

/**
 * 删除本地会话
 */
function deleteSession(sessionId, event) {
    event.stopPropagation();
    if (confirm('确定要删除这个会话的所有消息吗？')) {
        const count = chatHistoryManager.deleteSession(sessionId);
        renderSessionList();
        showToast(`已删除 ${count} 条消息`, 'success');
    }
}

/**
 * 显示提示
 */
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    const colors = {
        success: 'bg-green-500',
        error: 'bg-red-500',
        info: 'bg-blue-500',
        warning: 'bg-yellow-500'
    };
    
    toast.className = `fixed top-20 right-4 ${colors[type]} text-white px-6 py-3 rounded-lg shadow-lg z-50 animate-fadeIn`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.remove();
    }, 3000);
}

/**
 * 初始化历史管理模块
 */
function initHistoryModule() {
    const historyBtn = document.querySelector('button[onclick*="历史"]');
    if (historyBtn) {
        historyBtn.addEventListener('click', () => {
            showHistoryPanel();
        });
    }
    
    renderHistoryList();
    renderSessionList();
}

/**
 * 显示历史面板
 */
function showHistoryPanel() {
    showToast('历史记录功能开发中...', 'info');
}

/**
 * 搜索历史记录（本地）
 */
function searchHistory(searchTerm) {
    const roleFilter = document.getElementById('history-filter-role')?.value || '';
    renderHistoryList({ search: searchTerm, role: roleFilter });
}

/**
 * 过滤历史记录（本地）
 */
function filterHistory() {
    const searchTerm = document.getElementById('history-search')?.value || '';
    const roleFilter = document.getElementById('history-filter-role')?.value || '';
    renderHistoryList({ search: searchTerm, role: roleFilter });
}

/**
 * 显示历史视图
 */
function showHistoryView(viewType) {
    const messagesView = document.getElementById('history-list');
    const sessionsView = document.getElementById('session-list');
    const messagesBtn = document.getElementById('view-messages');
    const sessionsBtn = document.getElementById('view-sessions');
    
    if (viewType === 'messages') {
        messagesView.classList.remove('hidden');
        sessionsView.classList.add('hidden');
        messagesBtn.className = 'px-4 py-2 bg-blue-600 text-white rounded-lg text-sm transition';
        sessionsBtn.className = 'px-4 py-2 bg-gray-200 text-gray-700 rounded-lg text-sm hover:bg-gray-300 transition';
        renderHistoryList();
    } else {
        messagesView.classList.add('hidden');
        sessionsView.classList.remove('hidden');
        messagesBtn.className = 'px-4 py-2 bg-gray-200 text-gray-700 rounded-lg text-sm hover:bg-gray-300 transition';
        sessionsBtn.className = 'px-4 py-2 bg-blue-600 text-white rounded-lg text-sm transition';
        loadAndRenderSessionsFromServer();
    }
}

/**
 * 导出历史记录
 */
function exportHistory() {
    chatHistoryManager.exportHistory();
    showToast('历史记录已导出', 'success');
}

/**
 * 清空所有历史记录（本地）
 */
function clearAllHistory() {
    if (confirm('确定要清空所有历史记录吗？此操作不可恢复！')) {
        chatHistoryManager.clearAll();
        renderHistoryList();
        renderSessionList();
        showToast('历史记录已清空', 'success');
    }
}

/**
 * 从后端清空所有历史记录
 */
async function clearAllHistoryFromServer() {
    if (!confirm('确定要清空所有历史记录吗？此操作不可恢复！')) {
        return;
    }
    
    try {
        const result = await chatHistoryManager.clearHistoryFromServer(1);
        if (result.success) {
            showToast('历史记录已清空', 'success');
            loadAndRenderSessionsFromServer();
        } else {
            showToast('清空失败: ' + (result.detail || '未知错误'), 'error');
        }
    } catch (error) {
        console.error('清空历史失败:', error);
        showToast('清空失败', 'error');
    }
}

/**
 * 获取并显示统计信息
 */
async function showHistoryStatsFromServer() {
    try {
        const data = await chatHistoryManager.fetchStatsFromServer(1);
        const stats = data.stats || {};
        
        const modal = document.createElement('div');
        modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
        modal.onclick = (e) => {
            if (e.target === modal) modal.remove();
        };
        
        modal.innerHTML = `
            <div class="bg-white rounded-2xl shadow-2xl max-w-md w-full mx-4 p-6 animate-fadeIn">
                <div class="flex justify-between items-center mb-4">
                    <h3 class="text-xl font-bold text-gray-800">📊 对话统计</h3>
                    <button onclick="this.closest('.fixed').remove()" class="text-gray-400 hover:text-gray-600 text-2xl">&times;</button>
                </div>
                
                <div class="grid grid-cols-2 gap-4 mb-6">
                    <div class="bg-gradient-to-br from-blue-50 to-blue-100 p-4 rounded-xl text-center">
                        <div class="text-3xl font-bold text-blue-600">${stats.total_messages || 0}</div>
                        <div class="text-sm text-gray-600 mt-1">总消息数</div>
                    </div>
                    <div class="bg-gradient-to-br from-green-50 to-green-100 p-4 rounded-xl text-center">
                        <div class="text-3xl font-bold text-green-600">${stats.user_messages || 0}</div>
                        <div class="text-sm text-gray-600 mt-1">我的消息</div>
                    </div>
                    <div class="bg-gradient-to-br from-purple-50 to-purple-100 p-4 rounded-xl text-center">
                        <div class="text-3xl font-bold text-purple-600">${stats.assistant_messages || 0}</div>
                        <div class="text-sm text-gray-600 mt-1">AI回复</div>
                    </div>
                    <div class="bg-gradient-to-br from-yellow-50 to-yellow-100 p-4 rounded-xl text-center">
                        <div class="text-3xl font-bold text-yellow-600">${stats.conversation_days || 0}</div>
                        <div class="text-sm text-gray-600 mt-1">活跃天数</div>
                    </div>
                </div>
                
                ${stats.character_breakdown ? `
                    <div class="mb-4">
                        <h4 class="font-semibold text-gray-700 mb-2">各角色消息分布</h4>
                        <div class="space-y-2">
                            ${Object.entries(stats.character_breakdown).map(([char, count]) => `
                                <div class="flex justify-between items-center p-2 bg-gray-50 rounded-lg">
                                    <span class="text-sm text-gray-700">${getCharacterName(char)}</span>
                                    <span class="text-sm font-medium text-blue-600">${count} 条</span>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                ` : ''}
                
                ${stats.earliest_message ? `
                    <div class="text-xs text-gray-500 space-y-1 pt-4 border-t">
                        <p>📅 最早消息: ${new Date(stats.earliest_message).toLocaleString('zh-CN')}</p>
                        <p>📅 最新消息: ${new Date(stats.latest_message).toLocaleString('zh-CN')}</p>
                    </div>
                ` : ''}
            </div>
        `;
        
        document.body.appendChild(modal);
        
    } catch (error) {
        console.error('获取统计信息失败:', error);
        alert('获取统计信息失败');
    }
}

document.addEventListener('DOMContentLoaded', initHistoryModule);
// 暴露全局函数到window对象（遵循前端模块化规范）
window.searchHistory = searchHistory;
window.filterHistory = filterHistory;
window.exportHistory = exportHistory;
window.clearAllHistory = clearAllHistory;
window.showHistoryView = showHistoryView;

