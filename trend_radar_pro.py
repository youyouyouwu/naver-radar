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

# ================= 2. 核心逻辑：获取数据 =================
def get_datalab_trend(client_id, client_secret, keyword, time_unit='month'):
    url = "https://openapi.naver.com/v1/datalab/search"
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
        "Content-Type": "application/json"
    }
    
    end_date = datetime.now()
    # 按天查询数据量大，限制为3年以防超时
    start_date = end_date - timedelta(days=365 * 3 + 30) 
    
    body = {
        "startDate": start_date.strftime("%Y-%m-%d"),
        "endDate": end_date.strftime("%Y-%m-%d"),
        "timeUnit": time_unit, 
        "keywordGroups": [{"groupName": keyword, "keywords": [keyword]}]
    }
    
    try:
        resp = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except:
        return None
    return None

# ================= 3. 核心逻辑：分析算法 (防崩溃 + 季节性修复) =================
def analyze_custom_trend(data_json, start_month, end_month, compare_years):
    # 1. 基础结构检查
    if not data_json or 'results' not in data_json or not data_json['results']: return None
    points = data_json['results'][0]['data']
    
    # 2. 核心防崩溃：如果该词没流量(空列表)，直接返回
    if not points: return None
        
    df = pd.DataFrame(points)
    
    # 3. 双重保险：确保有 period 列
    if 'period' not in df.columns: return None

    df['period'] = pd.to_datetime(df['period'])
    df['month'] = df['period'].dt.month
    df['year'] = df['period'].dt.year
    df['ratio'] = df['ratio'].astype(float)
    
    # 4. 确定对比基准 (计算环比爆发力)
    # 逻辑：目标区间的前一个月作为基准
    base_month = start_month - 1
    if base_month == 0: base_month = 12 
    
    seasonal_growths = [] 
    peak_scores = []      
    
    current_year = datetime.now().year
    years_to_analyze = range(current_year - compare_years, current_year)
    
    for yr in years_to_analyze:
        # A. 获取目标区间热度
        if start_month <= end_month:
            mask_target = (df['year'] == yr) & (df['month'] >= start_month) & (df['month'] <= end_month)
        else: 
            mask_target = (df['year'] == yr) & (df['month'] == start_month)
            
        target_data = df[mask_target]
        target_val = target_data['ratio'].mean() if not target_data.empty else 0
        
        # B. 获取基准月热度
        if base_month == 12:
            mask_base = (df['year'] == yr - 1) & (df['month'] == base_month)
        else:
            mask_base = (df['year'] == yr) & (df['month'] == base_month)
            
        base_data = df[mask_base]
        base_val = base_data['ratio'].mean() if not base_data.empty else 0.01 
        
        # C. 计算环比涨幅
        if base_val > 0.1: 
            growth = ((target_val - base_val) / base_val) * 100
            seasonal_growths.append(growth)
            peak_scores.append(target_val)
            
    if not seasonal_growths: return None
    
    avg_growth = sum(seasonal_growths) / len(seasonal_growths)
    avg_peak = sum(peak_scores) / len(peak_scores)
    win_count = len([g for g in seasonal_growths if g > 10]) 
    win_rate = (win_count / len(seasonal_growths)) * 100
    
    # 5. 评级
    tag, score = "😐 平淡", 50
    if win_rate >= 75 and avg_growth > 50 and avg_peak > 40:
        tag, score = "🔥 S级: 季节性暴涨", 100
    elif win_rate >= 60 and avg_growth > 20:
        tag, score = "📈 A级: 稳步上涨", 80
    elif avg_growth < -10:
        tag, score = "❄️ D级: 季节性转冷", 0
    elif avg_peak < 10:
        tag, score = "💤 流量过低", 20
        
    return {
        "评级": tag, 
        "选品得分": score, 
        "平均涨幅%": round(avg_growth, 1), 
        "区间热度(0-100)": round(avg_peak, 1), 
        "上涨胜率%": round(win_rate, 0), 
        "RawData": df
    }

# ================= 4. UI 界面 =================
st.title("📡 Naver 趋势雷达 (Ultra: 季节性爆发力版)")

with st.sidebar:
    st.header("1. 配置")
    client_id = st.text_input("Client ID", type="password")
    client_secret = st.text_input("Client Secret", type="password")
    
    st.divider()
    st.header("2. 规则")
    
    st.subheader("⏱️ 数据精度")
    time_unit_label = st.radio(
        "选择数据点密度",
        ('month', 'week', 'date'),
        index=0, 
        format_func=lambda x: {'month': '按月 (看大趋势)', 'week': '按周 (看节奏)', 'date': '按天 (看细节)'}[x]
    )
    
    st.divider()
    
    st.subheader("📅 目标月份区间")
    st.caption("逻辑：自动对比【前一个月】计算爆发力")
    month_range = st.slider("选择旺季区间", 1, 12, (10, 11), format="%d月")
    start_m, end_m = month_range
    
    compare_mode = st.radio("验证年份", (2, 3), format_func=lambda x: f"验证过去 {x} 年规律")

st.info(f"💡 当前逻辑：寻找在 **{start_m}-{end_m}月** 会比上个月暴涨的产品。（基于过去{compare_mode}年规律验证）")
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
            raw = get_datalab_trend(client_id, client_secret, kw, time_unit_label)
            analysis = analyze_custom_trend(raw, start_m, end_m, compare_mode)
            
            if analysis:
                results.append({
                    "赛道": kw,
                    "评级": analysis['评级'],
                    "得分": analysis['选品得分'],
                    "爆发力(环比%)": analysis['平均涨幅%'],
                    "区间热度": analysis['区间热度(0-100)'],
                    "RawData": analysis['RawData']
                })
            
            time.sleep(0.1)
            progress_bar.progress((i+1)/len(keywords))
            
        if results:
            df = pd.DataFrame(results).sort_values(by=['得分', '爆发力(环比%)'], ascending=[False, False])
            
            st.success("✅ 扫描完成！")
            
            # 结果表格 (修复了 use_container_width 警告)
            st.dataframe(
                df.drop(columns=['RawData', '得分']),
                width="stretch", 
                column_config={
                    "爆发力(环比%)": st.column_config.ProgressColumn(format="%.1f%%", min_value=-50, max_value=100),
                    "区间热度": st.column_config.ProgressColumn(min_value=0, max_value=100)
                }
            )
            
            st.divider()
            st.subheader("📊 历史走势 (交互增强版)")
            
            for _, row in df.head(5).iterrows(): 
                kw, raw_df = row['赛道'], row['RawData']
                fig = go.Figure()
                
                plot_years = sorted(raw_df['year'].unique())[-compare_mode-1:] 
                
                for yr in plot_years:
                    y_data = raw_df[raw_df['year'] == yr]
                    
                    fig.add_trace(go.Scatter(
                        x=y_data['period'], 
                        y=y_data['ratio'], 
                        mode='lines', 
                        name=f"{yr}年",
                        hovertemplate="<b>%{x|%Y-%m-%d}</b><br>热度: %{y:.0f}<extra></extra>"
                    ))
                
                fig.update_layout(
                    title=f"【{kw}】历史走势 ({time_unit_label})", 
                    xaxis_title="时间", 
                    yaxis_title="搜索热度", 
                    height=400,
                    hovermode="x unified", 
                    xaxis=dict(
                        tickformat="%Y-%m-%d",
                        showspikes=True,
                        spikemode="across",
                        spikesnap="cursor",
                        showline=True, showgrid=True
                    )
                )
                
                st.plotly_chart(fig, use_container_width=True)
