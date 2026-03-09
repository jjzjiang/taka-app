import streamlit as st
import pandas as pd
import os
from datetime import datetime, timedelta

# --- 1. 初始化与稳健加载 ---
st.set_page_config(page_title="Taka 零售与财务专业版", layout="wide")
# 升级到 v7 版本确保所有列（含坏货、已售、应收）物理对齐
STOCK_FILE = "taka_stock_final_v7.csv" 
SALES_FILE = "taka_sales_final_v7.csv"

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

# --- 2. 侧边栏：核心管理与备份 ---
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
    with st.expander("📂 恢复数据"):
        u_st = st.file_uploader("恢复库存", type="csv")
        if u_st and st.button("确认覆盖库存"):
            pd.read_csv(u_st).to_csv(STOCK_FILE, index=False)
            st.rerun()
        u_sl = st.file_uploader("恢复流水", type="csv")
        if u_sl and st.button("确认覆盖销售"):
            pd.read_csv(u_sl).to_csv(SALES_FILE, index=False)
            st.rerun()

# --- 3. 筛选逻辑 ---
st.write("### 🔍 SKU 快速筛选")
q = st.text_input("输入产品名或颜色查找...", placeholder="实时联动报表与下拉菜单")

def get_f(df, q):
    if q and not df.empty:
        return df[df['商品名称'].str.contains(q, case=False, na=False) | df['颜色'].str.contains(q, case=False, na=False)]
    return df

# --- 4. 主界面 ---
t1, t2, t3 = st.tabs(["📊 库存看板与编辑", "💰 批量记账管理", "📈 周期财务分析"])

with t1:
    f_stock = get_f(df_stock, q)
    view_df = f_stock.copy()
    view_df['单件利润'] = view_df['售卖价格'] - view_df['进价成本']
    view_df['毛利率'] = ((view_df['单件利润'] / view_df['售卖价格']) * 100).fillna(0).map("{:.1f}%".format)
    st.dataframe(view_df[['商品名称', '颜色', '售卖价格', '毛利率', '应收到数量', '已售出数量', '坏货数量', '展示数量', '货柜数量', '储物间数量', '总库存']], use_container_width=True)
    
    if not df_stock.empty:
        st.divider()
        st.write("### ⚙️ 信息/坏货校准 (Edit)")
        df_stock['label'] = df_stock['商品名称'] + " (" + df_stock['颜色'] + ")"
        target = st.selectbox("选择商品", df_stock['label'])
        idx = df_stock[df_stock['label'] == target].index[0]
        with st.form("edit_stock"):
            e_name = st.text_input("名称", value=df_stock.at[idx, '商品名称'])
            c1, c2, c3 = st.columns(3)
            e_cost, e_price, e_sold = c1.number_input("成本", value=float(df_stock.at[idx, '进价成本'])), c2.number_input("售价", value=float(df_stock.at[idx, '售卖价格'])), c3.number_input("已售修正", value=int(df_stock.at[idx, '已售出数量']))
            i1, i2, i3, i4, i5 = st.columns(5)
            e_exp, e_dis, e_sh, e_st, e_dm = i1.number_input("应收", value=int(df_stock.at[idx, '应收到数量'])), i2.number_input("展示", value=int(df_stock.at[idx, '展示数量'])), i3.number_input("货柜", value=int(df_stock.at[idx, '货柜数量'])), i4.number_input("储物", value=int(df_stock.at[idx, '储物间数量'])), i5.number_input("坏货", value=int(df_stock.at[idx, '坏货数量']))
            if st.form_submit_button("保存校准"):
                df_stock.at[idx, '商品名称'] = e_name
                df_stock.at[idx, '进价成本'], df_stock.at[idx, '售卖价格'], df_stock.at[idx, '已售出数量'] = e_cost, e_price, e_sold
                df_stock.at[idx, '应收到数量'], df_stock.at[idx, '展示数量'], df_stock.at[idx, '货柜数量'], df_stock.at[idx, '储物间数量'], df_stock.at[idx, '坏货数量'] = e_exp, e_dis, e_sh, e_st, e_dm
                df_stock.at[idx, '总库存'] = e_dis + e_sh + e_st + e_dm
                df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                st.rerun()

with t2:
    st.subheader("销售记账")
    with st.expander("➕ 新增销售", expanded=True):
        f_opts = get_f(df_stock, q)
        if not f_opts.empty:
            df_stock['label'] = df_stock['商品名称'] + " (" + df_stock['颜色'] + ")"
            with st.form("add_sale"):
                s_l = st.selectbox("商品", f_opts['label'])
                c1, c2 = st.columns(2)
                s_q = c1.number_input("数量", min_value=1, step=1)
                idx_p = df_stock[df_stock['label'] == s_l].index[0]
                s_p = c2.number_input("单价", value=float(df_stock.at[idx_p, '售卖价格']))
                s_d = st.date_input("日期", value=datetime.now())
                if st.form_submit_button("确认记账"):
                    # 修复 ValueError
                    new_s = pd.DataFrame([[s_d.strftime("%Y-%m-%d"), df_stock.at[idx_p, '商品名称'], df_stock.at[idx_p, '颜色'], s_q, s_p, s_q*s_p]], columns=SALES_COLS)
                    pd.concat([new_s, df_sales], ignore_index=True).to_csv(SALES_FILE, index=False)
                    df_stock.at[idx_p, '货柜数量'] -= s_q
                    df_stock.at[idx_p, '已售出数量'] += s_q
                    df_stock.at[idx_p, '总库存'] = df_stock.iloc[idx_p][['展示数量', '货柜数量', '储物间数量', '坏货数量']].sum()
                    df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                    st.rerun()
    
    st.divider()
    st.write("### 🧾 勾选批量撤销记录")
    f_sl = get_f(df_sales, q)
    if not f_sl.empty:
        f_sl_sel = f_sl.copy()
        f_sl_sel.insert(0, "选择", False)
        edt = st.data_editor(f_sl_sel, column_config={"选择": st.column_config.CheckboxColumn("选择", default=False)}, disabled=f_sl.columns, use_container_width=True, hide_index=True)
        sel = edt[edt["选择"] == True]
        if not sel.empty and st.button("🔴 批量撤销", type="primary"):
            for _, r in sel.iterrows():
                m = df_stock[(df_stock['商品名称']==r['商品名称']) & (df_stock['颜色']==r['颜色'])].index
                if not m.empty:
                    df_stock.at[m[0], '货柜数量'] += r['销售数量']
                    df_stock.at[m[0], '已售出数量'] -= r['销售数量']
                    df_stock.at[m[0], '总库存'] = df_stock.iloc[m[0]][['展示数量', '货柜数量', '储物间数量', '坏货数量']].sum()
            for _, r in sel.iterrows():
                df_sales = df_sales[~((df_sales['日期']==r['日期']) & (df_sales['商品名称']==r['商品名称']) & (df_sales['颜色']==r['颜色']) & (df_sales['销售数量']==r['销售数量']))]
            df_stock.to_csv(STOCK_FILE, index=False); df_sales.to_csv(SALES_FILE, index=False); st.rerun()

with t3:
    st.subheader("📈 周期财务分析")
    if not df_sales.empty:
        period = st.radio("时间粒度", ["Daily", "Weekly (Mon Start)", "Monthly"], horizontal=True)
        rpt = df_sales.copy()
        rpt['日期'] = pd.to_datetime(rpt['日期'])
        # 修复 Weekly 逻辑
        if "Daily" in period: rpt['周期'] = rpt['日期'].dt.strftime('%Y-%m-%d')
        elif "Weekly" in period: rpt['周期'] = (rpt['日期'] - pd.to_timedelta(rpt['日期'].dt.dayofweek, unit='D')).dt.strftime('%Y-%m-%d')
        else: rpt['周期'] = rpt['日期'].dt.strftime('%Y-%m')
        
        summ = rpt.groupby(['周期', '商品名称', '颜色']).agg({'销售数量':'sum', '总营业额':'sum'}).reset_index()
        summ = summ.merge(df_stock[['商品名称', '颜色', '进价成本']], on=['商品名称', '颜色'], how='left')
        summ['总成本'] = summ['销售数量'] * summ['进价成本']
        summ['具体毛利'] = summ['总营业额'] - summ['总成本']
        summ['毛利率 (%)'] = ((summ['具体毛利'] / summ['总营业额']) * 100).fillna(0)
        
        f_sum = get_f(summ, q)
        c1, c2, c3 = st.columns(3)
        c1.metric("总营业额", f"${f_sum['总营业额'].sum():.2f}")
        c2.metric("具体毛利", f"${f_sum['具体毛利'].sum():.2f}")
        c3.metric("平均毛利率", f"{(f_sum['具体毛利'].sum()/f_sum['总营业额'].sum()*100 if f_sum['总营业额'].sum()>0 else 0):.1f}%")
        st.dataframe(f_sum.style.format({'总营业额':"${:.2f}", '总成本':"${:.2f}", '具体毛利':"${:.2f}", '毛利率 (%)':"{:.1f}%"}), use_container_width=True)
