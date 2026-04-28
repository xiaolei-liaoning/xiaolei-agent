"""数据分析与可视化处理器（工业级 v3.4.0）

支持：描述性统计、柱状图、饼图、词云、折线图、对比分析、热力图、OCR文字识别
依赖：pandas, matplotlib(可选), wordcloud(可选), numpy(可选), paddleocr(可选)
"""

import os
import time
import json
import logging
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from datetime import datetime
from functools import lru_cache

# 导入pandas
import pandas as pd

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / 'output'


class DataAnalysisHandler:
    """数据分析处理器 - 支持多种统计分析和可视化图表。

    工业级特性：
    - 同步/异步双接口
    - matplotlib不可用时自动降级为文字报告
    - 统一图表命名规范：分析图表_YYYYMMDD_HHMMSS.png
    - 智能列类型识别（文本列/数值列）
    - 多级搜索路径查找CSV文件

    Attributes:
        output_dir: 图表输出目录
    """

    def __init__(self) -> None:
        """初始化数据分析处理器，自动创建输出目录。"""
        self.output_dir: Path = OUTPUT_DIR
        self.output_dir.mkdir(exist_ok=True)
        logger.info("DataAnalysisHandler 初始化完成, 输出目录: %s", self.output_dir)

    def execute(
        self,
        action: str = '描述性统计',
        file_path: Optional[str] = None,
        chart_type: str = 'bar',
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """执行数据分析操作（同步接口）。

        Args:
            action: 操作类型，支持：
                描述性统计/stats, 柱状图/bar, 饼图/pie,
                词云/wordcloud, 折线图/line/趋势,
                对比分析, 热力图/heatmap/相关性
            file_path: CSV文件路径，为空则自动查找最新CSV
            chart_type: 图表类型 bar/pie/line
            **kwargs: 额外参数

        Returns:
            Dict[str, Any]: 包含 success, action, reply 等字段的字典。
                图表类操作额外返回 chart_path。
        """
        start_time = time.perf_counter()
        try:
            result = self._do_execute(action, file_path, chart_type, **kwargs)
            elapsed = time.perf_counter() - start_time
            logger.info("数据分析完成 [%s], 耗时: %.3fs", action, elapsed)
            result.setdefault('_elapsed', round(elapsed, 3))
            return result
        except Exception as e:
            logger.error("数据分析异常 [%s]: %s", action, e, exc_info=True)
            return {'success': False, 'error': f'数据分析异常: {e}'}

    async def aexecute(
        self,
        action: str = '描述性统计',
        file_path: Optional[str] = None,
        chart_type: str = 'bar',
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """执行数据分析操作（异步接口）。

        与 execute 相同逻辑，以协程方式运行，适用于异步执行引擎。

        Args:
            action: 操作类型
            file_path: CSV文件路径
            chart_type: 图表类型
            **kwargs: 额外参数

        Returns:
            Dict[str, Any]: 分析结果
        """
        start_time = time.perf_counter()
        try:
            result = self._do_execute(action, file_path, chart_type, **kwargs)
            elapsed = time.perf_counter() - start_time
            logger.info("数据分析完成(异步) [%s], 耗时: %.3fs", action, elapsed)
            result.setdefault('_elapsed', round(elapsed, 3))
            return result
        except Exception as e:
            logger.error("数据分析异常(异步) [%s]: %s", action, e, exc_info=True)
            return {'success': False, 'error': f'数据分析异常: {e}'}

    def _do_execute(
        self,
        action: str,
        file_path: Optional[str],
        chart_type: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """核心执行逻辑，供同步/异步接口共用。"""
        if not file_path:
            file_path = self._find_latest_csv()
            if not file_path:
                return {'success': False, 'error': '未找到数据文件，请先爬取数据或指定文件路径'}

        # 根据文件类型加载
        file_ext = Path(file_path).suffix.lower()
        
        # OCR相关操作
        ocr_actions = ['ocr', 'OCR', '文字识别', '图片识别']
        if action in ocr_actions and file_ext in ('.jpg', '.jpeg', '.png', '.gif', '.bmp'):
            return self._ocr_recognition(file_path, **kwargs)
        
        if file_ext == '.csv':
            df = self._load_csv(file_path)
            if df is None:
                return {'success': False, 'error': '文件读取失败'}
            if df.empty:
                return {'success': False, 'error': '数据文件为空'}
        elif file_ext in ('.txt', '.md'):
            return self._analyze_text_file(file_path, action)
        elif file_ext in ('.jpg', '.jpeg', '.png', '.gif', '.bmp'):
            return self._analyze_image_file(file_path, action)
        elif file_ext in ('.doc', '.docx'):
            return self._analyze_word_file(file_path, action)
        else:
            return {'success': False, 'error': f'不支持的文件格式: {file_ext}'}

        action_map: Dict[str, Any] = {
            '描述性统计': lambda: self._descriptive_stats(df),
            '统计': lambda: self._descriptive_stats(df),
            'stats': lambda: self._descriptive_stats(df),
            '柱状图': lambda: self._create_bar_chart(df),
            'bar': lambda: self._create_bar_chart(df),
            '可视化': lambda: self._create_bar_chart(df),
            '图表': lambda: self._create_bar_chart(df),
            '饼图': lambda: self._create_pie_chart(df),
            'pie': lambda: self._create_pie_chart(df),
            '词云': lambda: self._create_wordcloud(df),
            'wordcloud': lambda: self._create_wordcloud(df),
            '折线图': lambda: self._create_line_chart(df),
            'line': lambda: self._create_line_chart(df),
            '趋势': lambda: self._create_line_chart(df),
            '对比分析': lambda: self._comparison_analysis(df),
            '热力图': lambda: self._heatmap(df),
            'heatmap': lambda: self._heatmap(df),
            '相关性': lambda: self._heatmap(df),
            'ocr': lambda: self._ocr_recognition(file_path),
            'OCR': lambda: self._ocr_recognition(file_path),
            '文字识别': lambda: self._ocr_recognition(file_path),
            '图片识别': lambda: self._ocr_recognition(file_path),
            '预测': lambda: self._ml_predict(df, **kwargs),
            'predict': lambda: self._ml_predict(df, **kwargs),
            '时间序列预测': lambda: self._time_series_predict(df, **kwargs),
            'timeseries': lambda: self._time_series_predict(df, **kwargs),
        }

        handler = action_map.get(action)
        if handler:
            return handler()
        logger.warning("未知数据分析动作: %s, 降级为描述性统计", action)
        return self._descriptive_stats(df)

    def _load_csv(self, file_path: str) -> Optional[Any]:
        """加载CSV文件，支持UTF-8和GBK编码。

        Args:
            file_path: CSV文件路径

        Returns:
            pandas.DataFrame 或 None（加载失败时）
        """
        try:
            import pandas as pd
        except ImportError:
            logger.error("pandas未安装")
            return None

        for encoding in ('utf-8-sig', 'utf-8', 'gbk', 'gb18030', 'latin-1'):
            try:
                df = pd.read_csv(file_path, encoding=encoding)
                logger.debug("CSV加载成功 [%s], 编码: %s, 行数: %d", file_path, encoding, len(df))
                return df
            except (UnicodeDecodeError, UnicodeError):
                continue
            except Exception as e:
                logger.error("CSV加载失败 [%s]: %s", file_path, e)
                return None
        logger.error("CSV编码不支持: %s", file_path)
        return None

    def _find_latest_csv(self) -> Optional[str]:
        """自动查找最新的CSV文件。

        搜索路径优先级：
        1. skills/data_analysis/output/
        2. data/
        3. 当前工作目录

        Returns:
            最新CSV文件路径，或None
        """
        search_dirs: List[Path] = [
            self.output_dir,
            Path(__file__).parent.parent.parent / 'data',
            Path.cwd(),
        ]
        csv_files: List[Path] = []
        for d in search_dirs:
            if d.exists():
                csv_files.extend(d.glob('*.csv'))

        if not csv_files:
            logger.debug("未找到CSV文件, 搜索目录: %s", search_dirs)
            return None

        csv_files.sort(key=lambda f: os.path.getmtime(str(f)), reverse=True)
        best = csv_files[0]
        logger.debug("找到最新CSV: %s (共%d个)", best, len(csv_files))
        return str(best)

    def _find_columns(self, df: Any) -> Tuple[List[str], List[str]]:
        """智能识别文本列和数值列。

        Args:
            df: pandas DataFrame

        Returns:
            (text_cols, num_cols) 元组
        """
        import pandas as pd

        text_cols: List[str] = []
        num_cols: List[str] = []
        for col in df.columns:
            if pd.api.types.is_numeric_dtype(df[col]):
                num_cols.append(col)
            else:
                text_cols.append(col)
        return text_cols, num_cols

    def _generate_chart_filename(self) -> Path:
        """生成统一的图表文件名。

        Returns:
            图表路径 Path对象
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return self.output_dir / f'分析图表_{timestamp}.png'

    def _setup_matplotlib(self) -> Any:
        """初始化matplotlib配置，设置中文字体和Agg后端。

        Returns:
            matplotlib.pyplot 模块

        Raises:
            ImportError: matplotlib未安装
        """
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        plt.rcParams['font.sans-serif'] = [
            'SimHei', 'Arial Unicode MS', 'PingFang SC',
            'STHeiti', 'Heiti TC', 'Microsoft YaHei',
        ]
        plt.rcParams['axes.unicode_minus'] = False
        plt.rcParams['figure.dpi'] = 150
        return plt

    # ── 描述性统计 ────────────────────────────────────────

    def _descriptive_stats(self, df: Any) -> Dict[str, Any]:
        """描述性统计分析 - 包含pandas describe + 自定义统计。

        输出包含：行数/列数/数据类型分布/缺失值/每列统计摘要

        Args:
            df: pandas DataFrame

        Returns:
            包含统计结果的字典
        """
        import pandas as pd

        stats: Dict[str, Any] = {}
        dtype_dist: Dict[str, int] = {}
        missing_info: Dict[str, int] = {}

        for col in df.columns:
            dtype_str = str(df[col].dtype)
            dtype_dist[dtype_str] = dtype_dist.get(dtype_str, 0) + 1
            missing_info[col] = int(df[col].isna().sum())

            if pd.api.types.is_numeric_dtype(df[col]):
                stats[col] = {
                    'count': int(df[col].count()),
                    'mean': round(float(df[col].mean()), 4),
                    'std': round(float(df[col].std()), 4),
                    'min': round(float(df[col].min()), 4),
                    '25%': round(float(df[col].quantile(0.25)), 4),
                    '50%': round(float(df[col].median()), 4),
                    '75%': round(float(df[col].quantile(0.75)), 4),
                    'max': round(float(df[col].max()), 4),
                }
            else:
                vc = df[col].value_counts().head(5)
                stats[col] = {
                    'unique': int(df[col].nunique()),
                    'top_values': {str(k): int(v) for k, v in vc.items()},
                }

        total_missing = sum(missing_info.values())
        missing_cols = [c for c, cnt in missing_info.items() if cnt > 0]

        lines = [
            f'📊 数据分析完成',
            f'总行数: {len(df)}，总列数: {len(df.columns)}',
            f'数据类型分布: {dtype_dist}',
            f'缺失值: 共{total_missing}个',
        ]
        if missing_cols:
            lines.append(f'缺失列: {", ".join(missing_cols[:10])}')
        lines.append('统计摘要:')
        for col, info in list(stats.items())[:5]:
            if 'mean' in info:
                lines.append(f'  {col}: 均值={info["mean"]}, 标准差={info["std"]}, 范围=[{info["min"]}, {info["max"]}]')
            else:
                lines.append(f'  {col}: 唯一值={info["unique"]}, TOP={list(info["top_values"].items())[:3]}')

        return {
            'success': True,
            'action': '描述性统计',
            'rows': len(df),
            'columns': list(df.columns),
            'dtype_distribution': dtype_dist,
            'missing_values': missing_info,
            'total_missing': total_missing,
            'statistics': stats,
            'preview': df.head(5).to_string(),
            'reply': '\n'.join(lines),
        }

    # ── 柱状图 ────────────────────────────────────────────

    def _create_bar_chart(self, df: Any) -> Dict[str, Any]:
        """创建水平柱状图 - 渐变色，智能列选择。

        matplotlib不可用时降级为文字报告。

        Args:
            df: pandas DataFrame

        Returns:
            包含 chart_path 的字典，或降级后的文字报告
        """
        try:
            plt = self._setup_matplotlib()
            from matplotlib.colors import LinearSegmentedColormap

            text_cols, num_cols = self._find_columns(df)
            fig, ax = plt.subplots(figsize=(14, max(6, len(df.head(15)) * 0.4)))

            if text_cols and num_cols:
                text_col, num_col = text_cols[0], num_cols[0]
                data = df.head(15).copy()
                data['_sort_val'] = pd.to_numeric(data[num_col], errors='coerce')
                data = data.dropna(subset=['_sort_val']).sort_values('_sort_val', ascending=True)
                labels = data[text_col].astype(str).tolist()
                values = data['_sort_val'].tolist()

                cmap = LinearSegmentedColormap.from_list('grad', ['#4F46E5', '#7C3AED', '#EC4899'])
                colors = [cmap(i / max(len(values) - 1, 1)) for i in range(len(values))]

                bars = ax.barh(range(len(values)), values, color=colors, height=0.7,
                               edgecolor='white', linewidth=0.5)
                ax.set_yticks(range(len(labels)))
                ax.set_yticklabels(labels, fontsize=9)
                ax.set_xlabel(num_col, fontsize=11)
                ax.set_title(f'{num_col} 排名 Top {len(values)}', fontsize=14, fontweight='bold', pad=15)

                if values:
                    max_val = max(abs(v) for v in values) if values else 1
                    for bar, val in zip(bars, values):
                        ax.text(bar.get_width() + max_val * 0.01,
                                bar.get_y() + bar.get_height() / 2,
                                f'{val:,.1f}', va='center', fontsize=8, color='#555')

                ax.spines['top'].set_visible(False)
                ax.spines['right'].set_visible(False)
            else:
                df_num = df.select_dtypes(include='number').head(10)
                if df_num.empty:
                    plt.close()
                    return {'success': False, 'error': '无可用于柱状图的数据'}
                df_num.plot(kind='bar', ax=ax)
                ax.set_title('数据柱状图', fontsize=14, fontweight='bold')

            plt.tight_layout()
            chart_path = self._generate_chart_filename()
            plt.savefig(str(chart_path), dpi=150, bbox_inches='tight', facecolor='white')
            plt.close()

            return {
                'success': True, 'action': '柱状图',
                'chart_path': str(chart_path),
                'reply': f'📊 柱状图已生成: {chart_path}',
            }

        except ImportError:
            logger.warning('matplotlib不可用，降级为文字报告')
            return self._descriptive_stats(df)
        except Exception as e:
            logger.error('柱状图生成失败: %s', e, exc_info=True)
            return {'success': False, 'error': f'图表生成失败: {e}'}

    # ── 饼图 ──────────────────────────────────────────────

    def _create_pie_chart(self, df: Any) -> Dict[str, Any]:
        """创建饼图 - 环形图，前8项，百分比标签。

        matplotlib不可用时降级为文字报告。

        Args:
            df: pandas DataFrame

        Returns:
            包含 chart_path 的字典
        """
        try:
            plt = self._setup_matplotlib()

            text_cols, _ = self._find_columns(df)
            target_col = text_cols[0] if text_cols else df.columns[0]
            counts = df[target_col].value_counts().head(8)

            if counts.empty:
                plt.close()
                return {'success': False, 'error': '无数据可生成饼图'}

            palette = ['#4F46E5', '#7C3AED', '#EC4899', '#F59E0B',
                       '#10B981', '#3B82F6', '#EF4444', '#8B5CF6']

            fig, ax = plt.subplots(figsize=(10, 8))
            wedges, texts, autotexts = ax.pie(
                counts.values,
                labels=counts.index.astype(str),
                autopct='%1.1f%%', startangle=140,
                colors=palette[:len(counts)],
                pctdistance=0.75, textprops={'fontsize': 10},
            )
            for at in autotexts:
                at.set_fontsize(9)
                at.set_color('white')
                at.set_fontweight('bold')

            ax.add_artist(plt.Circle((0, 0), 0.55, fc='white'))
            ax.set_title(f'{target_col} 分布', fontsize=14, fontweight='bold', pad=20)

            legend_labels = [f'{idx}: {val} ({val / len(df) * 100:.1f}%)'
                            for idx, val in counts.items()]
            ax.legend(wedges, legend_labels, loc='center left', bbox_to_anchor=(1, 0.5), fontsize=9)

            plt.tight_layout()
            chart_path = self._generate_chart_filename()
            plt.savefig(str(chart_path), dpi=150, bbox_inches='tight', facecolor='white')
            plt.close()

            return {
                'success': True, 'action': '饼图',
                'chart_path': str(chart_path),
                'reply': f'📊 饼图已生成: {chart_path}',
            }

        except ImportError:
            logger.warning('matplotlib不可用，降级为文字报告')
            counts = df[df.columns[0]].value_counts().head(8)
            reply = f'{df.columns[0]} 分布:\n' + '\n'.join(
                f'  {k}: {v} ({v / len(df) * 100:.1f}%)' for k, v in counts.items()
            )
            return {'success': True, 'action': '饼图(文字)', 'reply': reply}
        except Exception as e:
            logger.error('饼图生成失败: %s', e, exc_info=True)
            return {'success': False, 'error': f'图表生成失败: {e}'}

    # ── 词云 ──────────────────────────────────────────────

    def _create_wordcloud(self, df: Any) -> Dict[str, Any]:
        """生成词云图。

        自动搜索系统中的中文字体路径。

        Args:
            df: pandas DataFrame

        Returns:
            包含 chart_path 的字典，或文字降级结果
        """
        try:
            from wordcloud import WordCloud  # type: ignore[import-untyped]
        except ImportError:
            logger.warning('wordcloud未安装，降级为文字')
            text_cols, _ = self._find_columns(df)
            col = text_cols[0] if text_cols else df.columns[0]
            top = df[col].astype(str).str.cat(sep=' ').split()[:50]
            return {
                'success': True, 'action': '词云(文字)',
                'reply': f'⚠️ wordcloud未安装(pip install wordcloud)\n高频词: {", ".join(top[:15])}',
            }

        try:
            plt = self._setup_matplotlib()
            text_cols, _ = self._find_columns(df)
            text_col = text_cols[0] if text_cols else df.columns[0]
            all_text = ' '.join(df[text_col].astype(str).tolist())

            font_path: Optional[str] = None
            for fp in [
                '/System/Library/Fonts/PingFang.ttc',
                '/System/Library/Fonts/STHeiti Medium.ttc',
                '/System/Library/Fonts/Hiragino Sans GB.ttc',
                '/Library/Fonts/Arial Unicode.ttf',
            ]:
                if os.path.exists(fp):
                    font_path = fp
                    break

            wc_params: Dict[str, Any] = {
                'width': 1200, 'height': 600,
                'background_color': 'white',
                'max_words': 150,
                'collocations': False,
                'random_state': 42,
            }
            if font_path:
                wc_params['font_path'] = font_path

            wc = WordCloud(**wc_params).generate(all_text)

            fig, ax = plt.subplots(figsize=(14, 7))
            ax.imshow(wc, interpolation='bilinear')
            ax.axis('off')
            ax.set_title(f'{text_col} 词云', fontsize=14, fontweight='bold', pad=15)

            plt.tight_layout()
            chart_path = self._generate_chart_filename()
            plt.savefig(str(chart_path), dpi=150, bbox_inches='tight', facecolor='white')
            plt.close()

            return {
                'success': True, 'action': '词云',
                'chart_path': str(chart_path),
                'reply': f'☁️ 词云已生成: {chart_path}',
            }

        except Exception as e:
            logger.error('词云生成失败: %s', e, exc_info=True)
            return {'success': False, 'error': f'词云生成失败: {e}'}

    # ── 折线图 ────────────────────────────────────────────

    def _create_line_chart(self, df: Any) -> Dict[str, Any]:
        """创建折线图 - 趋势分析。

        自动识别所有数值列并绘制趋势线。

        Args:
            df: pandas DataFrame

        Returns:
            包含 chart_path 的字典
        """
        try:
            plt = self._setup_matplotlib()
            _, num_cols = self._find_columns(df)

            if not num_cols:
                plt.close()
                return {'success': False, 'error': '无数值列可绘制折线图'}

            fig, ax = plt.subplots(figsize=(14, 6))
            palette = ['#4F46E5', '#EC4899', '#10B981', '#F59E0B', '#3B82F6', '#EF4444']

            for i, col in enumerate(num_cols[:6]):
                values = pd.to_numeric(df[col], errors='coerce')
                ax.plot(range(len(values)), values, label=col,
                        color=palette[i % len(palette)], linewidth=2, alpha=0.85,
                        marker='o' if len(values) <= 30 else '', markersize=3)

            ax.set_xlabel('数据序号', fontsize=11)
            ax.set_ylabel('数值', fontsize=11)
            ax.set_title('趋势分析', fontsize=14, fontweight='bold', pad=15)
            ax.legend(loc='best', fontsize=9)
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.grid(axis='y', alpha=0.3)

            plt.tight_layout()
            chart_path = self._generate_chart_filename()
            plt.savefig(str(chart_path), dpi=150, bbox_inches='tight', facecolor='white')
            plt.close()

            return {
                'success': True, 'action': '折线图',
                'chart_path': str(chart_path),
                'reply': f'📈 折线图已生成: {chart_path}',
            }

        except ImportError:
            logger.warning('matplotlib不可用，降级为文字报告')
            return self._descriptive_stats(df)
        except Exception as e:
            logger.error('折线图生成失败: %s', e, exc_info=True)
            return {'success': False, 'error': f'图表生成失败: {e}'}

    # ── 对比分析 ──────────────────────────────────────────

    def _comparison_analysis(self, df: Any) -> Dict[str, Any]:
        """对比分析 - 含IQR异常值检测。

        Args:
            df: pandas DataFrame

        Returns:
            包含对比统计和异常值信息的字典
        """
        import pandas as pd

        _, num_cols = self._find_columns(df)
        comparison: Dict[str, Any] = {}

        for col in num_cols:
            col_data = pd.to_numeric(df[col], errors='coerce').dropna()
            if len(col_data) == 0:
                continue
            q75, q25 = col_data.quantile(0.75), col_data.quantile(0.25)
            iqr = q75 - q25
            outliers = int(((col_data < (q25 - 1.5 * iqr)) | (col_data > (q75 + 1.5 * iqr))).sum())
            cv = round(float(col_data.std() / col_data.mean()), 4) if col_data.mean() != 0 else None
            comparison[col] = {
                'mean': round(float(col_data.mean()), 4),
                'median': round(float(col_data.median()), 4),
                'iqr': round(float(iqr), 4),
                'outliers': outliers,
                'cv': cv,
            }

        lines = [
            '📊 对比分析完成',
            f'数据概览: {len(df)}行, {len(df.columns)}列, {len(num_cols)}个数值列',
            '异常值检测（IQR方法）:',
        ]
        for col, info in comparison.items():
            lines.append(
                f'  {col}: 均值={info["mean"]}, 中位数={info["median"]}, '
                f'变异系数={info["cv"]}, 异常值={info["outliers"]}个'
            )

        return {
            'success': True, 'action': '对比分析',
            'rows': len(df), 'columns': list(df.columns),
            'numeric_columns': num_cols,
            'comparison': comparison,
            'reply': '\n'.join(lines),
        }

    # ── 热力图 ────────────────────────────────────────────

    def _heatmap(self, df: Any) -> Dict[str, Any]:
        """热力图 - 特征相关性矩阵。

        需至少2个数值列。matplotlib不可用时降级为文字矩阵。

        Args:
            df: pandas DataFrame

        Returns:
            包含相关性矩阵和强相关特征对的字典
        """
        try:
            plt = self._setup_matplotlib()
            import numpy as np

            df_num = df.select_dtypes(include='number')
            if df_num.shape[1] < 2:
                plt.close()
                return {'success': False, 'error': '至少需要2个数值列才能生成热力图'}

            corr = df_num.corr()
            fig, ax = plt.subplots(figsize=(
                max(8, len(df_num.columns) * 0.8),
                max(6, len(df_num.columns) * 0.6),
            ))

            cmap = plt.cm.RdYlBu_r
            im = ax.imshow(corr, cmap=cmap, vmin=-1, vmax=1, aspect='auto')

            ax.set_xticks(range(len(corr.columns)))
            ax.set_yticks(range(len(corr.columns)))
            ax.set_xticklabels(corr.columns, rotation=45, ha='right', fontsize=9)
            ax.set_yticklabels(corr.columns, fontsize=9)

            for i in range(len(corr)):
                for j in range(len(corr)):
                    val = corr.iloc[i, j]
                    color = 'white' if abs(val) > 0.5 else 'black'
                    ax.text(j, i, f'{val:.2f}', ha='center', va='center', fontsize=8, color=color)

            cbar = plt.colorbar(im, ax=ax, shrink=0.8)
            cbar.set_label('相关系数', fontsize=10)
            ax.set_title('特征相关性热力图', fontsize=14, fontweight='bold', pad=15)

            strong_corr: List[str] = []
            for i in range(len(corr)):
                for j in range(i + 1, len(corr)):
                    if abs(corr.iloc[i, j]) > 0.7:
                        strong_corr.append(f'{corr.columns[i]} ↔ {corr.columns[j]}: {corr.iloc[i, j]:.3f}')

            plt.tight_layout()
            chart_path = self._generate_chart_filename()
            plt.savefig(str(chart_path), dpi=150, bbox_inches='tight', facecolor='white')
            plt.close()

            reply = f'🔥 热力图已生成: {chart_path}'
            if strong_corr:
                reply += f'\n强相关特征(|r|>0.7): {", ".join(strong_corr[:10])}'
            else:
                reply += '\n未发现强相关特征(|r|>0.7)'

            return {
                'success': True, 'action': '热力图',
                'chart_path': str(chart_path),
                'correlation_matrix': corr.to_dict(),
                'strong_correlations': strong_corr,
                'reply': reply,
            }

        except ImportError:
            logger.warning('matplotlib不可用，降级为文字报告')
            df_num = df.select_dtypes(include='number')
            if df_num.shape[1] < 2:
                return {'success': False, 'error': '至少需要2个数值列'}
            corr = df_num.corr()
            return {
                'success': True, 'action': '热力图(文字)',
                'correlation_matrix': corr.to_dict(),
                'reply': f'⚠️ matplotlib不可用\n相关性矩阵:\n{corr.to_string()}',
            }
        except Exception as e:
            logger.error('热力图生成失败: %s', e, exc_info=True)
            return {'success': False, 'error': f'图表生成失败: {e}'}

    # ── 文本文件分析 ──────────────────────────────────────

    def _analyze_text_file(self, file_path: str, action: str) -> Dict[str, Any]:
        """分析TXT/MD文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.split('\n')
            words = content.split()
            
            stats = {
                'total_chars': len(content),
                'total_lines': len(lines),
                'total_words': len(words),
                'avg_line_length': round(len(content) / max(len(lines), 1), 2),
            }
            
            reply = [
                f'📄 文本分析完成',
                f'总字符数: {stats["total_chars"]}',
                f'总行数: {stats["total_lines"]}',
                f'总词数: {stats["total_words"]}',
                f'平均每行长度: {stats["avg_line_length"]}',
            ]
            
            return {
                'success': True,
                'action': f'文本分析',
                'file_type': 'text',
                'statistics': stats,
                'reply': '\n'.join(reply),
            }
        except Exception as e:
            logger.error(f'文本分析失败: {e}')
            return {'success': False, 'error': f'分析失败: {e}'}

    # ── 图片文件分析 ──────────────────────────────────────

    def _analyze_image_file(self, file_path: str, action: str) -> Dict[str, Any]:
        """分析图片文件"""
        try:
            from PIL import Image
            
            img = Image.open(file_path)
            width, height = img.size
            format_name = img.format
            mode = img.mode
            file_size = Path(file_path).stat().st_size
            
            stats = {
                'width': width,
                'height': height,
                'format': format_name,
                'mode': mode,
                'file_size_kb': round(file_size / 1024, 2),
                'aspect_ratio': round(width / height, 2) if height > 0 else 0,
            }
            
            reply = [
                f'🖼️ 图片分析完成',
                f'尺寸: {width}x{height}',
                f'格式: {format_name}',
                f'颜色模式: {mode}',
                f'文件大小: {stats["file_size_kb"]}KB',
                f'宽高比: {stats["aspect_ratio"]}',
            ]
            
            return {
                'success': True,
                'action': f'图片分析',
                'file_type': 'image',
                'statistics': stats,
                'reply': '\n'.join(reply),
            }
        except ImportError:
            return {'success': False, 'error': 'PIL未安装 (pip install Pillow)'}
        except Exception as e:
            logger.error(f'图片分析失败: {e}')
            return {'success': False, 'error': f'分析失败: {e}'}
    
    # ── OCR文字识别（增强版）──────────────────────────────

    def _ocr_recognition(self, file_path: str, language: str = 'ch', **kwargs: Any) -> Dict[str, Any]:
        """使用PaddleOCR识别图片中的文字（增强版）
        
        支持多种语言和智能回复生成，集成ToolResultFormatter。
        
        Args:
            file_path: 图片文件路径
            language: 语言代码 ('ch'=中文, 'en'=英文, 'japan'=日文等)
            **kwargs: 额外参数
            
        Returns:
            包含识别结果的字典，包含智能格式化的回复
        """
        start_time = time.perf_counter()
        
        try:
            from paddleocr import PaddleOCR
            
            # 确定语言映射
            lang_map = {
                'ch': 'ch', 'chi': 'ch', 'chi_sim': 'ch', 'zh': 'ch', 'cn': 'ch',
                '中文': 'ch', '简体中文': 'ch',
                'en': 'en', 'eng': 'en', 'english': 'en', '英文': 'en',
                'japan': 'japan', 'jpn': 'japan', 'ja': 'japan', '日文': 'japan',
                'kor': 'korean', 'ko': 'korean', '韩文': 'korean',
            }
            
            ocr_lang = lang_map.get(language.lower(), 'ch')
            
            # 初始化OCR引擎
            logger.info("初始化PaddleOCR引擎，语言: %s", ocr_lang)
            ocr = PaddleOCR(use_angle_cls=True, lang=ocr_lang, show_log=False)
            
            # 执行OCR识别
            logger.info("开始OCR识别: %s", file_path)
            result = ocr.ocr(file_path)
            
            elapsed = time.perf_counter() - start_time
            
            # 处理识别结果
            if not result or not result[0]:
                tool_result = {
                    "tool_name": "ocr_recognition",
                    "success": True,
                    "result": {"text": "", "text_count": 0, "message": "未检测到文字内容"},
                    "execution_time": round(elapsed, 2),
                    "timestamp": datetime.now().isoformat(),
                    "output_path": ""
                }
                
                return {
                    'success': True, 'action': 'OCR识别', 'text': '', 'text_blocks': [],
                    'statistics': {'total_text_blocks': 0, 'total_chars': 0},
                    'reply': self._generate_ocr_reply(tool_result, file_path),
                    '_elapsed': round(elapsed, 3),
                }
            
            all_text = []
            text_blocks = []
            confidences = []
            
            # PaddleOCR 3.x返回OCRResult对象
            ocr_result = result[0]
            
            # 获取JSON格式的结果
            if hasattr(ocr_result, 'json'):
                json_result = ocr_result.json
                res_data = json_result.get('res', {})
                
                rec_texts = res_data.get('rec_texts', [])
                rec_scores = res_data.get('rec_scores', [])
                rec_polys = res_data.get('rec_polys', [])
                
                for i, text in enumerate(rec_texts):
                    confidence = rec_scores[i] if i < len(rec_scores) else 0.0
                    box = rec_polys[i] if i < len(rec_polys) else []
                    
                    if hasattr(box, 'tolist'):
                        box = box.tolist()
                    
                    if text and text.strip():
                        all_text.append(text)
                        confidences.append(float(confidence))
                        text_blocks.append({
                            'text': text,
                            'confidence': round(float(confidence), 3),
                            'position': box,
                        })
            else:
                # 兼容旧版本
                for line in ocr_result:
                    if line:
                        box = line[0]
                        text_info = line[1]
                        
                        if isinstance(text_info, (list, tuple)) and len(text_info) >= 2:
                            text = text_info[0]
                            confidence = text_info[1] if len(text_info) > 1 else 0.0
                        elif isinstance(text_info, str):
                            text = text_info
                            confidence = 0.0
                        else:
                            continue
                        
                        if text and text.strip():
                            all_text.append(text)
                            confidences.append(float(confidence))
                            text_blocks.append({
                                'text': text,
                                'confidence': round(float(confidence), 3),
                                'position': box,
                            })
            
            full_text = '\n'.join(all_text)
            
            # 计算统计信息
            avg_confidence = sum(confidences) / max(len(confidences), 1)
            stats = {
                'total_text_blocks': len(text_blocks),
                'total_chars': len(full_text),
                'avg_confidence': round(avg_confidence, 3),
                'max_confidence': round(max(confidences) if confidences else 0, 3),
                'min_confidence': round(min(confidences) if confidences else 0, 3),
            }
            
            # 保存识别结果到文件
            output_path = self._save_ocr_result(full_text, file_path)
            
            # 构建工具结果
            tool_result = {
                "tool_name": "ocr_recognition",
                "success": True,
                "result": {
                    "text": full_text[:200],  # 预览前200字符
                    "text_blocks": len(text_blocks),
                    "total_chars": stats['total_chars'],
                    "avg_confidence": stats['avg_confidence'],
                    "language": ocr_lang,
                    "output_path": output_path,
                },
                "execution_time": round(elapsed, 2),
                "timestamp": datetime.now().isoformat(),
                "output_path": output_path
            }
            
            # 生成智能回复
            reply = self._generate_ocr_reply(tool_result, file_path)
            
            logger.info(
                "OCR识别完成: 文本块=%d, 字符数=%d, 平均置信度=%.3f, 耗时=%.3fs",
                stats['total_text_blocks'], stats['total_chars'], stats['avg_confidence'], elapsed
            )
            
            return {
                'success': True,
                'action': 'OCR识别',
                'text': full_text,
                'text_blocks': text_blocks,
                'statistics': stats,
                'reply': reply,
                'output_path': output_path,
                '_elapsed': round(elapsed, 3),
            }
            
        except ImportError as e:
            logger.error("PaddleOCR未安装: %s", e)
            return {
                'success': False,
                'error': 'PaddleOCR未安装\n\n安装命令:\npip install paddleocr paddlepaddle\n\n注意：首次运行会自动下载模型文件（约400MB）',
            }
        except Exception as e:
            logger.error(f'OCR识别失败: {e}', exc_info=True)
            return {'success': False, 'error': f'OCR识别失败: {str(e)}'}

    def _save_ocr_result(self, text: str, source_image: str) -> str:
        """保存OCR识别结果到文本文件
        
        Args:
            text: 识别的文本内容
            source_image: 源图片路径
            
        Returns:
            保存的文件路径
        """
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            image_name = Path(source_image).stem
            output_filename = f"ocr_{image_name}_{timestamp}.txt"
            output_path = self.output_dir / output_filename
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"# OCR识别结果\n")
                f.write(f"# 源图片: {source_image}\n")
                f.write(f"# 识别时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# {'='*60}\n\n")
                f.write(text)
            
            logger.info("OCR结果已保存: %s", output_path)
            return str(output_path)
            
        except Exception as e:
            logger.error("保存OCR结果失败: %s", e)
            return ""

    def _generate_ocr_reply(self, tool_result: Dict[str, Any], image_path: str) -> str:
        """生成OCR识别的智能回复
        
        Args:
            tool_result: 工具执行结果
            image_path: 原始图片路径
            
        Returns:
            格式化后的回复文本
        """
        try:
            from core.tool_result_formatter import get_tool_result_formatter
            
            formatter = get_tool_result_formatter(enable_self_check=False)
            
            import asyncio
            
            async def generate():
                response = await formatter.format_response(
                    user_query=f"识别图片中的文字: {Path(image_path).name}",
                    tool_result=tool_result
                )
                return response.full_reply
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                reply = loop.run_until_complete(generate())
            finally:
                loop.close()
            
            return reply
            
        except Exception as e:
            logger.warning("ToolResultFormatter不可用，使用默认回复: %s", e)
            return self._fallback_ocr_reply(tool_result)

    def _fallback_ocr_reply(self, tool_result: Dict[str, Any]) -> str:
        """降级回复模板（当ToolResultFormatter不可用时使用）"""
        result = tool_result.get('result', {})
        success = tool_result.get('success', False)
        
        emoji = "✅" if success else "❌"
        
        lines = [
            f"{emoji} 已完成图片文字识别",
            "",
            f"📋 **概述**",
        ]
        
        if success:
            text_blocks = result.get('text_blocks', 0)
            total_chars = result.get('total_chars', 0)
            avg_confidence = result.get('avg_confidence', 0)
            
            lines.extend([
                f"成功从图片中提取了{text_blocks}个文本块，共{total_chars}个字符，平均置信度为{avg_confidence:.1%}。",
                "",
                f"⏱️ **耗时**",
                f"{tool_result.get('execution_time', 0):.2f}秒",
                "",
                f"📁 **文件位置**",
                result.get('output_path', '无文件输出'),
                "",
                f"🕐 **完成时间**",
                datetime.fromisoformat(tool_result.get('timestamp', datetime.now().isoformat())).strftime('%Y-%m-%d %H:%M:%S'),
                "",
                f"💡 **下一步建议**",
                "1. 检查识别结果是否准确",
                "2. 如需编辑，可打开文本文件进行修改",
                "3. 如有更多图片需要识别，请继续上传",
            ])
        else:
            error_msg = tool_result.get('error', '未知错误')
            lines.extend([
                f"图片文字识别失败",
                "",
                f"⏱️ **耗时**",
                f"{tool_result.get('execution_time', 0):.2f}秒",
                "",
                f"🔧 **故障排除**",
                f"错误信息：{error_msg}",
                "",
                f"💡 **下一步建议**",
                "1. 确认已安装PaddleOCR: pip install paddleocr paddlepaddle",
                "2. 检查图片格式是否正确（支持JPG/PNG/BMP等）",
                "3. 确保图片清晰可读",
            ])
        
        return "\n".join(lines)

    # ── Word文件分析 ──────────────────────────────────────

    def _analyze_word_file(self, file_path: str, action: str) -> Dict[str, Any]:
        """分析Word文件"""
        try:
            import docx
            
            doc = docx.Document(file_path)
            paragraphs = doc.paragraphs
            total_chars = sum(len(p.text) for p in paragraphs)
            total_words = sum(len(p.text.split()) for p in paragraphs)
            
            stats = {
                'total_paragraphs': len(paragraphs),
                'total_chars': total_chars,
                'total_words': total_words,
                'avg_paragraph_length': round(total_chars / max(len(paragraphs), 1), 2),
            }
            
            reply = [
                f'📝 Word文档分析完成',
                f'总段落数: {stats["total_paragraphs"]}',
                f'总字符数: {stats["total_chars"]}',
                f'总词数: {stats["total_words"]}',
                f'平均每段长度: {stats["avg_paragraph_length"]}',
            ]
            
            return {
                'success': True,
                'action': f'Word分析',
                'file_type': 'word',
                'statistics': stats,
                'reply': '\n'.join(reply),
            }
        except ImportError:
            return {'success': False, 'error': 'python-docx未安装 (pip install python-docx)'}
        except Exception as e:
            logger.error(f'Word分析失败: {e}')
            return {'success': False, 'error': f'分析失败: {e}'}
    
    def generate_pdf(self, content: str, title: str = "文档", output_path: str = None) -> Dict[str, Any]:
        """生成PDF文件"""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
            from reportlab.lib.units import cm
            from pathlib import Path
            
            if not output_path:
                desktop = Path.home() / "Desktop"
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = str(desktop / f"{title}_{timestamp}.pdf")
            
            c = canvas.Canvas(output_path, pagesize=A4)
            width, height = A4
            
            # 标题
            c.setFont("Helvetica-Bold", 16)
            c.drawString(2*cm, height - 2*cm, title)
            
            # 内容（简单换行）
            c.setFont("Helvetica", 10)
            y_position = height - 3*cm
            lines = content.split('\n')
            
            for line in lines:
                if y_position < 2*cm:  # 新页
                    c.showPage()
                    c.setFont("Helvetica", 10)
                    y_position = height - 2*cm
                
                # 处理中文（简化版，实际需中文字体）
                try:
                    c.drawString(2*cm, y_position, line[:80])  # 每行最多80字符
                except:
                    c.drawString(2*cm, y_position, "[Content]")
                
                y_position -= 0.5*cm
            
            c.save()
            
            logger.info(f"PDF已生成: {output_path}")
            return {
                "success": True,
                "pdf_path": output_path,
                "reply": f"📄 PDF已保存到: {output_path}",
            }
        except ImportError:
            return {"success": False, "error": "reportlab未安装 (pip install reportlab)"}
        except Exception as e:
            logger.error(f"PDF生成失败: {e}")
            return {"success": False, "error": f"生成失败: {e}"}

    def _ml_predict(self, df: Any, **kwargs: Any) -> Dict[str, Any]:
        """机器学习预测
        
        支持回归和分类任务，使用LightGBM模型
        
        Args:
            df: pandas DataFrame
            target_column: 目标列名
            prediction_type: 预测类型 (regression/classification)
            
        Returns:
            预测结果
        """
        try:
            import numpy as np
            from sklearn.model_selection import train_test_split
            from sklearn.metrics import mean_squared_error, accuracy_score
            from sklearn.preprocessing import LabelEncoder
        except ImportError:
            return {"success": False, "error": "scikit-learn未安装 (pip install scikit-learn)"}
        
        try:
            import lightgbm as lgb
        except ImportError:
            return {"success": False, "error": "lightgbm未安装 (pip install lightgbm)"}
        
        target_column = kwargs.get('target_column')
        if not target_column:
            return {"success": False, "error": "请指定目标列 (target_column)"}
        
        if target_column not in df.columns:
            return {"success": False, "error": f"目标列 '{target_column}' 不存在"}
        
        prediction_type = kwargs.get('prediction_type', 'regression')
        
        # 准备数据
        X = df.drop(columns=[target_column])
        y = df[target_column]
        
        # 处理分类目标
        if prediction_type == 'classification':
            le = LabelEncoder()
            y = le.fit_transform(y)
        
        # 处理非数值特征
        for col in X.columns:
            if X[col].dtype == 'object':
                X[col] = LabelEncoder().fit_transform(X[col].astype(str))
        
        # 填充缺失值
        X = X.fillna(0)
        
        # 分割数据
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        
        # 训练模型
        if prediction_type == 'regression':
            model = lgb.LGBMRegressor(
                n_estimators=100,
                learning_rate=0.1,
                max_depth=6,
                random_state=42,
                verbose=-1
            )
            model.fit(X_train, y_train)
            
            # 预测
            y_pred = model.predict(X_test)
            mse = mean_squared_error(y_test, y_pred)
            rmse = np.sqrt(mse)
            
            # 特征重要性
            importance = model.feature_importances_
            feature_names = X.columns
            
            reply_lines = [
                f"🤖 机器学习回归预测",
                f"目标列: {target_column}",
                f"训练样本: {len(X_train)}",
                f"测试样本: {len(X_test)}",
                f"均方误差(MSE): {mse:.4f}",
                f"均方根误差(RMSE): {rmse:.4f}",
                "",
                "特征重要性 Top 5:",
            ]
            
            for idx in np.argsort(importance)[-5:][::-1]:
                reply_lines.append(f"  {feature_names[idx]}: {importance[idx]:.4f}")
            
            return {
                "success": True,
                "action": "机器学习预测",
                "prediction_type": "regression",
                "mse": float(mse),
                "rmse": float(rmse),
                "feature_importance": dict(zip(feature_names, importance)),
                "reply": "\n".join(reply_lines),
            }
            
        else:
            model = lgb.LGBMClassifier(
                n_estimators=100,
                learning_rate=0.1,
                max_depth=6,
                random_state=42,
                verbose=-1
            )
            model.fit(X_train, y_train)
            
            # 预测
            y_pred = model.predict(X_test)
            accuracy = accuracy_score(y_test, y_pred)
            
            # 特征重要性
            importance = model.feature_importances_
            feature_names = X.columns
            
            reply_lines = [
                f"🤖 机器学习分类预测",
                f"目标列: {target_column}",
                f"训练样本: {len(X_train)}",
                f"测试样本: {len(X_test)}",
                f"准确率: {accuracy:.4f}",
                "",
                "特征重要性 Top 5:",
            ]
            
            for idx in np.argsort(importance)[-5:][::-1]:
                reply_lines.append(f"  {feature_names[idx]}: {importance[idx]:.4f}")
            
            return {
                "success": True,
                "action": "机器学习预测",
                "prediction_type": "classification",
                "accuracy": float(accuracy),
                "feature_importance": dict(zip(feature_names, importance)),
                "reply": "\n".join(reply_lines),
            }
            
    def _time_series_predict(self, df: Any, **kwargs: Any) -> Dict[str, Any]:
        """时间序列预测
        
        使用移动平均和线性回归进行简单的时间序列预测
        
        Args:
            df: pandas DataFrame
            target_column: 目标列名
            forecast_steps: 预测步数 (默认5)
            
        Returns:
            预测结果
        """
        try:
            import numpy as np
            from sklearn.linear_model import LinearRegression
        except ImportError:
            return {"success": False, "error": "scikit-learn未安装 (pip install scikit-learn)"}
        
        target_column = kwargs.get('target_column')
        if not target_column:
            return {"success": False, "error": "请指定目标列 (target_column)"}
        
        if target_column not in df.columns:
            return {"success": False, "error": f"目标列 '{target_column}' 不存在"}
        
        forecast_steps = kwargs.get('forecast_steps', 5)
        
        # 提取时间序列数据
        series = df[target_column].values
        
        # 移动平均平滑
        window_size = min(7, len(series) // 4)
        if window_size > 1:
            moving_avg = np.convolve(series, np.ones(window_size)/window_size, mode='valid')
        else:
            moving_avg = series
        
        # 线性回归预测
        X = np.arange(len(moving_avg)).reshape(-1, 1)
        y = moving_avg
        
        model = LinearRegression()
        model.fit(X, y)
        
        # 预测未来值
        last_index = len(moving_avg) - 1
        future_X = np.arange(last_index + 1, last_index + 1 + forecast_steps).reshape(-1, 1)
        predictions = model.predict(future_X)
        
        # 计算趋势
        slope = model.coef_[0]
        trend = "上升" if slope > 0 else "下降" if slope < 0 else "平稳"
        
        reply_lines = [
            f"📈 时间序列预测",
            f"目标列: {target_column}",
            f"预测步数: {forecast_steps}",
            f"趋势: {trend}",
            f"斜率: {slope:.4f}",
            "",
            "预测值:",
        ]
        
        for i, pred in enumerate(predictions[-forecast_steps:], 1):
            reply_lines.append(f"  +{i}: {pred:.2f}")
        
        return {
            "success": True,
            "action": "时间序列预测",
            "target_column": target_column,
            "forecast_steps": forecast_steps,
            "trend": trend,
            "slope": float(slope),
            "predictions": predictions[-forecast_steps:].tolist(),
            "reply": "\n".join(reply_lines),
        }


analysis_handler = DataAnalysisHandler()