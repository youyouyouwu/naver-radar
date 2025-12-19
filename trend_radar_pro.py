import streamlit as st
import pandas as pd
import requests
import json
import time
import plotly.graph_objects as go
from datetime import datetime, timedelta

st.set_page_config(page_title="Naver 趋势雷达 (Pro版)", page_icon="📡", layout="wide")

def get_datalab_trend(client_id, client_secret, keyword):
    url = "https://openapi.naver.com/v1/datalab/search"
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
        "Content-Type": "application/json"
    }
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * 4 + 30)
    body = {
        "startDate": start_date.strftime("%Y-%m-%d"),
        "endDate": end_date.strftime("%Y-%m-%d"),
        "timeUnit": "month",
        "keywordGroups": [{"groupName": keyword, "keywords": [keyword]}]
    }
    try:
        resp = requests.post(url, headers=headers, data=json.dumps(body), timeout=5)
        if resp.status_code == 200: return resp.json()
    except: return None
    return None

def analyze_custom_trend(data_json, start_month, end_month, compare_years):
    if not data_json or 'results' not in data_json or not data_json['results']: return None
    points = data_json['results'][0]['data']
    df = pd.DataFrame(points)
    df['period'] = pd.to_datetime(df['period'])
    df['month'] = df['period'].dt.month
    df['year'] = df['period'].dt.year
    df['ratio'] = df['ratio'].astype(float)
    
    yearly_performance = {}
    current_year = datetime.now().year
    years_to_analyze = range(current_year - compare_years, current_year)
    
    for yr in years_to_analyze:
        if start_month <= end_month:
            mask = (df['year'] == yr) & (df['month'] >= start_month) & (df['month'] <= end_month)
        else:
            mask = (df['year'] == yr) & (df['month'] == start_month) 
        period_data = df[mask]
        yearly_performance[yr] = period_data['ratio'].mean() if not period_data.empty else 0

    last_year = current_year - 1
    prev_year = current_year - 2
    old_year = current_year - 3
    growth_rates = []
    
    val_last = yearly_performance.get(last_year, 0)
    val_prev = yearly_performance.get(prev_year, 0)
    if val_prev > 1: growth_rates.append(((val_last - val_prev) / val_prev) * 100)
    else: growth_rates.append(0)
        
    if compare_years == 3:
        val_old = yearly_performance.get(old_year, 0)
        if val_old > 1: growth_rates.append(((val_prev - val_old) / val_old) * 100)
        else: growth_rates.append(0)
            
    if not growth_rates: return None
    avg_growth = sum(growth_rates) / len(growth_rates)
    win_count = len([g for g in growth_rates if g > 10])
    win_rate = (win_count / len(growth_rates)) * 100
    peak_score = val_last
    
    tag, score = "😐 观察", 50
    if compare_years == 3:
        if win_rate >= 66 and avg_growth > 20 and peak_score > 40: tag, score = "🔥 S级: 长期稳健爆款", 100
        elif avg_growth > 10: tag, score = "📈 A级: 上升通道", 80
    else:
        if avg_growth > 50 and peak_score > 40: tag, score = "🚀 S级: 近期黑马", 100
        elif avg_growth > 15: tag, score = "📈 A级: 增长中", 80
            
    if avg_growth < -10: tag, score = "❄️ D级: 下滑趋势", 0
    elif peak_score < 10: tag, score = "💤 流量太小", 20

    return {"评级": tag, "选品得分": score, "平均涨幅%": round(avg_growth, 1), 
            "区间热度(0-100)": round(peak_score, 1), "上涨胜率%": round(win_rate, 0), "RawData": df}

st.title("📡 Naver 趋势雷达 (Pro: 自定义区间版)")
with st.sidebar:
    st.header("1. API 配置")
    client_id = st.text_input("Client ID", type="password")
    client_secret = st.text_input("Client Secret", type="password")
    st.divider()
    st.header("2. 设定探测规则")
    month_range = st.slider("选择你要预测的月份范围", 1, 12, (11, 12), format="%d月")
    start_m, end_m = month_range
    st.divider()
    compare_mode = st.radio("选择回溯时间", (2, 3), format_func=lambda x: f"近 {x} 年环比 (YoY)")

keywords_text = st.text_area("输入赛道/类目词 (每行一个)", height=150, placeholder="滑雪\n加湿器\n露营\n圣诞节")

if st.button("🚀 开始雷达扫描", type="primary"):
    if not client_id or not keywords_text: st.error("请填写完整信息")
    else:
        keywords = [k.strip() for k in keywords_text.replace("\n", ",").split(",") if k.strip()]
        st.write(f"正在扫描 {len(keywords)} 个赛道...")
        results = []
        progress_bar = st.progress(0)
        
        for i, kw in enumerate(keywords):
            raw = get_datalab_trend(client_id, client_secret, kw)
            analysis = analyze_custom_trend(raw, start_m, end_m, compare_mode)
            if analysis:
                results.append({"赛道": kw, "评级": analysis['评级'], "得分": analysis['选品得分'], 
                                "平均涨幅%": analysis['平均涨幅%'], "区间热度": analysis['区间热度(0-100)'], 
                                "RawData": analysis['RawData']})
            time.sleep(0.1)
            progress_bar.progress((i+1)/len(keywords))
            
        if results:
            df = pd.DataFrame(results).sort_values(by=['得分', '平均涨幅%'], ascending=[False, False])
            st.success("✅ 扫描完成！")
            st.dataframe(df.drop(columns=['RawData', '得分']), use_container_width=True, 
                         column_config={"平均涨幅%": st.column_config.ProgressColumn(format="%.1f%%", min_value=-50, max_value=100), 
                                        "区间热度": st.column_config.ProgressColumn(min_value=0, max_value=100)})
            st.divider()
            st.subheader("📊 历史走势透视 (Top 3)")
            for _, row in df.head(3).iterrows():
                kw, raw_df = row['赛道'], row['RawData']
                fig = go.Figure()
                plot_years = sorted(raw_df['year'].unique())[-compare_mode-1:] 
                for yr in plot_years:
                    y_data = raw_df[raw_df['year'] == yr]
                    fig.add_trace(go.Scatter(x=y_data['month'], y=y_data['ratio'], mode='lines', name=f"{yr}年"))
                fig.update_layout(title=f"【{kw}】历史走势", xaxis_title="月份", yaxis_title="热度", height=300)
                fig.add_vrect(x0=start_m-0.5, x1=end_m+0.5, fillcolor="green", opacity=0.1, annotation_text="目标区间")
                st.plotly_chart(fig, use_container_width=True)