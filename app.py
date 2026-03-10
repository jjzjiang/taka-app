import streamlit as st
import pandas as pd
import os
from datetime import datetime, timedelta

# --- 1. 配置与文件初始化 ---
st.set_page_config(page_title="Taka 零售终极管理系统", layout="wide")
STOCK_FILE = "taka_stock_v11_final.csv" 
SALES_FILE = "taka_sales_v11_final.csv"
LOW_STOCK_THRESHOLD = 3

STOCK_COLS = ['商品名称', '颜色', '进价成本', '售卖价格', '应收到数量', '展示数量', '货柜数量', '储物间数量', '坏货数量', '已售出数量', '总库存']
SALES_COLS = ['日期', '商品名称', '颜色', '销售数量', '成交单价', '总营业额']

def load_data(file, columns):
    if not os.path.exists(file):
        df = pd.DataFrame(columns=columns)
        df.to_csv(file, index=False)
        return df
    df = pd.read_csv(file)
    for col in columns:
        if col not in df.columns: df[col] = 0
    return df[columns]

df_stock = load_data(STOCK_FILE, STOCK_COLS)
df_sales = load_data(SALES_FILE, SALES_COLS)

# --- 2. 侧边栏：核心管理与备份恢复 ---
with st.sidebar:
    st.header("🛠️ 核心管理")
    with st.expander("➕ 新增产品 (Add SKU)"):
        with st.form("new_sku"):
            n_name = st.text_input("产品名称")
            n_color = st.text_input("颜色")
            c1, c2, c3 = st.columns(3)
            n_cost, n_price, n_expect = c1.number_input("进价"), c2.number_input("售价"), c3.number_input("应收")
            i1, i2, i3, i4 = st.columns(4)
            n_disp, n_shelf, n_stor, n_dmg = i1.number_input("展示"), i2.number_input("货柜"), i3.number_input("储物"), i4.number_input("坏货")
            if st.form_submit_button("确认录入"):
                if n_name and n_color:
                    total = n_disp + n_shelf + n_stor + n_dmg
                    new_r = pd.DataFrame([[n_name, n_color, n_cost, n_price, n_expect, n_disp, n_shelf, n_stor, n_dmg, 0, total]], columns=STOCK_COLS)
                    pd.concat([df_stock, new_r], ignore_index=True).to_csv(STOCK_FILE, index=False)
                    st.rerun()

    st.divider()
    st.write("### 💾 数据中心")
    st.download_button("📥 备份库存", df_stock.to_csv(index=False).encode('utf-8-sig'), "stock.csv", "text/csv")
    st.download_button("📥 备份流水", df_sales.to_csv(index=False).encode('utf-8-sig'), "sales.csv", "text/csv")
    with st.expander("📂 恢复备份 (CSV)"):
        u_st = st.file_uploader("恢复库存", type="csv")
        if u_st and st.button("覆盖库存"):
            pd.read_csv(u_st).to_csv(STOCK_FILE, index=False); st.rerun()
        u_sl = st.file_uploader("恢复流水", type="csv")
        if u_sl and st.button("覆盖流水"):
            pd.read_csv(u_sl).to_csv(SALES_FILE, index=False); st.rerun()

# --- 3. 辅助功能 ---
q = st.text_input("🔍 快速筛选 SKU 或颜色...", placeholder="搜索将同步联动所有标签页")
def get_f(df, q):
    if q and not df.empty:
        return df[df['商品名称'].str.contains(q, case=False, na=False) | df['颜色'].str.contains(q, case=False, na=False)]
    return df

# --- 4. 主界面布局 ---
st.title("🏙️ Takashimaya 零售管理系统")
t1, t2, t3 = st.tabs(["📊 库存看板与批量管理", "💰 销售记账 (批量撤销)", "📈 财务多维分析"])

with t1:
    st.subheader("库存实物分布 (勾选以进行批量删除或编辑)")
    f_stock = get_f(df_stock, q)
    
    if not f_stock.empty:
        v_df = f_stock.copy()
        int_cols = ['应收到数量', '已售出数量', '总库存', '展示数量', '货柜数量', '储物间数量', '坏货数量']
        for col in int_cols: v_df[col] = v_df[col].fillna(0).astype(int)
        
        v_df.insert(0, "选择", False)
        
        # 使用 data_editor 并绑定 key
        edited_stock = st.data_editor(
            v_df[['选择', '商品名称', '颜色', '应收到数量', '已售出数量', '总库存', '展示数量', '货柜数量', '储物间数量', '坏货数量', '售卖价格']],
            column_config={"选择": st.column_config.CheckboxColumn("选择", default=False)},
            disabled=[col for col in v_df.columns if col != "选择"],
            use_container_width=True, hide_index=True, key="stock_editor"
        )
        
        selected_stock = edited_stock[edited_stock["选择"] == True]
        
        # 批量操作按钮
        if not selected_stock.empty:
            col_btn1, col_btn2, col_btn3 = st.columns([1.5, 1.5, 4]) # 调整列宽容纳新按钮
            with col_btn1:
                if st.button("🗑️ 批量删除选中", type="primary"):
                    for _, row in selected_stock.iterrows():
                        df_stock = df_stock[~((df_stock['商品名称'] == row['商品名称']) & (df_stock['颜色'] == row['颜色']))]
                    df_stock.to_csv(STOCK_FILE, index=False)
                    if "stock_editor" in st.session_state: del st.session_state["stock_editor"] # 删除后清空选中状态
                    st.rerun()
            with col_btn2:
                # 新增：取消选中按钮
                if st.button("🔄 取消所有选中", key="cancel_stock"):
                    if "stock_editor" in st.session_state:
                        del st.session_state["stock_editor"]
                    st.rerun()
            
            # 如果只选了一个，开启编辑模式
            if len(selected_stock) == 1:
                st.divider()
                st.write("### ⚙️ 编辑选中商品信息")
                row = selected_stock.iloc[0]
                orig_idx = df_stock[(df_stock['商品名称'] == row['商品名称']) & (df_stock['颜色'] == row['颜色'])].index[0]
                
                with st.form("edit_selected_stock"):
                    e_name = st.text_input("产品名称", value=df_stock.at[orig_idx, '商品名称'])
                    c1, c2, c3 = st.columns(3)
                    e_cost, e_price, e_sold = c1.number_input("进价", value=float(df_stock.at[orig_idx, '进价成本'])), c2.number_input("售价", value=float(df_stock.at[orig_idx, '售卖价格'])), c3.number_input("已售修正", value=int(df_stock.at[orig_idx, '已售出数量']))
                    i1, i2, i3, i4, i5 = st.columns(5)
                    e_exp, e_dis, e_sh, e_st, e_dm = i1.number_input("应收", value=int(df_stock.at[orig_idx, '应收到数量'])), i2.number_input("展示", value=int(df_stock.at[orig_idx, '展示数量'])), i3.number_input("货柜", value=int(df_stock.at[orig_idx, '货柜数量'])), i4.number_input("储物", value=int(df_stock.at[orig_idx, '储物间数量'])), i5.number_input("坏货", value=int(df_stock.at[orig_idx, '坏货数量']))
                    if st.form_submit_button("保存校准"):
                        df_stock.at[orig_idx, '商品名称'] = e_name
                        df_stock.at[orig_idx, '进价成本'], df_stock.at[orig_idx, '售卖价格'], df_stock.at[orig_idx, '已售出数量'] = e_cost, e_price, e_sold
                        df_stock.at[orig_idx, '应收到数量'], df_stock.at[orig_idx, '展示数量'], df_stock.at[orig_idx, '货柜数量'], df_stock.at[orig_idx, '储物间数量'], df_stock.at[orig_idx, '坏货数量'] = e_exp, e_dis, e_sh, e_st, e_dm
                        df_stock.at[orig_idx, '总库存'] = e_dis + e_sh + e_st + e_dm
                        df_stock.to_csv(STOCK_FILE, index=False)
                        if "stock_editor" in st.session_state: del st.session_state["stock_editor"] # 保存后清空选中状态
                        st.rerun()
        else:
            st.info("💡 勾选上方复选框可开启批量删除或单项编辑。")
    else:
        st.info("暂无库存数据，请先通过侧边栏添加。")

with t2:
    st.subheader("销售记账与流水管理")
    with st.expander("➕ 新增销售", expanded=True):
        f_opts = get_f(df_stock, q).copy() 
        if not f_opts.empty:
            f_opts['label'] = f_opts['商品名称'] + " (" + f_opts['颜色'] + ")" 
            with st.form("add_sale"):
                s_l = st.selectbox("商品", f_opts['label'])
                selected_row = f_opts[f_opts['label'] == s_l].iloc[0]
                default_price = float(selected_row['售卖价格'])
                
                c1, c2 = st.columns(2)
                s_q, s_p = c1.number_input("数量", 1), c2.number_input("单价", value=default_price)
                s_d = st.date_input("日期", value=datetime.now())
                
                if st.form_submit_button("确认"):
                    idx_p = df_stock[(df_stock['商品名称'] == selected_row['商品名称']) & (df_stock['颜色'] == selected_row['颜色'])].index[0]
                    new_s = pd.DataFrame([[s_d.strftime("%Y-%m-%d"), df_stock.at[idx_p,'商品名称'], df_stock.at[idx_p,'颜色'], s_q, s_p, s_q*s_p]], columns=SALES_COLS)
                    pd.concat([new_s, df_sales], ignore_index=True).to_csv(SALES_FILE, index=False)
                    
                    df_stock.at[idx_p, '货柜数量'] -= s_q
                    df_stock.at[idx_p, '已售出数量'] += s_q
                    df_stock.at[idx_p, '总库存'] = df_stock.iloc[idx_p][['展示数量', '货柜数量', '储物间数量', '坏货数量']].sum()
                    
                    df_stock.to_csv(STOCK_FILE, index=False) 
                    st.rerun()

    st.divider()
    f_sl = get_f(df_sales, q)
    if not f_sl.empty:
        f_sl_sel = f_sl.copy(); f_sl_sel.insert(0, "选择", False)
        # 为流水表的 editor 也加上 key
        edt = st.data_editor(f_sl_sel, column_config={"选择": st.column_config.CheckboxColumn("选择", default=False)}, disabled=f_sl.columns, use_container_width=True, hide_index=True, key="sales_editor")
        sel = edt[edt["选择"] == True]
        
        if not sel.empty:
            sc1, sc2, sc3 = st.columns([1.5, 1.5, 4])
            with sc1:
                if st.button("🔴 批量撤销流水", type="primary"):
                    for _, r in sel.iterrows():
                        m = df_stock[(df_stock['商品名称']==r['商品名称']) & (df_stock['颜色']==r['颜色'])].index
                        if not m.empty:
                            df_stock.at[m[0], '货柜数量'] += r['销售数量']; df_stock.at[m[0], '已售出数量'] -= r['销售数量']
                            df_stock.at[m[0], '总库存'] = df_stock.iloc[m[0]][['展示数量', '货柜数量', '储物间数量', '坏货数量']].sum()
                    for _, r in sel.iterrows():
                        df_sales = df_sales[~((df_sales['日期']==r['日期']) & (df_sales['商品名称']==r['商品名称']) & (df_sales['颜色']==r['颜色']) & (df_sales['销售数量']==r['销售数量']))]
                    df_stock.to_csv(STOCK_FILE, index=False); df_sales.to_csv(SALES_FILE, index=False)
                    if "sales_editor" in st.session_state: del st.session_state["sales_editor"] # 撤销后清空选中状态
                    st.rerun()
            with sc2:
                # 新增：取消流水选中按钮
                if st.button("🔄 取消所有选中", key="cancel_sales"):
                    if "sales_editor" in st.session_state:
                        del st.session_state["sales_editor"]
                    st.rerun()

with t3:
    st.subheader("📊 财务日历报表")
    if not df_sales.empty:
        df_sales['日期_dt'] = pd.to_datetime(df_sales['日期'])
        sel_range = st.date_input("选择查看时间段", value=[df_sales['日期_dt'].min(), df_sales['日期_dt'].max()])
        if len(sel_range) == 2:
            start, end = sel_range
            f_sales_range = df_sales[(df_sales['日期_dt'] >= pd.Timestamp(start)) & (df_sales['日期_dt'] <= pd.Timestamp(end))].copy()
            period = st.radio("维度", ["Daily", "Weekly", "Monthly"], horizontal=True)
            if "Daily" in period: f_sales_range['周期'] = f_sales_range['日期_dt'].dt.strftime('%Y-%m-%d')
            elif "Weekly" in period: f_sales_range['周期'] = (f_sales_range['日期_dt'] - pd.to_timedelta(f_sales_range['日期_dt'].dt.dayofweek, unit='D')).dt.strftime('Week of %b %d')
            else: f_sales_range['周期'] = f_sales_range['日期_dt'].dt.strftime('%Y-%m')
            
            summ = f_sales_range.groupby(['周期', '商品名称', '颜色']).agg({'销售数量':'sum', '总营业额':'sum'}).reset_index()
            summ = summ.merge(df_stock[['商品名称', '颜色', '进价成本']], on=['商品名称', '颜色'], how='left')
            summ['具体毛利'] = summ['总营业额'] - (summ['销售数量'] * summ['进价成本'])
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("总营业额", f"${summ['总营业额'].sum():.2f}")
            c2.metric("具体毛利", f"${summ['具体毛利'].sum():.2f}")
            c3.metric("总售出件数", f"{int(summ['销售数量'].sum())} 件")
            avg_m = summ['具体毛利'].sum()/summ['总营业额'].sum()*100 if summ['总营业额'].sum()>0 else 0
            c4.metric("平均毛利率", f"{avg_m:.1f}%")
            
            st.dataframe(get_f(summ.sort_values('周期', ascending=False), q).style.format({'总营业额':"${:.2f}", '具体毛利':"${:.2f}", '销售数量':"{:d}"}), use_container_width=True)
