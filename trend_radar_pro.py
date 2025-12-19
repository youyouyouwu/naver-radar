import streamlit as st
import pandas as pd
import requests
import json
import time
import hmac
import hashlib
import base64
import plotly.graph_objects as go
from datetime import datetime, timedelta

# ================= 1. 页面配置 =================
st.set_page_config(
    page_title="Naver 核武器 (Coupang实战版)", 
    page_icon="☢️", 
    layout="wide"
)

# ================= 2. 引擎 A: Search Ad API (获取当前真实基数) =================
def generate_signature(timestamp, method, uri, secret_key):
    message = f"{timestamp}.{method}.{uri}"
    return base64.b64encode(hmac.new(secret_key.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).digest()).decode()

def get_real_search_volume(api_key, secret_key, customer_id, keyword):
    """
    调用广告接口，获取近30天(即当前月份)的真实搜索量
    """
    base_url = "https://api.naver.com"
    uri = "/keywordstool"
    method = "GET"
    timestamp = str(int(time.time() * 1000))
    signature = generate_signature(timestamp, method, uri, secret_key)
    
    headers = {
        "X-Timestamp": timestamp, "X-API-KEY": api_key, "X-Customer": str(customer_id), "X-Signature": signature
    }
    
    try:
        resp = requests.get(base_url + uri, params={"hintKeywords": keyword, "showDetail": 1}, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if 'keywordList' in data and len(data['keywordList']) > 0:
                for item in data['keywordList']:
                    if item['relKeyword'].replace(" ", "") == keyword.replace(" ", ""):
                        pc = 10 if str(item['monthlyPcQcCnt']).startswith("<") else int(item['monthlyPcQcCnt'])
                        mo = 10 if str(item['monthlyMobileQcCnt']).startswith("<") else int(item['monthlyMobileQcCnt'])
                        return {"total_vol": pc + mo, "compIdx": item['compIdx']}
        return None
    except:
        return None

# ================= 3. 引擎 B: DataLab API (获取历史增长倍数) =================
def get_datalab_trend(client_id, client_secret, keyword):
    url = "https://openapi.naver.com/v1/datalab/search"
    headers = {
        "X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret, "Content-Type": "application/json"
    }
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * 4 + 30) # 取4年数据
    
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

# ================= 4. 中央计算核心 (算法逻辑) =================
def calculate_prediction(keyword, ads_keys, datalab_keys, target_start_m, target_end_m, cvr_rate):
    # Step 1: Ads 流量
    ads_data = get_real_search_volume(ads_keys['key'], ads_keys['secret'], ads_keys['id'], keyword)
    
    current_vol = 0
    comp_idx = "未知"
    
    if ads_data:
        current_vol = ads_data['total_vol']
        comp_idx = ads_data['compIdx']
    
    if current_vol < 10: return None

    # Step 2: DataLab 趋势
    trend_data = get_datalab_trend(datalab_keys['id'], datalab_keys['secret'], keyword)
    if not trend_data or 'results' not in trend_data: return None
    
    points = trend_data['results'][0]['data']
    if not points: return None
    
    df = pd.DataFrame(points)
    df['period'] = pd.to_datetime(df['period'])
    df['month'] = df['period'].dt.month
    df['year'] = df['period'].dt.year
    df['ratio'] = df['ratio'].astype(float)
    
    # Step 3: 计算倍数
    current_month_real = datetime.now().month 
    base_month = current_month_real
    
    multipliers = []
    years_list = df['year'].unique()
    this_year = datetime.now().year
    
    for yr in years_list:
        if yr >= this_year: continue 
        
        mask_base = (df['year'] == yr) & (df['month'] == base_month)
        val_base = df[mask_base]['ratio'].mean() if not df[mask_base].empty else 0.01
        
        if target_start_m <= target_end_m:
            mask_target = (df['year'] == yr) & (df['month'] >= target_start_m) & (df['month'] <= target_end_m)
        else:
             mask_target = (df['year'] == yr) & (df['month'] == target_start_m)
             
        val_target = df[mask_target]['ratio'].mean() if not df[mask_target].empty else 0
        
        if val_base > 0.5:
            m = val_target / val_base
            multipliers.append(m)
            
    if not multipliers: return None
    avg_multiplier = sum(multipliers) / len(multipliers)
    
    # Step 4: 最终预测
    predicted_monthly_vol = current_vol * avg_multiplier
    predicted_monthly_sales = predicted_monthly_vol * (cvr_rate / 100)
    
    # 评级
    tag, score = "😐 平稳", 50
    if avg_multiplier > 3.0: tag, score = "🔥 S级: 爆发增长", 100
    elif avg_multiplier > 1.2: tag, score = "📈 A级: 稳步增长", 80
    elif avg_multiplier < 0.8: tag, score = "❄️ D级: 季节性回落", 0
    
    return {
        "关键词": keyword,
        "评级": tag,
        "得分": score,
        "竞争度": comp_idx,
        "当前Search量": int(current_vol),
        "增长系数": round(avg_multiplier, 2),
        "🔍 预测月均搜索": int(predicted_monthly_vol),
        "💰 预测月均出单": int(predicted_monthly_sales),
        "RawData": df
    }

# ================= 5. UI 界面 =================
st.title("☢️ Naver 选品核武器 (Coupang 实战版)")
st.caption("逻辑：Ads流量 × 趋势倍数 × 转化率 = 真实备货参考")

with st.sidebar:
    with st.expander("1. Search Ad API (Key)", expanded=True):
        ads_key = st.text_input("Access License", type="password")
        ads_secret = st.text_input("Secret Key", type="password")
        cust_id = st.text_input("Customer ID", type="password")
        
    with st.expander("2. DataLab API (Key)", expanded=True):
        datalab_id = st.text_input("Client ID", type="password")
        datalab_secret = st.text_input("Client Secret", type="password")
        
    st.divider()
    st.header("3. 预测目标")
    
    target_range = st.slider("选择预测区间", 1, 12, (10, 11), format="%d月")
    t_start, t_end = target_range
    
    # 🔥🔥🔥 核心修改区：转化率 3.0% - 10.0% 🔥🔥🔥
    cvr = st.slider(
        "Coupang 转化率 (CVR)", 
        3.0, 10.0, 5.0, 0.1, 
        format="%.1f%%",
        help="3%%是及格线，5%%是优良，10%%是爆款天花板。"
    )
    
    st.info(f"💡 当前标准：按 **{cvr}%** 的转化率计算 **{t_start}-{t_end}月** 的出单潜力。")

keywords_input = st.text_area("输入关键词 (每行一个)", height=150, placeholder="감따는기구\n가습기")

if st.button("🚀 开始双引擎预测", type="primary"):
    if not all([ads_key, ads_secret, cust_id, datalab_id, datalab_secret, keywords_input]):
        st.error("⚠️ 请填写所有 5 个 API Key！")
    else:
        kws = [k.strip() for k in keywords_input.replace("\n", ",").split(",") if k.strip()]
        st.write(f"正在分析 {len(kws)} 个赛道，基准月：{datetime.now().month}月 -> 目标：{t_start}-{t_end}月...")
        
        ads_conf = {'key': ads_key, 'secret': ads_secret, 'id': cust_id}
        lab_conf = {'id': datalab_id, 'secret': datalab_secret}
        
        results = []
        progress = st.progress(0)
        
        for i, kw in enumerate(kws):
            res = calculate_prediction(kw, ads_conf, lab_conf, t_start, t_end, cvr)
            if res: results.append(res)
            time.sleep(0.2)
            progress.progress((i+1)/len(kws))
            
        if results:
            df = pd.DataFrame(results).sort_values(by=['💰 预测月均出单'], ascending=False)
            st.success("✅ 预测完成！")
            
            st.dataframe(
                df.drop(columns=['RawData', '得分']),
                use_container_width=True,
                column_config={
                    "当前Search量": st.column_config.NumberColumn(format="%d"),
                    "增长系数": st.column_config.NumberColumn(format="x %.2f"),
                    "🔍 预测月均搜索": st.column_config.ProgressColumn(format="%d", min_value=0, max_value=max(df['🔍 预测月均搜索'])),
                    "💰 预测月均出单": st.column_config.NumberColumn(format="%d 单", help="按设定转化率计算"),
                    "竞争度": st.column_config.TextColumn(help="Low=蓝海")
                }
            )
            
            st.divider()
            st.subheader("📊 历史验证")
            for _, row in df.head(3).iterrows():
                kw, raw_df = row['关键词'], row['RawData']
                fig = go.Figure()
                years = sorted(raw_df['year'].unique())[-3:]
                for yr in years:
                    y_data = raw_df[raw_df['year'] == yr]
                    fig.add_trace(go.Scatter(x=y_data['period'], y=y_data['ratio'], mode='lines', name=f"{yr}年"))
                
                fig.add_vrect(x0=f"{years[-1]}-{t_start:02d}-01", x1=f"{years[-1]}-{t_end:02d}-28", 
                              fillcolor="red", opacity=0.1, annotation_text="预测区间")
                
                fig.update_layout(title=f"【{kw}】历史走势", height=300, hovermode="x unified")
                st.plotly_chart(fig, use_container_width=True)
