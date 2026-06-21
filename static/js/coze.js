// ==================== Coze 平台 JavaScript ====================

// API 基础地址 — 后端默认 8001 端口
const API_BASE = 'http://localhost:8001';

// 全局变量
let currentAgentId = 'auto';  // 默认使用智能匹配
let currentAgentInfo = {
    id: 'auto',
    name: '智能匹配',
    description: '让系统智能选择最佳Agent',
    capabilities: ['智能', '自动', '匹配']
};
let messageCount = 0;
let responseStartTime = 0;

// Agent 配置映射
const AGENT_CONFIG = {
    'auto': { name: '智能匹配', description: '让系统智能选择最佳Agent', capabilities: ['智能', '自动', '匹配'] },
    'general': { name: '通用助手', description: '擅长处理各种日常问题', capabilities: ['聊天', '计算', '娱乐'] },
    'data_analyst': { name: '数据分析师', description: '擅长数据处理、统计分析和可视化', capabilities: ['数据', '分析', '可视化'] },
    'web_scraper': { name: '网络爬虫', description: '擅长从各平台抓取公开数据', capabilities: ['爬虫', '数据', '搜索'] },
    'weather_expert': { name: '天气预报员', description: '可以查询各城市的天气和预报', capabilities: ['天气', '预报', '查询'] },
    'system_toolbox': { name: '系统工具', description: '可以执行系统命令、管理文件', capabilities: ['系统', '命令', '文件'] },
    'translator': { name: '翻译官', description: '精通多语言互译', capabilities: ['翻译', '语言', '多语种'] },
    'deep_thinker': { name: '深度思考者', description: '擅长复杂问题的多维度分析和推理', capabilities: ['思考', '分析', '推理'] },
    'creative': { name: '创意助手', description: '擅长生成有趣内容、故事和艺术', capabilities: ['创意', '写作', '艺术'] }
};

// ==================== 用户偏好设置管理 ====================
const UserPreferences = {
    // 默认设置
    defaults: {
        theme: 'light',
        fontSize: 'medium',
        language: 'zh',
        soundEnabled: true,
        autosaveEnabled: true,
        lineNumbersEnabled: true,
        maxHistoryLength: 100  // 最大保存消息数
    },
    
    // 加载设置
    load() {
        try {
            const saved = localStorage.getItem('coze_preferences');
            return saved ? {...this.defaults, ...JSON.parse(saved)} : {...this.defaults};
        } catch (e) {
            console.error('加载用户偏好失败:', e);
            return {...this.defaults};
        }
    },
    
    // 保存设置
    save(prefs) {
        try {
            localStorage.setItem('coze_preferences', JSON.stringify(prefs));
            this.apply(prefs);
            console.log('✅ 用户偏好设置已保存');
        } catch (e) {
            console.error('保存用户偏好失败:', e);
        }
    },
    
    // 应用设置
    apply(prefs) {
        // 应用主题
        if (prefs.theme === 'auto') {
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            document.documentElement.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
        } else {
            document.documentElement.setAttribute('data-theme', prefs.theme);
        }
        
        // 应用字体大小
        document.documentElement.setAttribute('data-font-size', prefs.fontSize);
        
        // 更新UI状态
        this.updateUI(prefs);
    },
    
    // 更新UI状态
    updateUI(prefs) {
        // 更新主题选项
        document.querySelectorAll('.theme-option').forEach(el => {
            const theme = el.getAttribute('data-theme');
            const input = el.querySelector('input');
            if (input) {
                input.checked = theme === prefs.theme;
                el.classList.toggle('border-blue-500', theme === prefs.theme);
                el.classList.toggle('border-gray-300', theme !== prefs.theme);
            }
        });
        
        // 更新字体大小选项
        document.querySelectorAll('.font-size-option').forEach(el => {
            const size = el.getAttribute('data-size');
            el.classList.toggle('border-blue-500', size === prefs.fontSize);
            el.classList.toggle('border-gray-300', size !== prefs.fontSize);
        });
        
        // 更新语言选择
        const langSelect = document.getElementById('language-select');
        if (langSelect) langSelect.value = prefs.language;
        
        // 更新开关状态
        const soundToggle = document.getElementById('sound-toggle');
        if (soundToggle) soundToggle.checked = prefs.soundEnabled;
        
        const autosaveToggle = document.getElementById('autosave-toggle');
        if (autosaveToggle) autosaveToggle.checked = prefs.autosaveEnabled;
        
        const linenumbersToggle = document.getElementById('linenumbers-toggle');
        if (linenumbersToggle) linenumbersToggle.checked = prefs.lineNumbersEnabled;
    }
};

// ==================== 消息历史记录管理 ====================
const MessageHistory = {
    STORAGE_KEY: 'coze_message_history',
    
    // 加载消息历史
    load() {
        try {
            const saved = localStorage.getItem(this.STORAGE_KEY);
            return saved ? JSON.parse(saved) : [];
        } catch (e) {
            console.error('加载消息历史失败:', e);
            return [];
        }
    },
    
    // 保存消息历史
    save(messages) {
        try {
            const prefs = UserPreferences.load();
            const maxLen = prefs.maxHistoryLength || 100;
            
            // 限制消息数量
            if (messages.length > maxLen) {
                messages = messages.slice(-maxLen);
            }
            
            localStorage.setItem(this.STORAGE_KEY, JSON.stringify(messages));
            console.log(`💾 消息历史已保存 (${messages.length} 条)`);
        } catch (e) {
            console.error('保存消息历史失败:', e);
        }
    },
    
    // 添加消息
    add(role, content, timestamp = null) {
        const messages = this.load();
        messages.push({
            role: role,
            content: content,
            timestamp: timestamp || new Date().toISOString()
        });
        this.save(messages);
    },
    
    // 清空历史
    clear() {
        try {
            localStorage.removeItem(this.STORAGE_KEY);
            console.log('🗑️ 消息历史已清空');
        } catch (e) {
            console.error('清空消息历史失败:', e);
        }
    },
    
    // 导出为 JSON
    exportAsJSON() {
        const messages = this.load();
        const blob = new Blob([JSON.stringify(messages, null, 2)], {type: 'application/json'});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `chat_history_${new Date().getTime()}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        console.log('📥 消息历史已导出为 JSON');
    },
    
    // 导出为 TXT
    exportAsTXT() {
        const messages = this.load();
        let text = `聊天记录 - ${new Date().toLocaleString()}\n`;
        text += '='.repeat(50) + '\n\n';
        
        messages.forEach(msg => {
            const time = new Date(msg.timestamp).toLocaleString();
            const role = msg.role === 'user' ? '👤 用户' : '🤖 AI';
            text += `[${time}] ${role}:\n${msg.content}\n\n`;
        });
        
        const blob = new Blob([text], {type: 'text/plain;charset=utf-8'});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `chat_history_${new Date().getTime()}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        console.log('📥 消息历史已导出为 TXT');
    },
    
    // 搜索消息
    search(keyword) {
        const messages = this.load();
        if (!keyword) return messages;
        
        return messages.filter(msg => 
            msg.content.toLowerCase().includes(keyword.toLowerCase())
        );
    },
    
    // 恢复历史到界面
    restoreToUI() {
        const messages = this.load();
        if (messages.length === 0) {
            console.log('ℹ️ 没有可恢复的消息历史');
            return;
        }
        
        const chatContainer = document.querySelector('.chat-container');
        if (!chatContainer) {
            console.error('未找到聊天容器');
            return;
        }
        
        // 清空当前显示（保留欢迎消息）
        const welcomeMsg = chatContainer.querySelector('.message-welcome');
        chatContainer.innerHTML = '';
        if (welcomeMsg) chatContainer.appendChild(welcomeMsg);
        
        // 恢复消息
        messages.forEach(msg => {
            const messageDiv = document.createElement('div');
            messageDiv.className = `message message-${msg.role}`;
            
            const avatar = document.createElement('div');
            avatar.className = 'message-avatar';
            avatar.textContent = msg.role === 'user' ? '👤' : '🤖';
            
            const content = document.createElement('div');
            content.className = 'message-content';
            content.textContent = msg.content;
            
            const time = document.createElement('div');
            time.className = 'message-time';
            time.textContent = new Date(msg.timestamp).toLocaleTimeString();
            
            messageDiv.appendChild(avatar);
            messageDiv.appendChild(content);
            messageDiv.appendChild(time);
            chatContainer.appendChild(messageDiv);
        });
        
        // 滚动到底部
        chatContainer.scrollTop = chatContainer.scrollHeight;
        console.log(`✅ 已恢复 ${messages.length} 条消息`);
    }
};

// 设置主题
function setTheme(theme) {
    const prefs = UserPreferences.load();
    prefs.theme = theme;
    UserPreferences.save(prefs);
    console.log('🎨 主题已切换为:', theme);
    
    const themeNames = { light: '亮色主题', dark: '暗色主题', auto: '自动跟随' };
    showToast(`✅ 已切换到${themeNames[theme]}`);
}

// 设置字体大小
function setFontSize(size) {
    const prefs = UserPreferences.load();
    prefs.fontSize = size;
    UserPreferences.save(prefs);
    console.log('📏 字体大小已设置为:', size);
    
    const sizeNames = { small: '小', medium: '中', large: '大' };
    showToast(`✅ 字体大小已设置为${sizeNames[size]}`);
}

// 设置语言
function setLanguage(lang) {
    const prefs = UserPreferences.load();
    prefs.language = lang;
    UserPreferences.save(prefs);
    console.log('🌐 语言已切换为:', lang);
    
    const langNames = { zh: '简体中文', en: 'English' };
    showToast(`✅ 语言已切换为${langNames[lang]}`);
}

// 切换提示音
function toggleSound(enabled) {
    const prefs = UserPreferences.load();
    prefs.soundEnabled = enabled;
    UserPreferences.save(prefs);
    console.log('🔔 提示音已', enabled ? '开启' : '关闭');
}

// 切换自动保存
function toggleAutosave(enabled) {
    const prefs = UserPreferences.load();
    prefs.autosaveEnabled = enabled;
    UserPreferences.save(prefs);
    console.log('💾 自动保存已', enabled ? '开启' : '关闭');
}

// 切换行号显示
function toggleLineNumbers(enabled) {
    const prefs = UserPreferences.load();
    prefs.lineNumbersEnabled = enabled;
    UserPreferences.save(prefs);
    console.log('📝 代码行号已', enabled ? '开启' : '关闭');
}

// 打开设置面板
function openSettings() {
    const modal = document.getElementById('settings-modal');
    if (modal) {
        modal.classList.remove('hidden');
        const prefs = UserPreferences.load();
        UserPreferences.updateUI(prefs);
        console.log('⚙️ 设置面板已打开');
    }
}

// 关闭设置面板
function closeSettings() {
    const modal = document.getElementById('settings-modal');
    if (modal) {
        modal.classList.add('hidden');
        console.log('️ 设置面板已关闭');
    }
}

// 恢复默认设置
function resetSettings() {
    if (confirm('确定要恢复默认设置吗？所有自定义设置将被清除。')) {
        UserPreferences.save(UserPreferences.defaults);
        showToast('✅ 已恢复默认设置');
        console.log(' 已恢复默认设置');
    }
}

// 简单的Toast提示
function showToast(message, duration = 2000) {
    const toast = document.createElement('div');
    toast.className = 'fixed top-20 right-4 bg-green-600 text-white px-6 py-3 rounded-lg shadow-lg z-50';
    toast.textContent = message;
    toast.style.animation = 'fadeIn 0.3s ease-out';
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// 暂时禁用WebSocket，直接使用HTTP API
// WebSocket连接存在兼容性问题（403错误）
function initWebSocket() {
    console.log('⚠️  WebSocket暂时禁用，使用HTTP API');
}

// 添加消息到聊天界面
function addMessage(role, content, useMarkdown = true) {
    const chatMessages = document.getElementById('chat-messages');
    if (!chatMessages) return;

    const messageDiv = document.createElement('div');
    messageDiv.className = `flex ${role === 'user' ? 'justify-end' : 'justify-start'} mb-4`;

    const bubble = document.createElement('div');
    bubble.className = role === 'user' 
        ? 'max-w-[70%] bg-gradient-to-r from-blue-600 to-purple-600 text-white px-4 py-2 rounded-2xl rounded-tr-sm'
        : 'max-w-[70%] bg-white px-4 py-2 rounded-2xl rounded-tl-sm shadow-md';

    // 使用Markdown渲染
    if (useMarkdown && role === 'assistant') {
        bubble.innerHTML = markdownToHtml(content);
    } else {
        bubble.textContent = content;
    }

    messageDiv.appendChild(bubble);
    chatMessages.appendChild(messageDiv);

    // 滚动到底部
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    // 更新消息计数
    messageCount++;
    updateMessageStats();
}

// 添加带深度思考过程的消息
function addMessageWithThinking(role, content, thinkingProcess, useMarkdown = true) {
    const chatMessages = document.getElementById('chat-messages');
    if (!chatMessages) return;

    const messageDiv = document.createElement('div');
    messageDiv.className = `flex ${role === 'user' ? 'justify-end' : 'justify-start'} mb-4`;

    const bubble = document.createElement('div');
    bubble.className = role === 'user' 
        ? 'max-w-[70%] bg-gradient-to-r from-blue-600 to-purple-600 text-white px-4 py-2 rounded-2xl rounded-tr-sm'
        : 'max-w-[85%] bg-white px-4 py-3 rounded-2xl rounded-tl-sm shadow-md';

    let htmlContent = '';

    // 如果有深度思考过程，先显示折叠面板
    if (thinkingProcess && Object.keys(thinkingProcess).length > 0) {
        const thinkingId = 'thinking-' + Date.now();
        htmlContent += `
            <div class="mb-3 border-l-4 border-purple-500 pl-3">
                <button onclick="toggleThinking('${thinkingId}')" class="flex items-center text-purple-600 hover:text-purple-800 font-medium text-sm cursor-pointer">
                    <i class="fa fa-brain mr-2"></i>
                    <span>深度思考过程</span>
                    <i id="${thinkingId}-icon" class="fa fa-chevron-down ml-2 transition-transform"></i>
                </button>
                <div id="${thinkingId}" class="hidden mt-2 text-sm text-gray-600 space-y-2">
                    ${renderThinkingProcess(thinkingProcess)}
                </div>
            </div>
        `;
    }

    // 添加最终回复内容
    if (useMarkdown && role === 'assistant') {
        htmlContent += `<div>${markdownToHtml(content)}</div>`;
    } else {
        htmlContent += `<div>${content}</div>`;
    }

    bubble.innerHTML = htmlContent;
    messageDiv.appendChild(bubble);
    chatMessages.appendChild(messageDiv);

    // 滚动到底部
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    // 更新消息计数
    messageCount++;
    updateMessageStats();
}

// 渲染深度思考过程
function renderThinkingProcess(thinkingProcess) {
    let html = '';
    
    // 渲染搜索步骤
    if (thinkingProcess.search_steps && thinkingProcess.search_steps.length > 0) {
        html += '<div class="space-y-1">';
        thinkingProcess.search_steps.forEach((step, index) => {
            html += `
                <div class="flex items-start">
                    <span class="text-purple-500 mr-2">${index + 1}.</span>
                    <span>${escapeHtml(step)}</span>
                </div>
            `;
        });
        html += '</div>';
    }
    
    // 渲染搜索结果
    if (thinkingProcess.search_results && thinkingProcess.search_results.length > 0) {
        html += '<div class="mt-2 pt-2 border-t border-gray-200">';
        html += '<div class="text-xs text-gray-500 mb-1">📚 参考来源：</div>';
        html += '<ul class="list-disc list-inside space-y-1">';
        thinkingProcess.search_results.slice(0, 3).forEach(result => {
            const title = result.title || '未知来源';
            const url = result.url || '';
            html += `<li class="text-xs"><a href="${url}" target="_blank" class="text-blue-600 hover:underline">${escapeHtml(title)}</a></li>`;
        });
        html += '</ul></div>';
    }
    
    // 渲染推理链
    if (thinkingProcess.reasoning_chain && thinkingProcess.reasoning_chain.length > 0) {
        html += '<div class="mt-2 pt-2 border-t border-gray-200">';
        html += '<div class="text-xs text-gray-500 mb-1">🔗 推理链路：</div>';
        html += '<div class="space-y-1">';
        thinkingProcess.reasoning_chain.forEach((step, index) => {
            html += `
                <div class="flex items-start text-xs">
                    <i class="fa fa-arrow-right text-purple-400 mr-2 mt-0.5"></i>
                    <span>${escapeHtml(step)}</span>
                </div>
            `;
        });
        html += '</div></div>';
    }
    
    return html || '<div class="text-gray-400 italic">思考过程数据不可用</div>';
}

// HTML转义函数
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 切换思考过程显示/隐藏
function toggleThinking(thinkingId) {
    const element = document.getElementById(thinkingId);
    const icon = document.getElementById(thinkingId + '-icon');
    
    if (element && icon) {
        if (element.classList.contains('hidden')) {
            element.classList.remove('hidden');
            icon.style.transform = 'rotate(180deg)';
        } else {
            element.classList.add('hidden');
            icon.style.transform = 'rotate(0deg)';
        }
    }
}

// 简单的Markdown转HTML函数
function markdownToHtml(markdown) {
    let html = markdown;
    
    // 代码块
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="bg-gray-800 text-green-400 p-3 rounded-lg my-2 overflow-x-auto"><code>$2</code></pre>');
    
    // 行内代码
    html = html.replace(/`([^`]+)`/g, '<code class="bg-gray-200 text-red-600 px-1 rounded">$1</code>');
    
    // 粗体
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    
    // 斜体
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    
    // 列表
    html = html.replace(/^- (.+)$/gm, '<li class="ml-4">$1</li>');
    html = html.replace(/(<li.*<\/li>\n?)+/g, '<ul class="list-disc">$&</ul>');
    
    // 换行
    html = html.replace(/\n/g, '<br>');
    
    return html;
}

// 更新消息统计
function updateMessageStats() {
    const statsElement = document.getElementById('message-stats');
    if (statsElement) {
        statsElement.textContent = `${messageCount} 条消息`;
    }
}

// 打字机效果
function showTypingEffect(text) {
    const chatMessages = document.getElementById('chat-messages');
    if (!chatMessages) return;
    
    const messageDiv = document.createElement('div');
    messageDiv.className = 'flex message-animation';
    
    const typingId = 'typing-' + Date.now();
    messageDiv.innerHTML = `
        <div class="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full flex items-center justify-center mr-3 flex-shrink-0">
            <i class="fa fa-robot text-white"></i>
        </div>
        <div class="bg-white rounded-2xl rounded-tl-none p-4 max-w-[80%] shadow-md border border-gray-100">
            <div id="${typingId}" class="typing-cursor text-gray-800 leading-relaxed"></div>
        </div>
    `;
    
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    const typingElement = document.getElementById(typingId);
    let index = 0;
    const speed = 20; // 打字速度（毫秒）
    
    function typeWriter() {
        if (index < text.length) {
            typingElement.textContent += text.charAt(index);
            index++;
            setTimeout(typeWriter, speed);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        } else {
            // 打字完成，替换为Markdown渲染
            typingElement.classList.remove('typing-cursor');
            if (typeof marked !== 'undefined' && marked.parse) {
                typingElement.innerHTML = marked.parse(text);
            } else {
                typingElement.innerHTML = markdownToHtml(text);
            }
        }
    }
    
    typeWriter();
}

// 显示加载动画
function showLoading() {
    const chatMessages = document.getElementById('chat-messages');
    if (!chatMessages) return;
    
    const loadingDiv = document.createElement('div');
    loadingDiv.id = 'loading-indicator';
    loadingDiv.className = 'flex message-animation';
    loadingDiv.innerHTML = `
        <div class="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full flex items-center justify-center mr-3 flex-shrink-0">
            <i class="fa fa-robot text-white"></i>
        </div>
        <div class="bg-white rounded-2xl rounded-tl-none p-4 shadow-md border border-gray-100">
            <div class="loading-dots">
                <span class="w-2 h-2 bg-gray-400 rounded-full inline-block"></span>
                <span class="w-2 h-2 bg-gray-400 rounded-full inline-block"></span>
                <span class="w-2 h-2 bg-gray-400 rounded-full inline-block"></span>
            </div>
        </div>
    `;
    chatMessages.appendChild(loadingDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// 隐藏加载动画
function hideLoading() {
    const loadingIndicator = document.getElementById('loading-indicator');
    if (loadingIndicator) {
        loadingIndicator.remove();
    }
}

// 发送消息
function sendMessage() {
    const messageInput = document.getElementById('message-input');
    if (!messageInput) return;
    
    let message = messageInput.value.trim();
    
    if (message) {
        // 处理快捷指令
        message = processQuickCommands(message);
        
        addMessage('user', message, false);
        messageInput.value = '';
        responseStartTime = Date.now();
        
        // ✅ 保存用户消息到历史记录
        MessageHistory.add('user', message);
        
        showLoading();

        // 获取当前选中的Agent
        const agentId = getCurrentAgentId();
        const isGroupMode = isGroupModeEnabled();
        
        // 根据是否是组模式选择不同的API端点
        const apiUrl = isGroupMode ? `${API_BASE}/api/agent-groups/current/execute` : `${API_BASE}/api/chat`;
        
        // 构建请求体
        const requestBody = isGroupMode ? {
            message: message
        } : {
            message: message,
            user_id: 1,
            agent_id: agentId
        };

        // 直接使用HTTP请求（WebSocket暂时禁用）
        fetch(apiUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        })
        .then(response => response.json())
        .then(data => {
            hideLoading();
            
            // 检查是否有深度思考过程
            if (data.thinking_process && Object.keys(data.thinking_process).length > 0) {
                addMessageWithThinking('assistant', data.reply, data.thinking_process);
            } else {
                showTypingEffect(data.reply);
            }
            
            // ✅ 保存AI回复到历史记录
            MessageHistory.add('assistant', data.reply);
            
            // 更新响应时间统计
            if (responseStartTime) {
                const responseTime = Date.now() - responseStartTime;
                updateResponseTimeStats(responseTime);
            }
        })
        .catch(error => {
            hideLoading();
            console.error('发送消息失败:', error);
            addMessage('assistant', '抱歉，发送消息失败，请重试');
        });
    }
}

// 处理快捷指令
function processQuickCommands(message) {
    const commands = {
        '/天气': '帮我查询今天的天气',
        '/翻译': '请帮我翻译以下内容',
        '/分析': '请帮我分析以下内容',
        '/思考': '请深度思考以下问题',
        '/爬虫': '帮我从网上抓取一些数据',
        '/自动化': '帮我自动化完成这个任务'
    };
    
    for (const [command, replacement] of Object.entries(commands)) {
        if (message.startsWith(command)) {
            const content = message.substring(command.length).trim();
            if (content) {
                return replacement + '：' + content;
            } else {
                return replacement;
            }
        }
    }
    
    return message;
}

// ==================== 快捷指令自动补全 ====================
const QuickCommandAutocomplete = {
    commands: {
        '/天气': '帮我查询今天的天气',
        '/翻译': '请帮我翻译以下内容',
        '/分析': '请帮我分析以下内容',
        '/思考': '请深度思考以下问题',
        '/爬虫': '帮我从网上抓取一些数据',
        '/自动化': '帮我自动化完成这个任务',
        '/总结': '请总结以下内容',
        '/解释': '请解释以下概念',
        '/代码': '请帮我编写代码',
        '/优化': '请帮我优化这段代码'
    },
    
    // 初始化自动补全
    init() {
        const input = document.getElementById('message-input');
        if (!input) return;
        
        // 创建补全提示框
        this.createSuggestionBox();
        
        // 监听输入事件
        input.addEventListener('input', (e) => this.handleInput(e));
        input.addEventListener('keydown', (e) => this.handleKeydown(e));
        
        // 点击外部关闭提示框
        document.addEventListener('click', (e) => {
            if (!e.target.closest('#message-input') && !e.target.closest('.autocomplete-suggestions')) {
                this.hideSuggestions();
            }
        });
    },
    
    // 创建补全提示框
    createSuggestionBox() {
        const box = document.createElement('div');
        box.className = 'autocomplete-suggestions';
        box.style.cssText = `
            position: absolute;
            bottom: 100%;
            left: -50px;
            right: -50px;
            min-width: 400px;
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            box-shadow: 0 -4px 6px -1px rgba(0, 0, 0, 0.1);
            max-height: 300px;
            overflow-y: auto;
            z-index: 1000;
            display: none;
        `;
        
        const inputContainer = document.getElementById('message-input')?.parentElement;
        if (inputContainer) {
            inputContainer.style.position = 'relative';
            inputContainer.appendChild(box);
        }
    },
    
    // 处理输入事件
    handleInput(e) {
        const value = e.target.value;
        
        // 检查是否以 / 开头
        if (value.startsWith('/')) {
            const matches = this.getMatches(value);
            if (matches.length > 0) {
                this.showSuggestions(matches);
            } else {
                this.hideSuggestions();
            }
        } else {
            this.hideSuggestions();
        }
    },
    
    // 处理键盘事件
    handleKeydown(e) {
        const suggestions = document.querySelector('.autocomplete-suggestions');
        if (!suggestions || suggestions.style.display === 'none') return;
        
        const items = suggestions.querySelectorAll('.suggestion-item');
        const activeIndex = Array.from(items).findIndex(item => item.classList.contains('active'));
        
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            this.navigateSuggestions(items, activeIndex, 1);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            this.navigateSuggestions(items, activeIndex, -1);
        } else if (e.key === 'Tab' || e.key === 'Enter') {
            if (activeIndex >= 0) {
                e.preventDefault();
                this.selectSuggestion(items[activeIndex]);
            }
        } else if (e.key === 'Escape') {
            this.hideSuggestions();
        }
    },
    
    // 获取匹配的指令
    getMatches(input) {
        const prefix = input.toLowerCase();
        return Object.entries(this.commands)
            .filter(([cmd]) => cmd.toLowerCase().startsWith(prefix))
            .map(([cmd, desc]) => ({ command: cmd, description: desc }));
    },
    
    // 显示建议列表
    showSuggestions(matches) {
        const box = document.querySelector('.autocomplete-suggestions');
        if (!box) return;
        
        box.innerHTML = matches.map((match, index) => `
            <div class="suggestion-item ${index === 0 ? 'active' : ''}" 
                 data-command="${match.command}"
                 style="padding: 10px 15px; cursor: pointer; border-bottom: 1px solid #f3f4f6;">
                <div style="font-weight: 500; color: #3b82f6;">${match.command}</div>
                <div style="font-size: 12px; color: #6b7280; margin-top: 2px;">${match.description}</div>
            </div>
        `).join('');
        
        // 添加点击事件
        box.querySelectorAll('.suggestion-item').forEach(item => {
            item.addEventListener('click', () => this.selectSuggestion(item));
            item.addEventListener('mouseenter', () => {
                box.querySelectorAll('.suggestion-item').forEach(i => i.classList.remove('active'));
                item.classList.add('active');
            });
        });
        
        box.style.display = 'block';
    },
    
    // 隐藏建议列表
    hideSuggestions() {
        const box = document.querySelector('.autocomplete-suggestions');
        if (box) {
            box.style.display = 'none';
        }
    },
    
    // 导航建议（上下箭头）
    navigateSuggestions(items, currentIndex, direction) {
        if (items.length === 0) return;
        
        let newIndex = currentIndex + direction;
        if (newIndex < 0) newIndex = items.length - 1;
        if (newIndex >= items.length) newIndex = 0;
        
        items.forEach((item, index) => {
            item.classList.toggle('active', index === newIndex);
        });
        
        // 滚动到可见区域
        items[newIndex].scrollIntoView({ block: 'nearest' });
    },
    
    // 选择建议
    selectSuggestion(item) {
        const command = item.dataset.command;
        const input = document.getElementById('message-input');
        if (input) {
            input.value = command + ' ';
            input.focus();
        }
        this.hideSuggestions();
    }
};

// ==================== Agent 选择器功能 ====================

// 获取当前选中的 Agent ID
function getCurrentAgentId() {
    const selector = document.getElementById('agent-selector');
    if (selector) {
        return selector.value;
    }
    return currentAgentId;
}

// 检查是否启用组模式
function isGroupModeEnabled() {
    const toggle = document.getElementById('group-mode-toggle');
    return toggle && toggle.checked;
}

// 更新 Agent 能力标签
function updateAgentCapabilities(agentId) {
    const container = document.getElementById('agent-capabilities');
    if (!container) return;
    
    const agentConfig = AGENT_CONFIG[agentId];
    if (!agentConfig) return;
    
    // 更新全局 Agent 信息
    currentAgentInfo = {
        id: agentId,
        name: agentConfig.name,
        description: agentConfig.description,
        capabilities: agentConfig.capabilities
    };
    
    // 创建能力标签
    let html = '<span class="text-xs text-gray-400">能力:</span>';
    agentConfig.capabilities.forEach((cap, index) => {
        const colors = ['bg-blue-100 text-blue-700', 'bg-green-100 text-green-700', 'bg-purple-100 text-purple-700', 'bg-orange-100 text-orange-700', 'bg-pink-100 text-pink-700'];
        const color = colors[index % colors.length];
        html += `<span class="inline-flex items-center gap-1 px-2 py-1 ${color} rounded-full text-xs">${cap}</span>`;
    });
    
    container.innerHTML = html;
}

// 处理 Agent 选择变更
function handleAgentChange(event) {
    const agentId = event.target.value;
    currentAgentId = agentId;
    updateAgentCapabilities(agentId);
    
    // 如果选择了智能匹配，显示提示
    if (agentId === 'auto') {
        showToast('✅ 将由系统智能选择最佳Agent');
    } else {
        const agentConfig = AGENT_CONFIG[agentId];
        if (agentConfig) {
            showToast(`✅ 已切换到 ${agentConfig.name}`);
        }
    }
}

// 处理组模式切换
function handleGroupModeChange(event) {
    const isEnabled = event.target.checked;
    const agentSelector = document.getElementById('agent-selector');
    
    if (isEnabled) {
        // 组模式启用时禁用 Agent 选择器
        agentSelector.disabled = true;
        agentSelector.classList.add('opacity-50', 'cursor-not-allowed');
        showToast('🔄 已切换到组模式');
        
        // 检查是否有选中的小组
        checkCurrentGroup();
    } else {
        // 组模式禁用时启用 Agent 选择器
        agentSelector.disabled = false;
        agentSelector.classList.remove('opacity-50', 'cursor-not-allowed');
        showToast('🔄 已切换到单 Agent 模式');
    }
}

// 检查当前选中的小组
async function checkCurrentGroup() {
    try {
        const response = await fetch(`${API_BASE}/api/agent-groups/current/selected`);
        const data = await response.json();
        
        if (!data.success || !data.data.group) {
            // 没有选中的小组，显示选择小组的提示
            showToast('⚠️ 请先选择一个 Agent 小组');
            // 自动关闭组模式
            const toggle = document.getElementById('group-mode-toggle');
            if (toggle) {
                toggle.checked = false;
                handleGroupModeChange({ target: toggle });
            }
        }
    } catch (error) {
        console.error('检查小组状态失败:', error);
    }
}

// 从后端加载 Agent 列表
async function loadAgentList() {
    try {
        const response = await fetch(`${API_BASE}/api/agents`);
        const data = await response.json();
        
        if (data.success && data.data) {
            const selector = document.getElementById('agent-selector');
            if (selector) {
                // 清空现有选项（保留智能匹配）
                const autoOption = selector.querySelector('option[value="auto"]');
                selector.innerHTML = '';
                
                // 添加智能匹配选项
                const autoOpt = document.createElement('option');
                autoOpt.value = 'auto';
                autoOpt.textContent = '🤖 智能匹配';
                autoOpt.dataset.description = '让系统智能选择最佳Agent';
                selector.appendChild(autoOpt);
                
                // 添加后端返回的 Agent
                data.data.forEach(agent => {
                    const option = document.createElement('option');
                    option.value = agent.id;
                    option.textContent = agent.name;
                    option.dataset.description = agent.description;
                    selector.appendChild(option);
                });
                
                // 更新 AGENT_CONFIG
                data.data.forEach(agent => {
                    AGENT_CONFIG[agent.id] = {
                        name: agent.name,
                        description: agent.description,
                        capabilities: agent.capabilities || []
                    };
                });
            }
        }
    } catch (error) {
        console.error('加载 Agent 列表失败:', error);
    }
}

// 在 DOMContentLoaded 中初始化
document.addEventListener('DOMContentLoaded', () => {
    QuickCommandAutocomplete.init();
    
    // 初始化 Agent 选择器
    const agentSelector = document.getElementById('agent-selector');
    if (agentSelector) {
        agentSelector.addEventListener('change', handleAgentChange);
        // 初始化能力标签
        updateAgentCapabilities(agentSelector.value);
    }
    
    // 初始化组模式开关
    const groupToggle = document.getElementById('group-mode-toggle');
    if (groupToggle) {
        groupToggle.addEventListener('change', handleGroupModeChange);
    }
    
    // 尝试从后端加载 Agent 列表
    loadAgentList();
});

// 更新响应时间统计
function updateResponseTimeStats(responseTime) {
    const statsElement = document.getElementById('response-time-stats');
    if (statsElement) {
        const avgTime = Math.round(responseTime / 1000 * 10) / 10;
        statsElement.textContent = `平均响应时间: ${avgTime}s`;
    }
}

// 快捷指令
function sendQuickCommand(command) {
    const messageInput = document.getElementById('message-input');
    if (messageInput) {
        messageInput.value = command;
        sendMessage();
    }
}

// 清空聊天
function clearChat() {
    if (confirm('确定要清空所有聊天记录吗？')) {
        const chatMessages = document.getElementById('chat-messages');
        if (chatMessages) {
            chatMessages.innerHTML = '';
            messageCount = 0;
            updateMessageStats();
            alert('✅ 聊天记录已清空');
        }
    }
}

// 导出对话
function exportChat() {
    const chatMessages = document.getElementById('chat-messages');
    if (!chatMessages) return;
    
    let exportText = '=== AI 对话记录 ===\n\n';
    exportText += `导出时间: ${new Date().toLocaleString()}\n\n`;
    exportText += '---\n\n';
    
    const messages = chatMessages.querySelectorAll('.flex');
    messages.forEach(msg => {
        const isUser = msg.classList.contains('justify-end');
        const textElement = msg.querySelector('.bg-white, .bg-gradient-to-r');
        if (textElement) {
            const role = isUser ? '我' : 'AI';
            const text = textElement.textContent.trim();
            exportText += `${role}: ${text}\n\n`;
        }
    });
    
    // 创建下载链接
    const blob = new Blob([exportText], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `chat_${new Date().toISOString().slice(0,10)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    
    alert('✅ 对话已导出为文本文件');
}

// HTML转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 导航切换
function switchTab(tabName) {
    console.log('切换到标签页:', tabName);
    currentCharacter = tabName;
    
    // 隐藏所有页面
    document.querySelectorAll('.page-section').forEach(section => {
        section.classList.add('hidden');
    });
    
    // 显示目标页面
    const targetSection = document.getElementById(tabName);
    if (targetSection) {
        targetSection.classList.remove('hidden');
    }
    
    // 工作流 iframe 动态加载
    if (tabName === 'workflow') {
        const iframe = document.getElementById('workflow-editor-frame');
        if (iframe && !iframe.src) {
            const apiBase = window.location.port === '5500' ? 'http://localhost:8001' : window.location.origin;
            iframe.src = `${apiBase}/workflow_editor`;
        }
    }
    
    // 更新导航按钮状态
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.remove('active', 'bg-blue-100', 'text-blue-600');
        btn.classList.add('text-gray-600');
    });
    
    const activeBtn = document.querySelector(`.nav-btn[data-page="${tabName}"]`);
    if (activeBtn) {
        activeBtn.classList.add('active', 'bg-blue-100', 'text-blue-600');
        activeBtn.classList.remove('text-gray-600');
    }
    
    // 如果是Agent小组页面,加载小组列表
    if (tabName === 'agent-group') {
        loadAgentGroups();
    }
}

// 创建自定义技能
function createCustomSkill() {
    console.log('创建自定义技能');
    
    // 获取表单数据
    const inputs = document.querySelectorAll('#skill input, #skill textarea');
    const skillData = {};
    inputs.forEach(input => {
        const label = input.previousElementSibling?.textContent || '未命名';
        skillData[label] = input.value;
    });
    
    console.log('技能数据:', skillData);
    
    // 验证必填字段
    if (!skillData['技能名称'] || skillData['技能名称'].trim() === '') {
        alert('⚠️ 请输入技能名称');
        return;
    }
    
    if (!skillData['技能描述'] || skillData['技能描述'].trim() === '') {
        alert('⚠️ 请输入技能描述');
        return;
    }
    
    // 显示创建成功提示
    alert(`✅ 技能"${skillData['技能名称']}"创建成功！\n\n实际功能：\n1. 技能注册到系统\n2. 生成技能配置文件\n3. 添加到技能商店\n\n（此功能待后端支持）`);
    
    // 清空表单
    inputs.forEach(input => {
        if (input.tagName === 'INPUT' || input.tagName === 'TEXTAREA') {
            input.value = '';
        }
    });
}

// 创建新计划
function createNewPlan(event) {
    event.preventDefault();
    console.log('创建新计划');
    
    // 获取目标输入
    const form = event.target;
    const goalInput = form.querySelector('input[type="text"]');
    if (!goalInput || !goalInput.value.trim()) {
        alert('⚠️ 请输入你的目标');
        return;
    }
    
    const goal = goalInput.value.trim();
    console.log('计划目标:', goal);
    
    // 调用后端API创建计划
    fetch(`${API_BASE}/api/plans`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            goal: goal,
            user_id: 1
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert(`✅ 计划创建成功！\n\n目标：${goal}\n\n计划ID：${data.plan_id}`);
            goalInput.value = '';
            // 重新加载计划列表
            loadPlans();
        } else {
            alert('❌ 创建失败：' + data.detail);
        }
    })
    .catch(error => {
        console.error('创建计划失败:', error);
        alert('❌ 创建计划失败，请稍后重试');
    });
}

// 加载计划列表
function loadPlans() {
    console.log('加载计划列表...');
    
    // 加载计划统计数据
    fetch(`${API_BASE}/api/plans/stats`)
    .then(response => response.json())
    .then(stats => {
        // 更新统计数据
        const totalEl = document.querySelector('#plan .grid .bg-white:nth-child(1) .text-2xl');
        const inProgressEl = document.querySelector('#plan .grid .bg-white:nth-child(2) .text-2xl');
        const pendingEl = document.querySelector('#plan .grid .bg-white:nth-child(3) .text-2xl');
        
        if (totalEl) totalEl.textContent = stats.total || 0;
        if (inProgressEl) inProgressEl.textContent = stats.in_progress || 0;
        if (pendingEl) pendingEl.textContent = stats.pending || 0;
    })
    .catch(error => {
        console.error('加载计划统计失败:', error);
    });
    
    // 加载计划列表
    fetch(`${API_BASE}/api/plans?limit=50`)
    .then(response => response.json())
    .then(data => {
        const plansList = document.getElementById('plans-list');
        if (!plansList) return;
        
        // 清空现有内容（保留空状态提示）
        const emptyState = document.getElementById('empty-plans');
        plansList.innerHTML = '';
        if (emptyState) {
            plansList.appendChild(emptyState);
        }
        
        if (!data.plans || data.plans.length === 0) {
            if (emptyState) {
                emptyState.classList.remove('hidden');
            }
            return;
        }
        
        if (emptyState) {
            emptyState.classList.add('hidden');
        }
        
        // 渲染计划卡片
        data.plans.forEach(plan => {
            const statusClass = plan.status === '进行中' ? 'bg-green-100 text-green-700' :
                               plan.status === '已完成' ? 'bg-blue-100 text-blue-700' :
                               plan.status === '已暂停' ? 'bg-gray-100 text-gray-700' :
                               'bg-orange-100 text-orange-700';
            
            const progressColor = plan.progress >= 60 ? 'bg-blue-600' :
                                 plan.progress >= 30 ? 'bg-green-500' :
                                 'bg-orange-400';
            
            const card = document.createElement('div');
            card.className = 'plan-card bg-white rounded-xl shadow-md p-5 cursor-pointer hover:shadow-lg transition';
            card.setAttribute('data-status', plan.status);
            card.setAttribute('data-plan-id', plan.id);
            
            card.innerHTML = `
                <div class="flex justify-between items-start mb-3">
                    <div>
                        <h4 class="font-medium text-lg">${plan.name}</h4>
                        <p class="text-sm text-gray-500 mt-1">开始时间: ${plan.start_date || '未设置'}</p>
                    </div>
                    <span class="px-3 py-1 rounded-full text-xs font-medium ${statusClass}">${plan.status}</span>
                </div>
                <div class="mb-3">
                    <div class="flex justify-between text-sm text-gray-600 mb-1">
                        <span>进度</span>
                        <span class="font-semibold">${plan.progress}%</span>
                    </div>
                    <div class="w-full bg-gray-200 rounded-full h-2">
                        <div class="${progressColor} h-2 rounded-full" style="width: ${plan.progress}%"></div>
                    </div>
                </div>
                <div class="flex justify-between text-xs text-gray-500">
                    <span>预计完成: ${plan.end_date || '未设置'}</span>
                    <div class="flex gap-2">
                        <button class="text-blue-600 hover:underline" onclick="viewPlanDetails(event, '${plan.name.replace(/'/g, "\\'")}')">查看详情</button>
                        <button class="text-red-600 hover:underline" onclick="deletePlan(event, '${plan.name.replace(/'/g, "\\'")}')">删除</button>
                    </div>
                </div>
            `;
            
            plansList.appendChild(card);
        });
    })
    .catch(error => {
        console.error('加载计划列表失败:', error);
    });
}

// 查看计划详情
function viewPlanDetails(event, planName) {
    event.stopPropagation();
    console.log('查看计划详情:', planName);
    
    // 先通过名称查找计划ID
    const planCards = document.querySelectorAll('.plan-card');
    let planId = null;
    
    planCards.forEach(card => {
        if (card.querySelector('h4')?.textContent === planName) {
            planId = card.getAttribute('data-plan-id');
        }
    });
    
    if (!planId) {
        alert('❌ 未找到计划ID');
        return;
    }
    
    // 调用后端API获取计划详情
    fetch(`${API_BASE}/api/plans/${planId}`)
    .then(response => response.json())
    .then(data => {
        if (data.id) {
            let details = `📋 计划详情：${data.name}\n\n`;
            details += `目标：${data.goal}\n`;
            details += `状态：${data.status}\n`;
            details += `进度：${data.progress}%\n`;
            
            if (data.start_date) {
                details += `开始时间：${data.start_date}\n`;
            }
            if (data.end_date) {
                details += `预计完成：${data.end_date}\n`;
            }
            
            if (data.steps && data.steps.length > 0) {
                details += `\n计划步骤：\n`;
                data.steps.forEach((step, index) => {
                    details += `${index + 1}. ${step.description || step}\n`;
                });
            }
            
            alert(details);
        } else {
            alert(' 获取计划详情失败：' + data.detail);
        }
    })
    .catch(error => {
        console.error('获取计划详情失败:', error);
        alert('❌ 获取计划详情失败，请稍后重试');
    });
}

// 删除计划
function deletePlan(event, planName) {
    event.stopPropagation();
    
    if (confirm(`确定要删除计划"${planName}"吗？`)) {
        // 先通过名称查找计划ID
        const planCards = document.querySelectorAll('.plan-card');
        let planId = null;
        
        planCards.forEach(card => {
            if (card.querySelector('h4')?.textContent === planName) {
                planId = card.getAttribute('data-plan-id');
            }
        });
        
        if (!planId) {
            alert('❌ 未找到计划ID');
            return;
        }
        
        // 调用后端API删除计划
        fetch(`${API_BASE}/api/plans/${planId}`, {
            method: 'DELETE'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert(`✅ ${data.message}`);
                // 从DOM中移除该计划卡片
                const card = document.querySelector(`.plan-card[data-plan-id="${planId}"]`);
                if (card) {
                    card.remove();
                }
                // 重新加载计划列表
                loadPlans();
            } else {
                alert('❌ 删除失败：' + data.detail);
            }
        })
        .catch(error => {
            console.error('删除计划失败:', error);
            alert('❌ 删除计划失败，请稍后重试');
        });
    }
}

// 技能搜索和筛选
function filterSkills() {
    const searchTerm = document.getElementById('skill-search')?.value.toLowerCase() || '';
    const skillCards = document.querySelectorAll('.skill-card');
    let visibleCount = 0;
    
    skillCards.forEach(card => {
        const name = card.getAttribute('data-name').toLowerCase();
        const category = card.getAttribute('data-category').toLowerCase();
        const description = card.querySelector('p')?.textContent.toLowerCase() || '';
        
        const matchesSearch = name.includes(searchTerm) || 
                            category.includes(searchTerm) || 
                            description.includes(searchTerm);
        
        if (matchesSearch) {
            card.style.display = 'block';
            visibleCount++;
        } else {
            card.style.display = 'none';
        }
    });
    
    const countElement = document.getElementById('skill-count');
    if (countElement) countElement.textContent = visibleCount;
}

function filterByCategory(category) {
    const skillCards = document.querySelectorAll('.skill-card');
    let visibleCount = 0;
    
    // 更新按钮状态
    const buttons = document.querySelectorAll('#skill button[onclick^="filterByCategory"]');
    buttons.forEach(btn => {
        if (btn.textContent === category || (category === 'all' && btn.textContent === '全部')) {
            btn.className = 'px-4 py-2 rounded-lg text-sm bg-blue-600 text-white';
        } else {
            btn.className = 'px-4 py-2 rounded-lg text-sm border border-gray-200 hover:border-blue-400';
        }
    });
    
    skillCards.forEach(card => {
        if (category === 'all') {
            card.style.display = 'block';
            visibleCount++;
        } else {
            const cardCategory = card.getAttribute('data-category');
            if (cardCategory && cardCategory.includes(category)) {
                card.style.display = 'block';
                visibleCount++;
            } else {
                card.style.display = 'none';
            }
        }
    });
    
    const countElement = document.getElementById('skill-count');
    if (countElement) countElement.textContent = visibleCount;
}

// 计划筛选
function filterPlans(status) {
    const planCards = document.querySelectorAll('.plan-card');
    let visibleCount = 0;
    
    // 更新按钮状态
    const buttons = document.querySelectorAll('#plan button[onclick^="filterPlans"]');
    buttons.forEach(btn => {
        if (btn.textContent === status || (status === 'all' && btn.textContent === '全部')) {
            btn.className = 'px-4 py-2 rounded-lg text-sm bg-blue-600 text-white';
        } else {
            btn.className = 'px-4 py-2 rounded-lg text-sm border border-gray-200 hover:border-blue-400';
        }
    });
    
    planCards.forEach(card => {
        if (status === 'all') {
            card.classList.remove('hidden');
            visibleCount++;
        } else {
            const cardStatus = card.getAttribute('data-status');
            if (cardStatus === status) {
                card.classList.remove('hidden');
                visibleCount++;
            } else {
                card.classList.add('hidden');
            }
        }
    });
    
    // 显示/隐藏空状态提示
    const emptyState = document.getElementById('empty-plans');
    if (emptyState) {
        if (visibleCount === 0) {
            emptyState.classList.remove('hidden');
        } else {
            emptyState.classList.add('hidden');
        }
    }
}

// 代码模板
const codeTemplates = {
    web: '生成一个简单的个人主页网站，包含导航栏、个人介绍和项目展示',
    api: '创建一个REST API接口，支持用户注册、登录和数据查询功能',
    script: '编写一个Python脚本，自动整理下载文件夹中的文件，按类型分类',
    game: '开发一个简单的HTML5贪吃蛇游戏，支持键盘控制和分数统计'
};

function loadTemplate(type) {
    const textarea = document.getElementById('code-requirement');
    if (textarea && codeTemplates[type]) {
        textarea.value = codeTemplates[type];
        textarea.focus();
        console.log('加载模板:', type);
    }
}

function optimizeRequirement() {
    const textarea = document.getElementById('code-requirement');
    if (textarea && textarea.value.trim()) {
        console.log('优化需求描述');
        alert('✨ 智能优化功能\n\n实际功能：\n1. AI分析需求描述\n2. 补充缺失的技术细节\n3. 优化表达使其更清晰\n4. 添加必要的约束条件\n\n（此功能待后端支持）');
    } else {
        alert('⚠️ 请先输入需求描述');
    }
}

function clearRequirement() {
    const textarea = document.getElementById('code-requirement');
    if (textarea) {
        textarea.value = '';
        textarea.focus();
    }
}

function generateCode() {
    const textarea = document.getElementById('code-requirement');
    if (textarea && textarea.value.trim()) {
        console.log('生成代码');
        alert('🚀 代码生成中...\n\n实际功能：\n1. AI理解需求描述\n2. 生成对应代码\n3. 代码预览和编辑\n4. 下载和运行代码\n\n（此功能待后端支持）');
    } else {
        alert('⚠️ 请先输入需求描述');
    }
}

// ==================== Agent小组管理功能 ====================

// 打开新建小组模态框
function openCreateGroupModal() {
    console.log('打开新建小组模态框');
    const modal = document.getElementById('agent-group-modal');
    const modalTitle = document.getElementById('modal-title');
    const saveBtn = document.getElementById('save-group-btn');
    const groupNameInput = document.getElementById('group-name');
    
    // 重置表单
    modalTitle.innerHTML = '<i class="fa fa-users mr-2 text-blue-600"></i>新建Agent小组';
    saveBtn.textContent = '创建';
    groupNameInput.value = '';
    
    // 清空所有复选框
    document.querySelectorAll('.agent-member-checkbox').forEach(cb => {
        cb.checked = false;
    });
    
    // 重置选择框
    document.getElementById('scheduling-strategy').value = 'pipeline';
    document.getElementById('circuit-breaker').checked = false;
    document.getElementById('elastic-scaling').checked = false;
    
    // 显示模态框
    modal.classList.remove('hidden');
}

// 关闭小组模态框
function closeGroupModal() {
    console.log('关闭小组模态框');
    const modal = document.getElementById('agent-group-modal');
    modal.classList.add('hidden');
}

// 保存小组（创建或编辑）
async function saveGroup() {
    console.log('保存小组');
    const groupName = document.getElementById('group-name').value.trim();
    
    if (!groupName) {
        alert('请输入小组名称');
        return;
    }
    
    // 获取选中的成员并转换为后端需要的 agents 格式
    const memberIds = [];
    document.querySelectorAll('.agent-member-checkbox:checked').forEach(cb => {
        memberIds.push(cb.value);
    });
    
    if (memberIds.length === 0) {
        alert('请至少选择一个Agent成员');
        return;
    }

    // 从 availableAgents 中查找完整信息，构建 agents 数组
    const allAgents = [
        ...(agentGroupManager.availableAgents.character_agents || []),
        ...(agentGroupManager.availableAgents.tool_agents || [])
    ];
    const agents = memberIds.map(id => {
        const found = allAgents.find(a => a.agent_id === id);
        return found ? {
            agent_id: found.agent_id,
            agent_type: found.agent_type || 'tool',
            agent_name: found.agent_name || found.name || id,
            description: found.description || '',
            skills: found.skills || [],
            priority: 1.0,
            enabled: true
        } : { agent_id: id, agent_type: 'tool', agent_name: id, skills: [], priority: 1.0, enabled: true };
    });
    
    // 获取其他配置
    const strategy = document.getElementById('scheduling-strategy').value;
    const circuitBreaker = document.getElementById('circuit-breaker').checked;
    const elasticScaling = document.getElementById('elastic-scaling').checked;
    
    const saveBtn = document.getElementById('save-group-btn');
    const groupId = saveBtn.getAttribute('data-group-id');
    
    try {
        let response;
        let groupData;
        
        if (groupId) {
            // 编辑模式 - 更新现有小组
            console.log('更新小组:', groupId);
            response = await fetch(`${API_BASE}/api/agent-groups/${groupId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    name: groupName,
                    agents: agents,
                    strategy: strategy,
                    circuit_breaker: circuitBreaker,
                    elastic_scaling: elasticScaling
                })
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || '更新失败');
            }
            
            groupData = await response.json();
            console.log('小组更新成功:', groupData);
            
            // 清除编辑标记
            saveBtn.removeAttribute('data-group-id');
            
            // 关闭模态框
            closeGroupModal();
            
            // 重新加载小组列表
            await loadAgentGroups();
            
            // 显示成功提示
            alert(`✅ 小组"${groupName}"更新成功！\n\n成员: ${agents.map(a => a.agent_name).join(', ')}\n策略: ${groupData.strategy}\n熔断: ${circuitBreaker ? '开启' : '关闭'}\n弹性伸缩: ${elasticScaling ? '开启' : '关闭'}`);
        } else {
            // 创建模式 - 新建小组
            console.log('创建小组');
            response = await fetch(`${API_BASE}/api/agent-groups`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    name: groupName,
                    agents: agents,
                    strategy: strategy,
                    circuit_breaker: circuitBreaker,
                    elastic_scaling: elasticScaling
                })
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || '创建失败');
            }
            
            groupData = await response.json();
            console.log('小组创建成功:', groupData);
            
            // 关闭模态框
            closeGroupModal();
            
            // 重新加载小组列表
            await loadAgentGroups();
            
            // 显示成功提示
            alert(`✅ 小组"${groupName}"创建成功！\n\n成员: ${agents.map(a => a.agent_name).join(', ')}\n策略: ${groupData.strategy}\n熔断: ${circuitBreaker ? '开启' : '关闭'}\n弹性伸缩: ${elasticScaling ? '开启' : '关闭'}`);
        }
    } catch (error) {
        console.error('保存小组失败:', error);
        alert(`❌ 保存小组失败: ${error.message}`);
    }
}

// 加载Agent小组列表
async function loadAgentGroups() {
    try {
        const response = await fetch(`${API_BASE}/api/agent-groups`);
        if (!response.ok) {
            throw new Error('获取小组列表失败');
        }

        const data = await response.json();
        console.log('获取到Agent小组列表:', data);

        // 清空现有列表 - 使用正确的元素ID
        const grid = document.getElementById('agent-groups-list');
        if (!grid) {
            console.error('找不到 agent-groups-list 元素');
            return;
        }
        grid.innerHTML = '';

        // 添加小组卡片
        if (data.groups && data.groups.length > 0) {
            data.groups.forEach(group => {
                addGroupCardToGrid(group);
            });
        } else {
            grid.innerHTML = '<p class="text-gray-500 text-center py-8">暂无Agent小组，点击上方按钮创建一个吧！</p>';
        }
    } catch (error) {
        console.error('加载Agent小组列表失败:', error);
    }
}

// 添加小组卡片到网格
function addGroupCardToGrid(groupData) {
    const grid = document.getElementById('agent-groups-list');
    if (!grid) {
        console.error('找不到 agent-groups-list 元素');
        return;
    }
    
    const statusConfig = {
        '运行中': { bg: 'bg-green-100', text: 'text-green-800', dot: 'bg-green-500', button: 'bg-gray-100 text-gray-700 hover:bg-gray-200', buttonText: '停止小组', action: 'stop' },
        '休眠': { bg: 'bg-yellow-100', text: 'text-yellow-800', dot: 'bg-yellow-500', button: 'bg-blue-600 text-white hover:bg-blue-700', buttonText: '启动小组', action: 'start' },
        '离线': { bg: 'bg-gray-100', text: 'text-gray-800', dot: 'bg-gray-500', button: 'bg-blue-600 text-white hover:bg-blue-700', buttonText: '启动小组', action: 'start' }
    };
    
    const config = statusConfig[groupData.status] || statusConfig['离线'];
    
    const card = document.createElement('div');
    card.className = 'agent-group-card bg-white rounded-xl shadow-md overflow-hidden hover:shadow-lg transition';
    card.setAttribute('data-group-id', groupData.id);
    card.innerHTML = `
        <div class="p-5">
            <div class="flex items-start justify-between mb-3">
                <div>
                    <h3 class="font-semibold text-gray-800">${groupData.name}</h3>
                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${config.bg} ${config.text}">
                        <span class="w-2 h-2 ${config.dot} rounded-full mr-1.5"></span>${groupData.status}
                    </span>
                </div>
                <div class="flex space-x-1">
                    <button class="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition" title="编辑" onclick="openEditGroupModal('${groupData.id}')">
                        <i class="fa fa-pencil"></i>
                    </button>
                    <button class="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition" title="删除" onclick="deleteGroup('${groupData.id}', '${groupData.name}')">
                        <i class="fa fa-trash"></i>
                    </button>
                </div>
            </div>
            
            <div class="space-y-3">
                <div class="flex items-center text-sm text-gray-600">
                    <i class="fa fa-users mr-2 text-gray-400"></i>
                    <span>成员: ${groupData.agents ? groupData.agents.map(a => a.agent_name || a.agent_id).join(', ') : ''}</span>
                </div>
                <div class="flex items-center text-sm text-gray-600">
                    <i class="fa fa-random mr-2 text-gray-400"></i>
                    <span>策略: ${groupData.strategy}</span>
                </div>
                <div class="flex items-center text-sm text-gray-600">
                    <i class="fa fa-shield mr-2 text-gray-400"></i>
                    <span>熔断: ${groupData.circuit_breaker ? '开启' : '关闭'}</span>
                </div>
                <div class="flex items-center text-sm text-gray-600">
                    <i class="fa fa-expand mr-2 text-gray-400"></i>
                    <span>弹性伸缩: ${groupData.elastic_scaling ? '开启' : '关闭'}</span>
                </div>
            </div>
            
            <div class="mt-4 pt-4 border-t border-gray-100">
                <button class="w-full py-2 ${config.button} transition text-sm" onclick="toggleGroupStatus('${groupData.id}', '${config.action}', '${groupData.name}')">
                    ${config.buttonText}
                </button>
            </div>
        </div>
    `;
    
    grid.appendChild(card);
}

// 删除小组
async function deleteGroup(groupId, groupName) {
    console.log('删除小组:', groupName, 'ID:', groupId);
    
    if (!confirm(`确定要删除小组"${groupName}"吗？此操作不可恢复。`)) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/api/agent-groups/${groupId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || '删除失败');
        }
        
        const result = await response.json();
        console.log('删除成功:', result);
        
        alert(`✅ ${result.message}`);
        
        // 重新加载小组列表
        await loadAgentGroups();
    } catch (error) {
        console.error('删除小组失败:', error);
        alert(`❌ 删除小组失败: ${error.message}`);
    }
}

// 打开编辑小组模态框
async function openEditGroupModal(groupId) {
    console.log('打开编辑小组模态框, ID:', groupId);
    
    try {
        // 获取小组详情
        const response = await fetch(`${API_BASE}/api/agent-groups/${groupId}`);
        if (!response.ok) {
            throw new Error('获取小组详情失败');
        }
        
        const groupData = await response.json();
        console.log('小组详情:', groupData);
        
        const modal = document.getElementById('agent-group-modal');
        const modalTitle = document.getElementById('modal-title');
        const saveBtn = document.getElementById('save-group-btn');
        const groupNameInput = document.getElementById('group-name');
        
        // 设置编辑模式
        modalTitle.innerHTML = '<i class="fa fa-pencil mr-2 text-blue-600"></i>编辑Agent小组';
        saveBtn.textContent = '保存';
        saveBtn.setAttribute('data-group-id', groupId); // 保存ID用于更新
        groupNameInput.value = groupData.name;
        
        // 设置成员复选框
        document.querySelectorAll('.agent-member-checkbox').forEach(cb => {
            cb.checked = groupData.agents && groupData.agents.some(a => a.agent_id === cb.value);
        });
        
        // 设置调度策略
        const strategyMap = {
            '流水线模式': 'pipeline',
            '并行评审': 'parallel_review',
            '主从模式': 'master_slave',
            '动态拍卖': 'dynamic_auction'
        };
        const strategyKey = Object.keys(strategyMap).find(key => strategyMap[key] === groupData.strategy);
        
        if (strategyKey) {
            document.getElementById('scheduling-strategy').value = strategyMap[strategyKey];
        }
        
        // 设置开关
        document.getElementById('circuit-breaker').checked = groupData.circuit_breaker;
        document.getElementById('elastic-scaling').checked = groupData.elastic_scaling;
        
        // 显示模态框
        modal.classList.remove('hidden');
    } catch (error) {
        console.error('加载小组详情失败:', error);
        alert(`❌ 加载小组详情失败: ${error.message}`);
    }
}

// 切换小组状态
async function toggleGroupStatus(groupId, action, groupName) {
    console.log('切换小组状态:', groupName, 'ID:', groupId, '操作:', action);
    
    const actionText = action === 'start' ? '启动' : '停止';
    
    if (!confirm(`确定要${actionText}小组"${groupName}"吗？`)) {
        return;
    }
    
    try {
        const endpoint = action === 'start' ? 'activate' : 'deactivate';
        const response = await fetch(`${API_BASE}/api/agent-groups/${groupId}/${endpoint}`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `${actionText}失败`);
        }
        
        const result = await response.json();
        console.log(`${actionText}成功:`, result);
        
        alert(`✅ ${result.message}`);
        
        // 重新加载小组列表
        await loadAgentGroups();
    } catch (error) {
        console.error(`${actionText}小组失败:`, error);
        alert(`❌ ${actionText}小组失败: ${error.message}`);
    }
}

// ==================== 事件监听器初始化 ====================
document.addEventListener('DOMContentLoaded', function() {
    // 页面切换事件
    const navButtons = document.querySelectorAll('.nav-btn');
    const pageSections = document.querySelectorAll('.page-section');

    // 导航按钮点击事件
    navButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const page = this.getAttribute('data-page');
            console.log('切换到页面:', page);
            switchTab(page);
        });
    });

    // 表单提交
    const chatForm = document.getElementById('chat-form');
    if (chatForm) {
        chatForm.addEventListener('submit', function(e) {
            e.preventDefault();
            console.log('表单提交，发送消息');
            sendMessage();
        });
    }

    // 导航切换
    const navItems = document.querySelectorAll('.nav-item');
    console.log('找到导航项数量:', navItems.length);
    navItems.forEach(item => {
        item.addEventListener('click', function(e) {
            e.preventDefault();
            const tabId = this.getAttribute('href').substring(1);
            console.log('点击导航项，切换到:', tabId);
            switchTab(tabId);
        });
    });

    // 快捷工具按钮点击事件
    const toolButtons = document.querySelectorAll('.coze-tool-btn');
    console.log('找到快捷工具按钮数量:', toolButtons.length);
    toolButtons.forEach(button => {
        button.addEventListener('click', function() {
            const toolName = this.textContent.trim();
            console.log('点击快捷工具按钮:', toolName);
            let command = '';
            
            switch(toolName) {
                case '写作':
                    command = '帮我写一篇关于人工智能的文章';
                    break;
                case 'PPT':
                    command = '帮我创建一个关于机器学习的PPT大纲';
                    break;
                case '设计':
                    command = '帮我设计一个网站logo';
                    break;
                case 'Excel':
                    command = '帮我创建一个销售数据表格';
                    break;
                case '网页':
                    command = '帮我设计一个个人网站';
                    break;
                case '音乐':
                    command = '帮我创作一首关于未来的歌曲';
                    break;
                case '视频':
                    command = '帮我制作一个产品介绍视频脚本';
                    break;
                default:
                    command = '帮我完成一个任务';
            }
            
            console.log('发送快捷命令:', command);
            sendQuickCommand(command);
        });
    });

    // 计划卡片点击事件
    const planCards = document.querySelectorAll('.plan-card');
    console.log('找到计划卡片数量:', planCards.length);
    planCards.forEach(card => {
        card.addEventListener('click', function() {
            const title = this.querySelector('h4').textContent;
            console.log('点击计划卡片:', title);
            let command = '';
            
            switch(title) {
                case '信息检索计划':
                    command = '帮我创建一个信息检索计划，使用爬虫和搜索引擎收集数据';
                    break;
                case '数据分析计划':
                    command = '帮我创建一个数据分析计划，处理数据并生成可视化报告';
                    break;
                case '翻译与总结计划':
                    command = '帮我创建一个翻译与总结计划，处理多语言文本并提取核心信息';
                    break;
                case '自动化任务计划':
                    command = '帮我创建一个自动化任务计划，使用GUI自动化执行重复性任务';
                    break;
                default:
                    command = '帮我创建一个计划';
            }
            
            console.log('发送计划命令:', command);
            sendQuickCommand(command);
        });
    });

    // 技能卡片点击事件
    const skillButtons = document.querySelectorAll('.skill-card button');
    console.log('找到技能按钮数量:', skillButtons.length);
    skillButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const skillCard = this.closest('.skill-card');
            const skillName = skillCard.querySelector('h4').textContent;
            const status = this.textContent.trim();
            
            console.log('点击技能:', skillName, '当前状态:', status);
            
            // 如果技能已启用，直接使用它
            if (status === '已启用') {
                const message = `请使用${skillName}技能帮我完成任务`;
                console.log('使用技能:', message);
                
                // 切换到聊天页面并使用该技能
                switchTab('chat');
                
                // 自动填充消息
                const messageInput = document.getElementById('message-input');
                if (messageInput) {
                    messageInput.value = message;
                    messageInput.focus();
                }
                
                // 显示提示
                alert(`✅ 已切换到聊天页面，请使用"${skillName}"技能\n\n示例消息已自动填充`);
            } else {
                // 如果技能未启用，显示启用提示
                alert(`🔧 技能"${skillName}"尚未启用\n\n请在聊天中使用该技能，系统会自动激活`);
            }
        });
    });

    // 代码编辑器运行按钮点击事件
    const runButtons = document.querySelectorAll('.fa-play');
    console.log('找到运行按钮数量:', runButtons.length);
    runButtons.forEach(icon => {
        const button = icon.closest('button');
        if (button) {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                console.log('点击运行按钮');
                
                // 获取代码内容
                const codeEditor = document.querySelector('textarea');
                if (codeEditor && codeEditor.value.trim()) {
                    const code = codeEditor.value.trim();
                    console.log('准备运行代码');
                    
                    // 显示运行中提示
                    alert('🔧 代码运行中...\n\n实际功能：\n1. 代码语法检查\n2. 代码执行测试\n3. 结果预览\n\n（此功能待后端支持）');
                } else {
                    alert('️ 请先在编辑器中输入代码需求');
                }
            });
        }
    });

    // 历史对话点击事件
    const historyItems = document.querySelectorAll('.history-session-item');
    console.log('找到历史对话数量:', historyItems.length);
    historyItems.forEach(item => {
        item.addEventListener('click', function() {
            const title = this.querySelector('h4').textContent;
            console.log('点击历史对话:', title);
            
            // 切换到聊天页面
            switchTab('chat');
            
            // 显示加载提示
            alert(`📜 加载历史对话：${title}\n\n实际功能：\n1. 从后端加载历史消息\n2. 显示完整对话内容\n3. 支持继续对话\n\n（此功能待后端支持）`);
        });
    });
});

// ==================== 文件上传和拖拽功能 ====================

// 全局变量：存储已上传的文件
let uploadedFiles = [];
const MAX_FILES = 5;

/**
 * 处理文件选择（通过点击按钮）
 */
function handleFileSelect(event) {
    const files = Array.from(event.target.files);
    processFiles(files);
}

/**
 * 处理文件（验证和上传）
 */
async function processFiles(files) {
    if (uploadedFiles.length + files.length > MAX_FILES) {
        alert(`⚠️ 最多只能上传${MAX_FILES}个文件，当前已有${uploadedFiles.length}个文件`);
        return;
    }
    
    for (const file of files) {
        // 验证文件大小（最大10MB）
        if (file.size > 10 * 1024 * 1024) {
            alert(`⚠️ 文件 "${file.name}" 超过10MB限制`);
            continue;
        }
        
        try {
            // 上传文件到服务器
            console.log(`📤 正在上传文件: ${file.name}`);
            const formData = new FormData();
            formData.append('file', file);
            
            const response = await fetch(`${API_BASE}/api/upload`, {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || '上传失败');
            }
            
            const result = await response.json();
            console.log(`✅ 文件上传成功: ${result.filename}`);
            
            // 将上传结果添加到已上传列表
            uploadedFiles.push({
                name: file.name,
                size: file.size,
                path: result.file_path,
                success: true
            });
            
        } catch (error) {
            console.error(`❌ 文件上传失败: ${file.name}`, error);
            alert(`❌ 文件 "${file.name}" 上传失败: ${error.message}`);
        }
    }
    
    // 更新UI
    updateUploadedFilesUI();
}

/**
 * 更新已上传文件的UI显示
 */
function updateUploadedFilesUI() {
    const container = document.getElementById('uploaded-files');
    
    if (uploadedFiles.length === 0) {
        container.classList.add('hidden');
        container.innerHTML = '';
        return;
    }
    
    container.classList.remove('hidden');
    container.innerHTML = uploadedFiles.map((file, index) => `
        <div class="flex items-center bg-blue-50 border border-blue-200 rounded-lg px-3 py-2 text-sm">
            <i class="fa fa-file-o text-blue-500 mr-2"></i>
            <span class="text-gray-700 truncate max-w-[150px]">${file.name}</span>
            <span class="text-gray-400 text-xs ml-2">(${formatFileSize(file.size)})</span>
            <button onclick="removeFile(${index})" class="ml-2 text-red-500 hover:text-red-700 transition">
                <i class="fa fa-times"></i>
            </button>
        </div>
    `).join('');
}

/**
 * 格式化文件大小
 */
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

/**
 * 移除已上传的文件
 */
function removeFile(index) {
    uploadedFiles.splice(index, 1);
    updateUploadedFilesUI();
    
    // 清空文件输入框
    document.getElementById('file-input').value = '';
}

/**
 * 初始化拖拽上传功能
 */
function initDragAndDrop() {
    // 修复：使用正确的选择器 - 主内容区域
    const chatArea = document.querySelector('.coze-main');
    const dropZone = document.getElementById('drop-zone');
    
    if (!chatArea || !dropZone) {
        console.warn('⚠️ 拖拽上传初始化失败：找不到必要的DOM元素');
        return;
    }
    
    let dragCounter = 0;
    
    // 拖拽进入
    chatArea.addEventListener('dragenter', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dragCounter++;
        
        if (dragCounter === 1) {
            dropZone.classList.remove('hidden');
            // 添加视觉反馈到主内容区域
            chatArea.classList.add('drag-over');
        }
    });
    
    // 拖拽悬停
    chatArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.stopPropagation();
    });
    
    // 拖拽离开
    chatArea.addEventListener('dragleave', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dragCounter--;
        
        if (dragCounter === 0) {
            dropZone.classList.add('hidden');
            chatArea.classList.remove('drag-over');
        }
    });
    
    // 放下文件
    chatArea.addEventListener('drop', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dragCounter = 0;
        dropZone.classList.add('hidden');
        chatArea.classList.remove('drag-over');
        
        const files = Array.from(e.dataTransfer.files);
        if (files.length > 0) {
            console.log(`📎 检测到 ${files.length} 个文件被拖拽`);
            processFiles(files);
        }
    });
    
    console.log('✅ 拖拽上传监听器已绑定到 .coze-main');
}

/**
 * 修改发送消息函数，包含文件信息
 */
const originalSendMessage = window.sendMessage;
if (originalSendMessage) {
    window.sendMessage = async function() {
        const messageInput = document.getElementById('message-input');
        if (!messageInput) return;
        
        let message = messageInput.value.trim();
        
        // 处理快捷指令
        message = processQuickCommands(message);
        
        if (!message && uploadedFiles.length === 0) {
            alert('⚠️ 请输入消息或上传文件');
            return;
        }
        
        // 如果有上传的文件，在请求中包含文件路径
        if (uploadedFiles.length > 0) {
            const file_paths = uploadedFiles.map(f => f.path);
            
            // 如果用户没有输入消息，但有文件，使用默认消息
            if (!message) {
                message = '请分析这个文件';
            }
            
            try {
                // 显示加载状态
                showLoading();
                
                // 添加用户消息到聊天界面
                addMessage('user', message, false);
                messageInput.value = '';
                responseStartTime = Date.now();
                
                // 发送包含文件路径的请求
                const response = await fetch(`${API_BASE}/api/chat`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        message: message,
                        user_id: 1,
                        agent_id: currentCharacter,
                        file_paths: file_paths
                    })
                });
                
                if (!response.ok) {
                    const errorData = await response.json();
                    console.error('API 错误:', errorData);
                    throw new Error(errorData.detail || `HTTP ${response.status}`);
                }
                
                const data = await response.json();
                
                // 隐藏加载状态
                hideLoading();
                
                // 显示回复
                showTypingEffect(data.reply);
                
                // 更新响应时间统计
                if (responseStartTime) {
                    const responseTime = Date.now() - responseStartTime;
                    updateResponseTimeStats(responseTime);
                }
                
                // 发送后清空文件列表
                setTimeout(() => {
                    uploadedFiles = [];
                    updateUploadedFilesUI();
                    document.getElementById('file-input').value = '';
                }, 1000);
                
            } catch (error) {
                console.error('发送消息失败:', error);
                hideLoading();
                addMessage('assistant', `抱歉，发送消息失败：${error.message}`);
            }
        } else {
            // 没有文件时，调用原始发送函数
            return await originalSendMessage();
        }
    };
}

// 页面加载完成后初始化拖拽功能
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => {
        initDragAndDrop();
        console.log('✅ 文件拖拽上传功能已初始化');
    }, 1000);
});

// 暴露全局函数到window对象（遵循前端模块化规范）

// 核心对象
window.MessageHistory = MessageHistory;
window.UserPreferences = UserPreferences;

// 深度思考相关函数
window.toggleThinking = toggleThinking;
window.addMessageWithThinking = addMessageWithThinking;
window.renderThinkingProcess = renderThinkingProcess;

// 设置相关函数
window.openSettings = openSettings;
window.closeSettings = closeSettings;
window.setFontSize = setFontSize;
window.resetSettings = resetSettings;
window.setLanguage = typeof setLanguage !== 'undefined' ? setLanguage : function() {};
window.toggleSound = typeof toggleSound !== 'undefined' ? toggleSound : function() {};
window.toggleAutosave = typeof toggleAutosave !== 'undefined' ? toggleAutosave : function() {};
window.toggleLineNumbers = typeof toggleLineNumbers !== 'undefined' ? toggleLineNumbers : function() {};

// 计划管理相关函数
window.createNewPlan = createNewPlan;
window.filterPlans = filterPlans;
window.viewPlanDetails = viewPlanDetails;
window.deletePlan = deletePlan;
window.loadPlans = typeof loadPlans !== 'undefined' ? loadPlans : function() {};

// 技能管理相关函数
window.filterByCategory = typeof filterByCategory !== 'undefined' ? filterByCategory : function() {};
window.createCustomSkill = typeof createCustomSkill !== 'undefined' ? createCustomSkill : function() {};
window.filterSkills = typeof filterSkills !== 'undefined' ? filterSkills : function() {};

// Agent小组相关函数
window.showCreateGroupModal = typeof showCreateGroupModal !== 'undefined' ? showCreateGroupModal : function() {};

// 历史记录相关函数
window.searchHistory = typeof searchHistory !== 'undefined' ? searchHistory : function() {};
window.filterHistory = typeof filterHistory !== 'undefined' ? filterHistory : function() {};
window.exportHistory = typeof exportHistory !== 'undefined' ? exportHistory : function() {};
window.clearAllHistory = typeof clearAllHistory !== 'undefined' ? clearAllHistory : function() {};
window.showHistoryView = typeof showHistoryView !== 'undefined' ? showHistoryView : function() {};

// 代码生成相关函数
window.loadTemplate = typeof loadTemplate !== 'undefined' ? loadTemplate : function() {};
window.optimizeRequirement = typeof optimizeRequirement !== 'undefined' ? optimizeRequirement : function() {};
window.clearRequirement = typeof clearRequirement !== 'undefined' ? clearRequirement : function() {};
window.generateCode = typeof generateCode !== 'undefined' ? generateCode : function() {};

// 聊天相关函数
window.clearChat = typeof clearChat !== 'undefined' ? clearChat : function() {};
window.updateResponseTimeStats = typeof updateResponseTimeStats !== 'undefined' ? updateResponseTimeStats : function() {};
