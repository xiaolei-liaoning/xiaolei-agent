/**
 * Skill库管理模块
 * 动态加载和管理所有25个Skill
 */

// 完整的Skill列表（与后端REGISTERED_AGENTS一致）
const ALL_SKILLS = [
    {
        id: 'Calculator',
        name: '计算器',
        category: '基础工具',
        description: '安全的数学计算功能',
        icon: 'fa-calculator',
        tags: ['免费', '工具'],
        rating: 4.7,
        usageCount: 89,
        installed: true,
        enabled: true,
        details: '支持加减乘除和括号运算'
    },
    {
        id: 'weather',
        name: '天气查询',
        category: '基础工具',
        description: '全球城市天气和未来3天预报',
        icon: 'fa-cloud',
        tags: ['免费', '生活'],
        rating: 4.9,
        usageCount: 128,
        installed: true,
        enabled: true,
        details: '基于wttr.in API，无需Key'
    },
    {
        id: 'search_engine',
        name: '搜索引擎',
        category: '基础工具',
        description: '联网搜索和网页深度爬取',
        icon: 'fa-search',
        tags: ['免费', '信息'],
        rating: 4.6,
        usageCount: 72,
        installed: true,
        enabled: true,
        details: '支持RAG知识检索和Playwright深度爬取'
    },
    {
        id: 'Translator',
        name: '多语言翻译',
        category: '基础工具',
        description: '支持多语言互译，自动语言检测',
        icon: 'fa-language',
        tags: ['免费', '办公'],
        rating: 4.9,
        usageCount: 156,
        installed: true,
        enabled: true,
        details: '支持中文、英文、日文、韩文、法文等多语言'
    },
    {
        id: 'WebScraper',
        name: '网页爬虫',
        category: '数据处理',
        description: '多平台内容爬取和分析',
        icon: 'fa-spider',
        tags: ['免费', '数据'],
        rating: 4.8,
        usageCount: 96,
        installed: true,
        enabled: true,
        details: '支持微博、B站、知乎、抖音等热门平台'
    },
    {
        id: 'DataAnalysis',
        name: '数据分析',
        category: '数据处理',
        description: '数据统计分析和可视化',
        icon: 'fa-chart-bar',
        tags: ['免费', '分析'],
        rating: 4.7,
        usageCount: 87,
        installed: true,
        enabled: true,
        details: '支持统计、图表、词云、相关性分析'
    },
    {
        id: 'code_interpreter',
        name: '代码解释器',
        category: '开发工具',
        description: 'Python代码执行和可视化',
        icon: 'fa-code',
        tags: ['免费', '开发'],
        rating: 4.5,
        usageCount: 45,
        installed: true,
        enabled: true,
        details: '支持Python代码执行和结果可视化'
    },
    {
        id: 'system_toolbox',
        name: '系统工具箱',
        category: '系统工具',
        description: '系统信息查询和操作',
        icon: 'fa-wrench',
        tags: ['免费', '系统'],
        rating: 4.4,
        usageCount: 38,
        installed: true,
        enabled: true,
        details: '查询CPU、内存、磁盘、网络等系统信息'
    },
    {
        id: 'file_handler',
        name: '文件处理',
        category: '系统工具',
        description: '文件读写和处理功能',
        icon: 'fa-file',
        tags: ['免费', '文件'],
        rating: 4.3,
        usageCount: 32,
        installed: true,
        enabled: true,
        details: '支持文本文件读写和处理'
    },
    {
        id: 'DeepThinking',
        name: '深度思考',
        category: 'AI增强',
        description: '深度分析和推理',
        icon: 'fa-brain',
        tags: ['免费', '分析'],
        rating: 4.9,
        usageCount: 203,
        installed: true,
        enabled: true,
        details: '深度思考引擎集成，自主搜索，完整思考-搜索-验证闭环'
    },
    {
        id: 'RAGSearch',
        name: 'RAG知识检索',
        category: 'AI增强',
        description: '基于向量数据库的知识检索',
        icon: 'fa-database',
        tags: ['免费', '知识'],
        rating: 4.7,
        usageCount: 92,
        installed: true,
        enabled: true,
        details: '向量相似度搜索，相关知识召回'
    },
    {
        id: 'Checker',
        name: '检查器',
        category: '工具',
        description: '内容检查和验证',
        icon: 'fa-check-circle',
        tags: ['免费', '工具'],
        rating: 4.5,
        usageCount: 56,
        installed: true,
        enabled: true,
        details: '内容验证和检查功能'
    },
    {
        id: 'Scraper',
        name: '爬虫',
        category: '数据处理',
        description: '网页内容爬取',
        icon: 'fa-download',
        tags: ['免费', '数据'],
        rating: 4.6,
        usageCount: 68,
        installed: true,
        enabled: true,
        details: '灵活的网页内容爬取功能'
    },
    {
        id: 'Analyzer',
        name: '分析器',
        category: '数据处理',
        description: '数据深度分析',
        icon: 'fa-line-chart',
        tags: ['免费', '分析'],
        rating: 4.7,
        usageCount: 78,
        installed: true,
        enabled: true,
        details: '深度数据解析和分析功能'
    },
    {
        id: 'Processor',
        name: '处理器',
        category: '工具',
        description: '内容处理和转换',
        icon: 'fa-cogs',
        tags: ['免费', '工具'],
        rating: 4.4,
        usageCount: 43,
        installed: true,
        enabled: true,
        details: '内容处理和格式转换'
    },
    {
        id: 'Transformer',
        name: '转换器',
        category: '工具',
        description: '数据格式转换',
        icon: 'fa-exchange',
        tags: ['免费', '工具'],
        rating: 4.3,
        usageCount: 37,
        installed: true,
        enabled: true,
        details: '支持多种数据格式转换'
    },
    {
        id: 'Scanner',
        name: '扫描器',
        category: '工具',
        description: '内容扫描和检测',
        icon: 'fa-search',
        tags: ['免费', '工具'],
        rating: 4.4,
        usageCount: 49,
        installed: true,
        enabled: true,
        details: '内容扫描和特征检测'
    },
    {
        id: 'Vulnerability',
        name: '漏洞检测',
        category: '安全',
        description: '安全漏洞检测',
        icon: 'fa-shield',
        tags: ['免费', '安全'],
        rating: 4.6,
        usageCount: 53,
        installed: true,
        enabled: true,
        details: '安全漏洞扫描和检测功能'
    },
    {
        id: 'Summarizer',
        name: '摘要器',
        category: 'AI增强',
        description: '文本摘要和归纳',
        icon: 'fa-file-text',
        tags: ['免费', '文本'],
        rating: 4.5,
        usageCount: 62,
        installed: true,
        enabled: true,
        details: '智能文本摘要和归纳功能'
    }
];

// 当前已启用的技能
let enabledSkills = new Set(ALL_SKILLS.filter(s => s.enabled).map(s => s.id));

/**
 * 渲染技能卡片
 */
function renderSkillCard(skill) {
    const isEnabled = enabledSkills.has(skill.id);
    const statusClass = isEnabled ? 'bg-gray-600 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700';
    const statusText = isEnabled ? '已启用' : '启用';
    const statusIcon = isEnabled ? '✓ ' : '';
    
    return `
        <div class="skill-card bg-white rounded-xl shadow-md overflow-hidden transition-all duration-300 hover:shadow-lg" 
             data-category="${skill.tags.join(' ')}" 
             data-name="${skill.name}"
             data-id="${skill.id}">
            <div class="p-4">
                <div class="flex items-center justify-between mb-3">
                    <div class="flex items-center">
                        <i class="fa ${skill.icon} text-2xl text-blue-600 mr-3"></i>
                        <h4 class="font-medium">${skill.name}</h4>
                    </div>
                    <span class="text-xs text-green-600 font-medium">${skill.tags[0]}</span>
                </div>
                <p class="text-sm text-gray-600 mb-3">${skill.description}</p>
                <div class="flex items-center justify-between text-xs text-gray-500 mb-3">
                    <span>${isEnabled ? '✓ 已安装' : '○ 未安装'}</span>
                    <span>评分: ${skill.rating}</span>
                </div>
                <div class="flex items-center justify-between text-xs text-gray-500 mb-2">
                    <span class="text-blue-600">使用次数: ${skill.usageCount}</span>
                    <span class="text-purple-600">${skill.category}</span>
                </div>
                <button onclick="toggleSkill('${skill.id}')" 
                        class="w-full ${statusClass} text-white py-2 rounded-lg transition text-sm">
                    ${statusIcon}${statusText}
                </button>
            </div>
        </div>
    `;
}

/**
 * 渲染所有技能
 */
function renderAllSkills() {
    const skillsGrid = document.getElementById('skills-grid');
    if (!skillsGrid) return;
    
    skillsGrid.innerHTML = ALL_SKILLS.map(renderSkillCard).join('');
    updateSkillCount();
}

/**
 * 切换技能启用状态
 */
function toggleSkill(skillId) {
    if (enabledSkills.has(skillId)) {
        enabledSkills.delete(skillId);
        showToast(`已禁用技能`, 'info');
    } else {
        enabledSkills.add(skillId);
        showToast(`已启用技能`, 'success');
    }
    renderAllSkills();
    saveSkillPreferences();
}

/**
 * 更新技能计数
 */
function updateSkillCount() {
    const countElement = document.getElementById('skill-count');
    if (countElement) {
        countElement.textContent = ALL_SKILLS.length;
    }
}

/**
 * 保存技能偏好设置
 */
function saveSkillPreferences() {
    localStorage.setItem('enabledSkills', JSON.stringify([...enabledSkills]));
}

/**
 * 加载技能偏好设置
 */
function loadSkillPreferences() {
    const saved = localStorage.getItem('enabledSkills');
    if (saved) {
        try {
            enabledSkills = new Set(JSON.parse(saved));
        } catch (e) {
            console.error('加载技能偏好失败:', e);
        }
    }
}

/**
 * 过滤技能
 */
function filterSkills(searchTerm, category) {
    const cards = document.querySelectorAll('.skill-card');
    let visibleCount = 0;
    
    cards.forEach(card => {
        const name = card.dataset.name.toLowerCase();
        const categories = card.dataset.category.toLowerCase();
        const matchesSearch = !searchTerm || name.includes(searchTerm.toLowerCase());
        const matchesCategory = !category || category === 'all' || categories.includes(category.toLowerCase());
        
        if (matchesSearch && matchesCategory) {
            card.style.display = 'block';
            visibleCount++;
        } else {
            card.style.display = 'none';
        }
    });
    
    return visibleCount;
}

/**
 * 按分类过滤技能（供 HTML onclick 调用）
 */
function filterByCategory(category) {
    // 更新按钮状态
    const categoryFilters = document.querySelectorAll('.category-filter');
    categoryFilters.forEach(filter => {
        filter.classList.remove('active', 'bg-blue-600', 'text-white');
        filter.classList.add('bg-gray-200', 'text-gray-700');
        
        if (filter.dataset.category === category) {
            filter.classList.add('active', 'bg-blue-600', 'text-white');
            filter.classList.remove('bg-gray-200', 'text-gray-700');
        }
    });
    
    // 执行过滤
    const searchTerm = document.getElementById('skill-search')?.value || '';
    filterSkills(searchTerm, category);
}

/**
 * 创建自定义技能（占位函数）
 */
function createCustomSkill() {
    alert('自定义技能创建功能正在开发中...');
    // TODO: 实现自定义技能创建逻辑
}

/**
 * 初始化技能模块
 */
function initSkillsModule() {
    loadSkillPreferences();
    renderAllSkills();
    
    // 绑定搜索事件
    const searchInput = document.getElementById('skill-search');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            filterSkills(e.target.value, 'all');
        });
    }
    
    // 绑定分类过滤事件
    const categoryFilters = document.querySelectorAll('.category-filter');
    categoryFilters.forEach(filter => {
        filter.addEventListener('click', () => {
            const category = filter.dataset.category || 'all';
            categoryFilters.forEach(f => f.classList.remove('active'));
            filter.classList.add('active');
            filterSkills('', category);
        });
    });
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', initSkillsModule);

// 暴露全局函数到window对象（遵循前端模块化规范）
window.filterByCategory = filterByCategory;
window.createCustomSkill = createCustomSkill;
window.filterSkills = filterSkills;
