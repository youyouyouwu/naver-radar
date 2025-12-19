# ... (上面的代码不用动) ...
            
            st.divider()
            st.subheader("📊 历史走势 (交互增强版)")
            
            for _, row in df.head(3).iterrows():
                kw, raw_df = row['赛道'], row['RawData']
                fig = go.Figure()
                
                # 只画最近 N 年的线
                plot_years = sorted(raw_df['year'].unique())[-compare_mode-1:] 
                
                for yr in plot_years:
                    y_data = raw_df[raw_df['year'] == yr]
                    
                    # 🎨 每一年的线
                    fig.add_trace(go.Scatter(
                        x=y_data['period'], 
                        y=y_data['ratio'], 
                        mode='lines', 
                        name=f"{yr}年",
                        # ✨ 魔法 1: 自定义鼠标悬停显示的格式
                        # %{x|%Y-%m-%d} 意思是：把日期格式化为 年-月-日
                        # %{y:.0f} 意思是：热度只显示整数，不要小数点
                        hovertemplate="<b>%{x|%Y-%m-%d}</b><br>热度: %{y:.0f}<extra></extra>"
                    ))
                
                # 🎨 图表整体布局设置
                fig.update_layout(
                    title=f"【{kw}】历史走势 ({time_unit_label})", 
                    xaxis_title="时间", 
                    yaxis_title="搜索热度", 
                    height=400,
                    
                    # ✨ 魔法 2: 开启“Naver同款”垂直准星
                    # 'x unified' 会显示一条垂直线，同时显示该时间点所有年份的数据
                    # 如果你觉得太乱，可以改成 'x'，就只显示鼠标指的那个点
                    hovermode="x unified",
                    
                    # 让 X 轴日期显示更聪明（自动根据缩放调整）
                    xaxis=dict(
                        tickformat="%Y-%m-%d",
                        showspikes=True, # 显示垂直辅助线
                        spikemode="across",
                        spikesnap="cursor",
                        showline=True, showgrid=True
                    )
                )
                
                st.plotly_chart(fig, use_container_width=True)
