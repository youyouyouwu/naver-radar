# ================= 3. 核心逻辑：分析算法 (修复版：专注季节性爆发力) =================
def analyze_custom_trend(data_json, start_month, end_month, compare_years):
    # 1. 基础检查
    if not data_json or 'results' not in data_json or not data_json['results']: return None
    points = data_json['results'][0]['data']
    if not points: return None
        
    df = pd.DataFrame(points)
    if 'period' not in df.columns: return None

    df['period'] = pd.to_datetime(df['period'])
    df['month'] = df['period'].dt.month
    df['year'] = df['period'].dt.year
    df['ratio'] = df['ratio'].astype(float)
    
    # 2. 确定“对比基准月”
    # 逻辑：如果您选了 10-11月，我们就拿 9月 (区间前一个月) 来做对比基准
    # 这样算出的是：进入这个区间后，流量暴涨了多少倍？
    base_month = start_month - 1
    if base_month == 0: base_month = 12 # 处理跨年：如果选1月，基准就是去年12月
    
    seasonal_growths = [] # 存储每一年的季节性涨幅
    peak_scores = []      # 存储每一年的热度峰值
    
    current_year = datetime.now().year
    # 根据用户选择，回溯过去 N 年 (不含今年，因为今年还没过完)
    years_to_analyze = range(current_year - compare_years, current_year)
    
    for yr in years_to_analyze:
        # A. 获取“目标区间”的热度 (例如 10-11月)
        if start_month <= end_month:
            mask_target = (df['year'] == yr) & (df['month'] >= start_month) & (df['month'] <= end_month)
        else: # 跨年区间暂简化
            mask_target = (df['year'] == yr) & (df['month'] == start_month)
            
        target_data = df[mask_target]
        target_val = target_data['ratio'].mean() if not target_data.empty else 0
        
        # B. 获取“基准月”的热度 (例如 9月)
        # 注意处理跨年基准 (比如目标是1月，基准是去年12月)
        if base_month == 12:
            mask_base = (df['year'] == yr - 1) & (df['month'] == base_month)
        else:
            mask_base = (df['year'] == yr) & (df['month'] == base_month)
            
        base_data = df[mask_base]
        base_val = base_data['ratio'].mean() if not base_data.empty else 0.01 # 防止除以0
        
        # C. 计算这一年的“季节性爆发力” (环比涨幅)
        # 逻辑：(目标 - 基准) / 基准
        if base_val > 0.1: # 过滤噪音
            growth = ((target_val - base_val) / base_val) * 100
            seasonal_growths.append(growth)
            peak_scores.append(target_val)
            
    # 3. 综合评分
    if not seasonal_growths: return None
    
    # 平均爆发力 (过去几年的平均环比涨幅)
    avg_growth = sum(seasonal_growths) / len(seasonal_growths)
    # 平均热度 (是不是主战场)
    avg_peak = sum(peak_scores) / len(peak_scores)
    # 胜率 (过去几年里，有几年是涨的？)
    win_count = len([g for g in seasonal_growths if g > 10]) # 涨幅>10%算涨
    win_rate = (win_count / len(seasonal_growths)) * 100
    
    # 4. 评级
    tag, score = "😐 平淡", 50
    
    # 评级逻辑：完全看爆发力和胜率
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
        "平均涨幅%": round(avg_growth, 1), # 这里显示的是季节性环比了！
        "区间热度(0-100)": round(avg_peak, 1), 
        "上涨胜率%": round(win_rate, 0), 
        "RawData": df
    }
