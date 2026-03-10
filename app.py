import streamlit as st
import pandas as pd
import os
from datetime import datetime, timedelta

# --- 1. 配置与初始化 ---
st.set_page_config(page_title="Taka 零售与财务终极版", layout="wide")
STOCK_FILE = "taka_stock_final_v10.csv" 
SALES_FILE = "taka_sales_final_v10.csv"
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

# --- 2. 侧边栏 ---
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
    st.download_button("📥 备份库存", df_stock.to_csv(index=False).encode('utf-8-sig'), "stock.csv", "text/csv")
    st.download_button("📥 备份流水", df_sales.to_csv(index=False).encode('utf-8-sig'), "sales.csv", "text/csv")

# --- 3. 辅助功能 ---
q = st.text_input("🔍 快速筛选 SKU 或颜色...")
def get_f(df, q):
    if q and not df.empty:
        return df[df['商品名称'].str.contains(q, case=False, na=False) | df['颜色'].str.contains(q, case=False, na=False)]
    return df

# --- 4. 主界面 ---
t1, t2, t3 = st.tabs(["📊 库存看板", "💰 批量记账", "📈 财务分析"])

with t1:
    f_stock = get_f(df_stock, q)
    view_df = f_stock.copy()
    
    # 修复小数点问题：强制转换为整数显示
    int_cols = ['应收到数量', '已售出数量', '总库存', '展示数量', '货柜数量', '储物间数量', '坏货数量']
    for col in int_cols:
        view_df[col] = view_df[col].astype(int)
        
    view_df['单件利润'] = view_df['售卖价格'] - view_df['进价成本']
    view_df['毛利率'] = ((view_df['单件利润'] / view_df['售卖价格']) * 100).fillna(0).map("{:.1f}%".format)
    
    st.dataframe(
        view_df[['商品名称', '颜色', '应收到数量', '已售出数量', '总库存', '展示数量', '货柜数量', '储物间数量', '坏货数量', '售卖价格', '毛利率']]
        .style.apply(lambda r: ['background-color: #ffcccc' if r['总库存'] <= LOW_STOCK_THRESHOLD else '' for _ in r], axis=1),
        use_container_width=True
    )
    
    if not df_stock.empty:
        st.divider()
        st.write("### ⚙️ 单项信息校准")
        df_stock['label'] = df_stock['商品名称'] + " (" + df_stock['颜色'] + ")"
        target = st.selectbox("选择商品", df_stock['label'])
        idx = df_stock[df_stock['label'] == target].index[0]
        with st.form("edit_stock"):
            c1, c2, c3 = st.columns(3)
            e_sold = c3.number_input("已售修正", value=int(df_stock.at[idx, '已售出数量']))
            i1, i2, i3, i4, i5 = st.columns(5)
            e_dis, e_sh, e_st, e_dm = i2.number_input("展示", value=int(df_stock.at[idx, '展示数量'])), i3.number_input("货柜", value=int(df_stock.at[idx, '货柜数量'])), i4.number_input("储物", value=int(df_stock.at[idx, '储物间数量'])), i5.number_input("坏货", value=int(df_stock.at[idx, '坏货数量']))
            if st.form_submit_button("保存"):
                df_stock.at[idx, '展示数量'], df_stock.at[idx, '货柜数量'], df_stock.at[idx, '储物间数量'], df_stock.at[idx, '坏货数量'], df_stock.at[idx, '已售出数量'] = e_dis, e_sh, e_st, e_dm, e_sold
                df_stock.at[idx, '总库存'] = e_dis + e_sh + e_st + e_dm
                df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False); st.rerun()

with t2:
    # (批量记账逻辑保持，已确保数据存为整数)
    st.subheader("销售记账")
    with st.expander("➕ 新增销售", expanded=True):
        f_opts = get_f(df_stock, q)
        if not f_opts.empty:
            df_stock['label'] = df_stock['商品名称'] + " (" + df_stock['颜色'] + ")"
            with st.form("add_sale"):
                s_l = st.selectbox("商品", f_opts['label'])
                c1, c2 = st.columns(2)
                s_q, s_p = c1.number_input("数量", 1), c2.number_input("单价", value=float(df_stock[df_stock['label']==s_l]['售卖价格'].iloc[0]))
                s_d = st.date_input("日期", value=datetime.now())
                if st.form_submit_button("确认"):
                    idx_p = df_stock[df_stock['label'] == s_l].index[0]
                    new_s = pd.DataFrame([[s_d.strftime("%Y-%m-%d"), df_stock.at[idx_p,'商品名称'], df_stock.at[idx_p,'颜色'], s_q, s_p, s_q*s_p]], columns=SALES_COLS)
                    pd.concat([new_s, df_sales], ignore_index=True).to_csv(SALES_FILE, index=False)
                    df_stock.at[idx_p, '货柜数量'] -= s_q
                    df_stock.at[idx_p, '已售出数量'] += s_q
                    df_stock.at[idx_p, '总库存'] = df_stock.iloc[idx_p][['展示数量', '货柜数量', '储物间数量', '坏货数量']].sum()
                    df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False); st.rerun()
    # (批量撤销代码...)

with t3:
    st.subheader("📊 财务透视报表")
    if not df_sales.empty:
        period = st.radio("选择统计维度", ["Daily (每日)", "Weekly Summary (周聚合)", "Monthly"], horizontal=True)
        rpt = df_sales.copy()
        rpt['日期'] = pd.to_datetime(rpt['日期'])
        
        # 优化 Weekly 日期：保留“周起始日”，但在报表中增加具体的日期分布
        if "Daily" in period:
            rpt['统计周期'] = rpt['日期'].dt.strftime('%Y-%m-%d')
        elif "Weekly" in period:
            rpt['统计周期'] = (rpt['日期'] - pd.to_timedelta(rpt['日期'].dt.dayofweek, unit='D')).dt.strftime('Week of %b %d')
        else:
            rpt['统计周期'] = rpt['日期'].dt.strftime('%Y-%m')
        
        # 聚合财务数据
        summ = rpt.groupby(['统计周期', '商品名称', '颜色']).agg({'销售数量':'sum', '总营业额':'sum'}).reset_index()
        summ = summ.merge(df_stock[['商品名称', '颜色', '进价成本']], on=['商品名称', '颜色'], how='left')
        summ['具体毛利'] = summ['总营业额'] - (summ['销售数量'] * summ['进价成本'])
        
        # 排序：按统计周期倒序（最新的在上面）
        summ = summ.sort_values('统计周期', ascending=False)
        f_sm = get_f(summ, q)
        
        # --- 核心改进：顶部大字指标卡 ---
        st.markdown("---")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("总营业额 (Total Sales)", f"${f_sm['总营业额'].sum():.2f}")
        m2.metric("具体毛利 (Total Profit)", f"${f_sm['具体毛利'].sum():.2f}")
        # 这里就是你要的大字：售卖数量
        m3.metric("总售出件数 (Units Sold)", f"{int(f_sm['销售数量'].sum())} 件")
        avg_m = f_sm['具体毛利'].sum()/f_sm['总营业额'].sum()*100 if f_sm['总营业额'].sum()>0 else 0
        m4.metric("平均毛利率 (Avg Margin)", f"{avg_m:.1f}%")
        st.markdown("---")
        
        st.dataframe(f_sm.style.format({
            '总营业额': "${:.2f}", 
            '具体毛利': "${:.2f}", 
            '销售数量': "{:d}",
            '进价成本': "${:.2f}"
        }), use_container_width=True)
