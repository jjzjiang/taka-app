import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- 1. 配置与文件初始化 ---
st.set_page_config(page_title="Taka 进销存-数据备份版", layout="wide")
STOCK_FILE = "taka_stock_final.csv" 
SALES_FILE = "taka_sales_final.csv"

STOCK_COLS = ['商品名称', '颜色', '进价成本', '售卖价格', '展示数量', '货柜数量', '储物间数量', '总库存']
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

# --- 2. 数据存取中心 (新功能) ---
with st.sidebar:
    st.header("💾 数据备份与恢复")
    st.info("网页版数据会定期重置，请务必每天下班前点击‘下载’备份。")
    
    # 下载备份
    st.write("### 1. 下载备份")
    st.download_button(
        label="📥 下载当前库存表",
        data=df_stock.to_csv(index=False).encode('utf-8-sig'),
        file_name=f"stock_backup_{datetime.now().strftime('%m%d')}.csv",
        mime="text/csv"
    )
    st.download_button(
        label="📥 下载当前销售流水",
        data=df_sales.to_csv(index=False).encode('utf-8-sig'),
        file_name=f"sales_backup_{datetime.now().strftime('%m%d')}.csv",
        mime="text/csv"
    )
    
    st.divider()
    
    # 上传恢复
    st.write("### 2. 上传恢复")
    up_stock = st.file_uploader("上传库存备份文件", type="csv")
    if up_stock:
        if st.button("确认覆盖当前库存数据"):
            new_stock = pd.read_csv(up_stock)
            new_stock.to_csv(STOCK_FILE, index=False)
            st.success("库存数据已恢复！")
            st.rerun()
            
    up_sales = st.file_uploader("上传销售备份文件", type="csv")
    if up_sales:
        if st.button("确认合并/覆盖销售数据"):
            new_sales = pd.read_csv(up_sales)
            new_sales.to_csv(SALES_FILE, index=False)
            st.success("销售流水已恢复！")
            st.rerun()

# --- 3. 全局搜索过滤 ---
st.write("### 🔍 SKU 快速筛选")
search_q = st.text_input("输入产品名或颜色（如下拉框找不到，请先在这里清空或输入正确关键词）", placeholder="例如：钛杯...")

def get_filtered(df, q):
    if q:
        mask = df['商品名称'].str.contains(q, case=False, na=False) | \
               df['颜色'].str.contains(q, case=False, na=False)
        return df[mask]
    return df

# --- 4. 主界面标签页 ---
t1, t2, t3 = st.tabs(["📊 库存看板", "💰 销售记账", "📈 利润分析"])

with t1:
    f_stock = get_filtered(df_stock, search_q)
    st.subheader("当前柜台分布")
    view_df = f_stock.copy()
    view_df['单件利润'] = view_df['售卖价格'] - view_df['进价成本']
    view_df['毛利率'] = ((view_df['单件利润'] / view_df['售卖价格']) * 100).fillna(0).map("{:.1f}%".format)
    st.dataframe(view_df[['商品名称', '颜色', '售卖价格', '毛利率', '展示数量', '货柜数量', '储物间数量', '总库存']], use_container_width=True)
    
    st.divider()
    st.write("### ⚙️ SKU 信息修正与删除")
    df_stock['label'] = df_stock['商品名称'] + " (" + df_stock['颜色'] + ")"
    if not df_stock.empty:
        col_edit, col_del = st.columns([2, 1])
        with col_edit:
            with st.expander("✏️ 修改 SKU 信息"):
                target = st.selectbox("选择商品", df_stock['label'], key="edit_s")
                idx = df_stock[df_stock['label'] == target].index[0]
                with st.form("edit_form"):
                    e_name = st.text_input("名称", value=df_stock.at[idx, '商品名称'])
                    e_color = st.text_input("颜色", value=df_stock.at[idx, '颜色'])
                    c1, c2 = st.columns(2)
                    e_cost = c1.number_input("进价", value=float(df_stock.at[idx, '进价成本']))
                    e_price = c2.number_input("售价", value=float(df_stock.at[idx, '售卖价格']))
                    if st.form_submit_button("保存"):
                        df_stock.at[idx, '商品名称'], df_stock.at[idx, '颜色'] = e_name, e_color
                        df_stock.at[idx, '进价成本'], df_stock.at[idx, '售卖价格'] = e_cost, e_price
                        df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                        st.rerun()
        with col_del:
            with st.expander("🗑️ 彻底删除 SKU"):
                del_t = st.selectbox("选择删除项", df_stock['label'], key="del_s")
                if st.button("确认删除", type="primary"):
                    df_stock = df_stock[df_stock['label'] != del_t]
                    df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                    st.rerun()

with t2:
    st.subheader("销售记账")
    col_l, col_r = st.columns(2)
    with col_l:
        st.write("### 1. 新增记录")
        f_options = get_filtered(df_stock, search_q)
        if f_options.empty: st.warning("请调整上方搜索词")
        else:
            with st.form("sales_form"):
                s_label = st.selectbox("售出商品", f_options['label'])
                c1, c2 = st.columns(2)
                s_qty = c1.number_input("数量", min_value=1, step=1)
                idx_p = df_stock[df_stock['label'] == s_label].index[0]
                s_price = c2.number_input("单价 (SGD)", value=float(df_stock.at[idx_p, '售卖价格']))
                sel_date = st.date_input("销售日期", value=datetime.now())
                if st.form_submit_button("确认提交"):
                    total = s_qty * s_price
                    new_sale = pd.DataFrame([[sel_date.strftime("%Y-%m-%d"), df_stock.at[idx_p, '商品名称'], df_stock.at[idx_p, '颜色'], s_qty, s_price, total]], columns=SALES_COLS)
                    df_sales = pd.concat([new_sale, df_sales], ignore_index=True)
                    df_sales.to_csv(SALES_FILE, index=False)
                    # 扣库存逻辑
                    df_stock.at[idx_p, '货柜数量'] -= s_qty
                    df_stock.at[idx_p, '总库存'] = df_stock.iloc[idx_p][['展示数量', '货柜数量', '储物间数量']].sum()
                    df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                    st.rerun()
    with col_r:
        st.write("### 2. 撤销记录")
        if not df_sales.empty:
            df_sales['cancel_l'] = df_sales['日期'] + " | " + df_sales['商品名称']
            del_idx = st.selectbox("选择撤销项", range(len(df_sales)), format_func=lambda x: df_sales.iloc[x]['cancel_l'])
            if st.button("确认撤销"):
                sale_to_del = df_sales.iloc[del_idx]
                match = df_stock[(df_stock['商品名称'] == sale_to_del['商品名称']) & (df_stock['颜色'] == sale_to_del['颜色'])].index
                if not match.empty:
                    df_stock.at[match[0], '货柜数量'] += sale_to_del['销售数量']
                    df_stock.at[match[0], '总库存'] = df_stock.iloc[match[0]][['展示数量', '货柜数量', '储物间数量']].sum()
                    df_stock.to_csv(STOCK_FILE, index=False)
                df_sales.drop(df_sales.index[del_idx]).drop(columns=['cancel_l']).to_csv(SALES_FILE, index=False)
                st.rerun()
    st.dataframe(get_filtered(df_sales, search_q), use_container_width=True)

with t3:
    st.subheader("💰 盈利能力看板")
    analysis = get_filtered(df_stock, search_q).copy()
    if not analysis.empty:
        analysis['单件利润'] = analysis['售卖价格'] - analysis['进价成本']
        analysis['毛利率 (%)'] = ((analysis['单件利润'] / analysis['售卖价格']) * 100).fillna(0)
        
        # 简单汇总历史总利润
        if not df_sales.empty:
            summary = df_sales.groupby(['商品名称', '颜色'])['销售数量'].sum().reset_index()
            analysis = analysis.merge(summary, on=['商品名称', '颜色'], how='left').fillna(0)
            analysis['累计毛利'] = analysis['销售数量'] * analysis['单件利润']
        else:
            analysis['累计毛利'] = 0

        m1, m2 = st.columns(2)
        m1.metric("筛选项总销售额", f"${(analysis['售卖价格']*analysis['销售数量']).sum():.2f}")
        m2.metric("筛选项累计毛利", f"${analysis['累计毛利'].sum():.2f}")
        
        st.dataframe(analysis[['商品名称', '颜色', '进价成本', '售卖价格', '单件利润', '毛利率 (%)', '累计毛利']], use_container_width=True)
