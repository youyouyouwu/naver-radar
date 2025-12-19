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
    page_title="Naver 核武器 (中文日期版)", 
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

# ================= 3. 引擎 B: DataLab API (天级数据) =================
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

# ================= 4. 计算核心 =================
def calculate_prediction(keyword, ads_keys, datalab_keys, target_date_start, target_date_end, cvr_rate, compare_years_depth):
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
    
    # Step 3: 计算倍数
    now_date = datetime.now().date()
    # 基准区间 = 过去30天
    base_end_md = now_date
    base_start_md = now_date - timedelta(days=30)
    
    multipliers = []
    this_year = datetime.now().year
    
    target_years_list = [this_year - i for i in range(1, compare_years_depth + 1)]
    
    for yr in target_years_list:
        try:
            # A. 历史基准区间
            h_base_start = base_start_md.replace(year=yr)
            h_base_end = base_end_md.replace(year=yr)
            
            # B. 历史目标区间
            h_target_start = target_date_start.replace(year=yr)
            h_target_end = target_date_end.replace(year=yr)
            
        except ValueError:
            continue
            
        # C. 提取数据
        mask_base = (df['period'].dt.date >= h_base_start) & (df['period'].dt.date <= h_base_end)
        val_base = df[mask_base]['ratio'].mean() if not df[mask_base].empty else 0.01
        
        mask_target = (df['period'].dt.date >= h_target_start) & (df['period'].dt.date <= h_target_end)
        val_target = df[mask_target]['ratio'].mean() if not df[mask_target].empty else 0
        
        if val_base > 0.1:
            m = val_target / val_base
            multipliers.append(m)
            
    if not multipliers: return None
    avg_multiplier = sum(multipliers) / len(multipliers)
    
    # Step 4: 最终预测
    days_in_target = (target_date_end - target_date_start).days + 1
    current_daily_avg = current_vol / 30
    
    predicted_total_vol = (current_daily_avg * avg_multiplier) * days_in_target
    predicted_total_sales = predicted_total_vol * (cvr_rate / 100)
    
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
        "🔍 预测区间总搜": int(predicted_total_vol),
        "💰 预测区间总单": int(predicted_total_sales),
        "RawData": df,
        "参考年份数": compare_years_depth,
        "天数": days_in_target
    }

# ================= 5. UI 界面 =================
st.title("☢️ Naver 选品核武器 (中文日期版)")

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
    st.write("### ⚙️ 第二步：预测设置")
    
    # 🔥🔥🔥 核心修改：拆分为两个独立的日期选择器 🔥🔥🔥
    st.caption("请选择您要预测的起止时间：")
    
    col1, col2 = st.columns(2)
    
    default_start = datetime.now().date() + timedelta(days=30)
    default_end = default_start + timedelta(days=14)
    
    with col1:
        t_date_start = st.date_input("开始日期 (Start)", default_start, format="YYYY/MM/DD")
    
    with col2:
        t_date_end = st.date_input("结束日期 (End)", default_end, format="YYYY/MM/DD")
        
    # 逻辑检查
    if t_date_start > t_date_end:
        st.error("⚠️ 结束日期不能早于开始日期！")

    compare_depth = st.radio(
        "参考历史年份", (1, 2, 3), index=1,
        format_func=lambda x: f"参考过去 {x} 年"
    )
    
    cvr = st.slider("Coupang 转化率", 3.0, 10.0, 5.0, 0.1, format="%.1f%%")

st.write("### 📝 第三步：输入关键词")
keywords_input = st.text_area("输入关键词 (每行一个)", height=150, placeholder="例如：\n감따는기구\n가습기")

if st.button("🚀 开始运行", type="primary"):
    # 阻断逻辑：如果日期选反了，不让跑
    if t_date_start > t_date_end:
        st.error("无法运行：请修正日期范围（结束日期必须晚于开始日期）")
    else:
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
            days_count = (t_date_end - t_date_start).days + 1
            st.info(f"✅ 正在预测 **{t_date_start}** 至 **{t_date_end}** (共{days_count}天) 的表现...")
            
            ads_conf = {'key': ads_key, 'secret': ads_secret, 'id': cust_id}
            lab_conf = {'id': datalab_id, 'secret': datalab_secret}
            
            results = []
            progress = st.progress(0)
            
            for i, kw in enumerate(kws):
                res = calculate_prediction(kw, ads_conf, lab_conf, t_date_start, t_date_end, cvr, compare_depth)
                if res: results.append(res)
                time.sleep(0.2)
                progress.progress((i+1)/len(kws))
                
            if results:
                df = pd.DataFrame(results).sort_values(by=['💰 预测区间总单'], ascending=False)
                st.success("✅ 预测完成！")
                
                st.dataframe(
                    df.drop(columns=['RawData', '得分', '参考年份数', '天数']),
                    use_container_width=True,
                    column_config={
                        "当前Search量": st.column_config.NumberColumn(format="%d", help="过去30天总量"),
                        "增长系数": st.column_config.NumberColumn(format="x %.2f"),
                        "🔍 预测区间总搜": st.column_config.ProgressColumn(format="%d", min_value=0, max_value=max(df['🔍 预测区间总搜'])),
                        "💰 预测区间总单": st.column_config.NumberColumn(format="%d 单", help=f"这{days_count}天的总预测单量"),
                        "竞争度": st.column_config.TextColumn()
                    }
                )
                
                st.divider()
                for _, row in df.head(3).iterrows():
                    kw, raw_df = row['关键词'], row['RawData']
                    depth = row['参考年份数']
                    
                    fig = go.Figure()
                    
                    years = sorted(raw_df['year'].unique())
                    target_years = [datetime.now().year - i for i in range(1, depth + 1)]
                    
                    for yr in years:
                        if yr in target_years:
                            y_data = raw_df[raw_df['year'] == yr]
                            fig.add_trace(go.Scatter(
                                x=y_data['period'], y=y_data['ratio'], 
                                mode='lines', name=f"{yr}年",
                                hovertemplate="<b>%{x|%Y-%m-%d}</b><br>热度: %{y:.1f}<extra></extra>"
                            ))
                    
                    ref_year = target_years[0] if target_years else years[-1]
                    
                    # 容错：防止闰年日期错误 (如2月29日映射到平年)
                    try:
                        v_start = t_date_start.replace(year=ref_year)
                        v_end = t_date_end.replace(year=ref_year)
                        
                        fig.add_vrect(x0=v_start, x1=v_end, 
                                      fillcolor="red", opacity=0.1, annotation_text="目标区间")
                    except:
                        pass # 如果日期映射失败就不画框了
                    
                    fig.update_layout(title=f"【{kw}】历史走势 (红色区域为你的预测时段)", height=350, hovermode="x unified")
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("⚠️ 运行结束，未得到有效数据。")
