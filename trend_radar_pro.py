import streamlit as st
import pandas as pd
import requests
import json
import time
import plotly.graph_objects as go
from datetime import datetime, timedelta

# ================= 1. 页面配置 =================
st.set_page_config(
    page_title="Naver 趋势雷达 (Ultra版)", 
    page_icon="📡", 
    layout="wide"
)

# ================= 2. 核心逻辑：获取数据 (支持时间粒度) =================
def get_datalab_trend(client_id, client_secret, keyword, time_unit='month'):
    url = "https://openapi.naver.com/v1/datalab/search"
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
        "Content-Type": "application/json"
    }
    
    # 动态调整查询时间范围
    # 'date' (按天) 数据量大，Naver API 有时会限制返回点数，这里取近3年比较稳妥
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * 3 + 30) 
    
    body = {
        "startDate": start_date.strftime("%Y-%m-%d"),
        "endDate": end_date.strftime("%Y-%m-%d"),
        "timeUnit": time_unit, # 动态传入：'date', 'week', 'month'
        "keywordGroups": [{"groupName": keyword, "keywords": [keyword]}]
    }
    
    try:
        # 设置稍长的超时，因为按天查询数据量大
        resp = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except:
        return None
    return None

# ================= 3. 核心逻辑：分析算法 (防崩溃 + 粒度适配) =================
def analyze_custom_trend(data_json, start_month, end_month, compare_years):
    # 1. 基础结构检查
    if not data_json or 'results' not in data_json or not data_json['results']:
        return None
        
    points = data_json['results'][0]['data']
    
    # 2. 核心防崩溃：如果该词没流量(空列表)，直接返回
    if not points:
        return None
        
    df = pd.DataFrame(points)
    
    # 3. 双重保险：确保有 period 列
    if 'period' not in df.columns:
        return None

    df['period'] = pd.to_datetime(df['period'])
    df['month'] = df['period'].dt.month
    df['year'] = df['period'].dt.year
    df['ratio'] = df['ratio'].astype(float)
    
    # 4. 计算逻辑
    yearly_performance = {}
    current_year = datetime.now().year
    years_to_analyze = range(current_year - compare_years, current_year)
    
    for yr in years_to_analyze:
        if start_month <= end_month:
            mask = (df['year'] == yr) & (df['month'] >= start_month) & (df['month'] <= end_month)
        else:
            mask = (df['year'] == yr) & (df['month'] == start_month) 
        
        period_data = df[mask]
        
        # 自动计算平均值 (无论是日、周、月)
        if not period_data.empty:
            yearly_performance[yr] = period_data['ratio'].mean()
        else:
            yearly_performance[yr] = 0

    # 5. 计算环比
    last_year = current_year - 1
    prev_year = current_year - 2
    old_year = current_year - 3
    growth_rates = []
    
    val_last = yearly_performance.get(last_year, 0)
    val_prev = yearly_performance.get(prev_year, 0)
    
    if val_prev > 1: 
        growth_rates.append(((val_last - val_prev) / val_prev) * 100)
    else: 
        growth_rates.append(0)
        
    if compare_years == 3:
        val_old = yearly_performance.get(old_year, 0)
        if val_old > 1: 
            growth_rates.append(((val_prev - val_old) / val_old) * 100)
        else: 
            growth_rates.append(0)
            
    if not growth_rates: return None
    
    avg_growth = sum(growth_rates) / len(growth_rates)
    win_count = len([g for g in growth_rates if g > 10])
    win_rate = (win_count / len(growth_rates)) * 100
    peak_score = val_last
    
    # 6. 评级打分
    tag, score = "😐 观察", 50
    if compare_years == 3:
        if win_rate >= 66 and avg_growth > 20 and peak_score > 40: tag, score = "🔥 S级: 长期稳健", 100
        elif avg_growth > 10: tag, score = "📈 A级: 上升通道", 80
    else:
        if avg_growth > 50 and peak_score > 40: tag, score = "🚀 S级: 近期黑马", 100
        elif avg_growth > 15: tag, score = "📈 A级: 增长中", 80
            
    if avg_growth < -10: tag, score = "❄️ D级: 下滑", 0
    elif peak_score < 10: tag, score = "💤 小流量", 20

    return {
        "评级": tag, 
        "选品得分": score, 
        "平均涨幅%": round(avg_growth, 1), 
        "区间热度(0-100)": round(peak_score, 1), 
        "上涨胜率%": round(win_rate, 0), 
        "RawData": df
    }

# ================= 4. UI 界面 =================
st.title("📡 Naver 趋势雷达 (Ultra: 任意精度版)")

with st.sidebar:
    st.header("1. 配置")
    client_id = st.text_input("Client ID", type="password")
    client_secret = st.text_input("Client Secret", type="password")
    
    st.divider()
    st.header("2. 规则")
    
    # 时间粒度选择
    st.subheader("⏱️ 数据精度")
    time_unit_label = st.radio(
        "选择数据点密度",
        ('month', 'week', 'date'),
        index=0, # 默认按月
        format_func=lambda x: {'month': '按月 (Month) - 看大趋势', 'week': '按周 (Week) - 看节奏', 'date': '按天 (Date) - 看细节'}[x]
    )
    
    st.divider()
    
    # 月份区间
    st.subheader("📅 目标月份区间")
    month_range = st.slider("选择你要预测的月份", 1, 12, (10, 11), format="%d月")
    start_m, end_m = month_range
    
    # 对比年份
    compare_mode = st.radio("回溯年份", (2, 3), format_func=lambda x: f"近 {x} 年")

st.info(f"💡 当前模式：以 **{time_unit_label}** 粒度，扫描 **{start_m}-{end_m}月** 的表现。")
keywords_text = st.text_area("输入关键词 (注意韩语拼写!)", height=150, placeholder="감따는기구\n리빙박스\n가습기")

if st.button("🚀 开始高精度扫描", type="primary"):
    if not client_id or not keywords_text:
        st.error("请填写完整信息")
    else:
        keywords = [k.strip() for k in keywords_text.replace("\n", ",").split(",") if k.strip()]
        
        st.write(f"正在扫描 {len(keywords)} 个赛道...")
        results = []
        progress_bar = st.progress(0)
        
        for i, kw in enumerate(keywords):
            # 传入用户选择的时间粒度
            raw = get_datalab_trend(client_id, client_secret, kw, time_unit_label)
            analysis = analyze_custom_trend(raw, start_m, end_m, compare_mode)
            
            if analysis:
                results.append({
                    "赛道": kw,
                    "评级": analysis['评级'],
                    "得分": analysis['选品得分'],
                    "平均涨幅%": analysis['平均涨幅%'],
                    "区间热度": analysis['区间热度(0-100)'],
                    "RawData": analysis['RawData']
                })
            
            time.sleep(0.1)
            progress_bar.progress((i+1)/len(keywords))
            
        if results:
            df = pd.DataFrame(results).sort_values(by=['得分', '平均涨幅%'], ascending=[False, False])
            
            st.success("✅ 扫描完成！")
            
            # 结果表格
            st.dataframe(
                df.drop(columns=['RawData', '得分']),
                use_container_width=True,
                column_config={
                    "平均涨幅%": st.column_config.ProgressColumn(format="%.1f%%", min_value=-50, max_value=100),
                    "区间热度": st.column_config.ProgressColumn(min_value=0, max_value=100)
                }
            )
            
            st.divider()
            st.subheader("📊 历史走势 (交互增强版)")
            
            for _, row in df.head(5).iterrows(): # 展示前5个
                kw, raw_df = row['赛道'], row['RawData']
                fig = go.Figure()
                
                # 只画最近 N 年
                plot_years = sorted(raw_df['year'].unique())[-compare_mode-1:] 
                
                for yr in plot_years:
                    y_data = raw_df[raw_df['year'] == yr]
                    
                    fig.add_trace(go.Scatter(
                        x=y_data['period'], 
                        y=y_data['ratio'], 
                        mode='lines', 
                        name=f"{yr}年",
                        # 悬停格式化
                        hovertemplate="<b>%{x|%Y-%m-%d}</b><br>热度: %{y:.0f}<extra></extra>"
                    ))
                
                # 交互式布局设置
                fig.update_layout(
                    title=f"【{kw}】历史走势 ({time_unit_label})", 
                    xaxis_title="时间", 
                    yaxis_title="搜索热度", 
                    height=400,
                    hovermode="x unified", # 开启垂直准星
                    xaxis=dict(
                        tickformat="%Y-%m-%d",
                        showspikes=True,
                        spikemode="across",
                        spikesnap="cursor",
                        showline=True, showgrid=True
                    )
                )
                
                st.plotly_chart(fig, use_container_width=True)
