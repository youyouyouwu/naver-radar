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
    page_title="Naver 核武器 (1:1对标版)", 
    page_icon="☢️", 
    layout="wide"
)

# ================= 2. 引擎 A: Search Ad API =================
def generate_signature(timestamp, method, uri, secret_key):
    try:
        message = f"{timestamp}.{method}.{uri}"
        return base64.b64encode(hmac.new(secret_key.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).digest()).decode()
    except Exception as e:
        return None

def get_real_search_volume(api_key, secret_key, customer_id, keyword):
    base_url = "https://api.naver.com"
    uri = "/keywordstool"
    method = "GET"
    timestamp = str(int(time.time() * 1000))
    
    if not secret_key: return None
    signature = generate_signature(timestamp, method, uri, secret_key)
    if not signature: return None
    
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

# ================= 3. 引擎 B: DataLab API =================
def get_datalab_trend(client_id, client_secret, keyword):
    url = "https://openapi.naver.com/v1/datalab/search"
    headers = {
        "X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret, "Content-Type": "application/json"
    }
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * 4 + 30) 
    
    body = {
        "startDate": start_date.strftime("%Y-%m-%d"),
        "endDate": end_date.strftime("%Y-%m-%d"),
        "timeUnit": "date", 
        "keywordGroups": [{"groupName": keyword, "keywords": [keyword]}]
    }
    try:
        resp = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
        if resp.status_code == 200: return resp.json()
    except: return None
    return None

# ================= 4. 计算核心 (1:1 对标逻辑) =================
def calculate_prediction(keyword, ads_keys, datalab_keys, target_start_m, target_end_m, cvr_rate, volume_ratio, compare_years_depth):
    # Step 1: Ads 流量
    ads_data = get_real_search_volume(ads_keys['key'], ads_keys['secret'], ads_keys['id'], keyword)
    
    current_vol = 0
    comp_idx = "未知"
    if ads_data:
        current_vol = ads_data['total_vol']
        comp_idx = ads_data['compIdx']
    
    # Step 2: DataLab 趋势
    trend_data = get_datalab_trend(datalab_keys['id'], datalab_keys['secret'], keyword)
    if not trend_data or 'results' not in trend_data: return None
    points = trend_data['results'][0]['data']
    if not points: return None
    
    df = pd.DataFrame(points)
    df['period'] = pd.to_datetime(df['period'])
    df['ratio'] = df['ratio'].astype(float)
    df['year'] = df['period'].dt.year
    df['month'] = df['period'].dt.month
    
    # Step 3: 计算倍数
    current_month_real = datetime.now().month 
    base_month = current_month_real
    
    multipliers = []
    this_year = datetime.now().year
    target_years_list = [this_year - i for i in range(1, compare_years_depth + 1)]
    
    for yr in target_years_list:
        mask_base = (df['year'] == yr) & (df['month'] == base_month)
        val_base = df[mask_base]['ratio'].mean() if not df[mask_base].empty else 0.01
        
        if target_start_m <= target_end_m:
            mask_target = (df['year'] == yr) & (df['month'] >= target_start_m) & (df['month'] <= target_end_m)
        else: 
             mask_target = (df['year'] == yr) & ((df['month'] >= target_start_m) | (df['month'] <= target_end_m))
             
        val_target = df[mask_target]['ratio'].mean() if not df[mask_target].empty else 0
        
        if val_base > 0.5:
            m = val_target / val_base
            multipliers.append(m)
            
    if not multipliers: return None
    avg_multiplier = sum(multipliers) / len(multipliers)
    
    # --- Step 4: 最终预测 (逻辑更新：1:1 对标) ---
    
    # A. 预测 Naver 未来热度
    predicted_naver_vol = current_vol * avg_multiplier
    
    # B. 对标 Coupang 流量
    # 用户逻辑：Naver量 ≈ Coupang量 (系数默认100%)
    predicted_coupang_vol = predicted_naver_vol * (volume_ratio / 100)
    
    # C. 计算最终出单 (基于 Coupang 流量)
    predicted_monthly_sales = predicted_coupang_vol * (cvr_rate / 100)
    
    # D. 区间总数
    if target_end_m >= target_start_m:
        months_count = target_end_m - target_start_m + 1
    else:
        months_count = (12 - target_start_m + 1) + target_end_m
        
    total_season_sales = predicted_monthly_sales * months_count
    
    tag, score = "😐 平稳", 50
    if avg_multiplier > 3.0: tag, score = "🔥 S级: 爆发增长", 100
    elif avg_multiplier > 1.2: tag, score = "📈 A级: 稳步增长", 80
    elif avg_multiplier < 0.8: tag, score = "❄️ D级: 季节性回落", 0
    
    return {
        "关键词": keyword,
        "评级": tag,
        "竞争度": comp_idx,
        "当前Search量": int(current_vol),
        "增长系数": round(avg_multiplier, 2),
        "🔍 预测Naver热度": int(predicted_naver_vol),
        "🔵 预估Coupang流量": int(predicted_coupang_vol), 
        "💰 月均单量": int(predicted_monthly_sales),
        "📦 备货总单量": int(total_season_sales),
        "RawData": df,
        "参考年份数": compare_years_depth
    }

# ================= 5. UI 界面 =================
st.title("☢️ Naver 选品核武器 (1:1 对标版)")

with st.sidebar:
    st.write("### 🔑 第一步：填写密钥")
    with st.expander("Search Ad API (广告)", expanded=True):
        ads_key = st.text_input("Access License", type="password")
        ads_secret = st.text_input("Secret Key", type="password")
        cust_id = st.text_input("Customer ID", type="password")
        
    with st.expander("DataLab API (趋势)", expanded=True):
        datalab_id = st.text_input("Client ID", type="password")
        datalab_secret = st.text_input("Client Secret", type="password")
        
    st.divider()
    st.write("### ⚙️ 第二步：核心参数")
    
    st.caption("1. 目标月份：")
    target_range = st.slider("月份区间", 1, 12, (10, 11), format="%d月")
    t_start, t_end = target_range
    
    st.caption("2. 流量对标 (Naver vs Coupang)：")
    # 🔥🔥🔥 核心修改：改为流量对标系数，默认 100% 🔥🔥🔥
    volume_ratio = st.slider(
        "平台对标系数", 
        50, 150, 100, 10, 
        format="%d%%",
        help="【经验值】\n- 100%: Naver搜多少，Coupang就搜多少 (默认)\n- 120%: Coupang比Naver更火\n- 80%: Naver比Coupang更火"
    )
    
    st.caption("3. 转化率 (CVR)：")
    cvr = st.slider("转化率", 1.0, 10.0, 5.0, 0.1, format="%.1f%%")
    
    compare_depth = st.radio("参考历史年份", (1, 2, 3), index=1, format_func=lambda x: f"参考过去 {x} 年")

st.write("### 📝 第三步：输入关键词")
keywords_input = st.text_area("输入关键词 (每行一个)", height=150, placeholder="例如：\n감따는기구\n가습기")

if st.button("🚀 开始运行", type="primary"):
    missing_items = []
    if not ads_key: missing_items.append("Access License")
    if not ads_secret: missing_items.append("Secret Key")
    if not cust_id: missing_items.append("Customer ID")
    if not datalab_id: missing_items.append("Client ID")
    if not datalab_secret: missing_items.append("Client Secret")
    if not keywords_input: missing_items.append("关键词")

    if missing_items:
        st.error(f"❌ 请完善信息：\n" + "\n".join([f"- {item}" for item in missing_items]))
    else:
        kws = [k.strip() for k in keywords_input.replace("\n", ",").split(",") if k.strip()]
        if t_end >= t_start: m_count = t_end - t_start + 1
        else: m_count = (12 - t_start + 1) + t_end
        
        st.info(f"✅ 计算公式：Naver流量 x {volume_ratio}% (对标Coupang) x {cvr}% (转化率)")
        
        ads_conf = {'key': ads_key, 'secret': ads_secret, 'id': cust_id}
        lab_conf = {'id': datalab_id, 'secret': datalab_secret}
        
        results = []
        progress = st.progress(0)
        
        for i, kw in enumerate(kws):
            res = calculate_prediction(kw, ads_conf, lab_conf, t_start, t_end, cvr, volume_ratio, compare_depth)
            if res: results.append(res)
            time.sleep(0.2)
            progress.progress((i+1)/len(kws))
            
        if results:
            df = pd.DataFrame(results).sort_values(by=['📦 备货总单量'], ascending=False)
            st.success("✅ 预测完成！")
            
            st.dataframe(
                df.drop(columns=['RawData', '参考年份数']),
                use_container_width=True,
                column_config={
                    "当前Search量": st.column_config.NumberColumn(format="%d"),
                    "增长系数": st.column_config.NumberColumn(format="x %.2f"),
                    "🔍 预测Naver热度": st.column_config.NumberColumn(format="%d", help="Naver端预测值"),
                    "🔵 预估Coupang流量": st.column_config.NumberColumn(format="%d", help=f"按 {volume_ratio}% 对标系数折算"),
                    "💰 月均单量": st.column_config.NumberColumn(format="%d 单"),
                    "📦 备货总单量": st.column_config.NumberColumn(format="%d 单", help="最终备货参考"),
                    "竞争度": st.column_config.TextColumn()
                }
            )
            
            st.divider()
            for _, row in df.head(3).iterrows():
                kw, raw_df = row['关键词'], row['RawData']
                depth = row['参考年份数']
                fig = go.Figure()
                years = sorted(raw_df['year'].unique())
                this_year = datetime.now().year
                target_years = [this_year - i for i in range(1, depth + 1)]
                
                for yr in years:
                    if yr in target_years:
                        y_data = raw_df[raw_df['year'] == yr]
                        fig.add_trace(go.Scatter(x=y_data['period'], y=y_data['ratio'], mode='lines', name=f"{yr}年"))
                
                try:
                    ref_year = target_years[0]
                    v_start = datetime(ref_year, t_start, 1)
                    if t_end == 12: v_end = datetime(ref_year, 12, 31)
                    else: v_end = datetime(ref_year, t_end + 1, 1) - timedelta(days=1)
                    fig.add_vrect(x0=v_start, x1=v_end, fillcolor="red", opacity=0.1, annotation_text="旺季")
                except: pass
                
                fig.update_layout(title=f"【{kw}】历史走势", height=350, hovermode="x unified")
                st.plotly_chart(fig, use_container_width=True)
