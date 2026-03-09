import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- 1. 配置与文件初始化 ---
st.set_page_config(page_title="Taka 进销存-批量操作版", layout="wide")
# 维持版本号确保字段一致性
STOCK_FILE = "taka_stock_final_v6.csv" 
SALES_FILE = "taka_sales_final_v6.csv"

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
    # ... (保留新增 SKU 功能)
    with st.expander("➕ 新增产品 (Add SKU)", expanded=False):
        with st.form("new_sku_form"):
            n_name = st.text_input("产品名称")
            n_color = st.text_input("颜色")
            c1, c2, c3 = st.columns(3)
            n_cost = c1.number_input("进价 (SGD)", min_value=0.0)
            n_price = c2.number_input("售价 (SGD)", min_value=0.0)
            n_expect = c3.number_input("应收到数量", min_value=0)
            st.write("--- 初始实收库存 ---")
            i1, i2, i3, i4 = st.columns(4)
            n_disp, n_shelf, n_stor, n_dmg = i1.number_input("展示"), i2.number_input("货柜"), i3.number_input("储物"), i4.number_input("坏货")
            if st.form_submit_button("确认录入"):
                if n_name and n_color:
                    n_total = n_disp + n_shelf + n_stor + n_dmg
                    new_row = pd.DataFrame([[n_name, n_color, n_cost, n_price, n_expect, n_disp, n_shelf, n_stor, n_dmg, 0, n_total]], columns=STOCK_COLS)
                    pd.concat([df_stock, new_row], ignore_index=True).to_csv(STOCK_FILE, index=False)
                    st.rerun()

    st.divider()
    st.write("### 💾 数据中心")
    st.download_button("📥 下载库存备份", df_stock.to_csv(index=False).encode('utf-8-sig'), "stock.csv", "text/csv")
    st.download_button("📥 下载销售备份", df_sales.to_csv(index=False).encode('utf-8-sig'), "sales.csv", "text/csv")
    
    with st.expander("📂 上传 CSV 恢复数据"):
        up_stock = st.file_uploader("恢复库存表", type="csv")
        if up_stock and st.button("确认覆盖库存"):
            pd.read_csv(up_stock).to_csv(STOCK_FILE, index=False)
            st.rerun()
        up_sales = st.file_uploader("恢复销售表", type="csv")
        if up_sales and st.button("确认覆盖销售"):
            pd.read_csv(up_sales).to_csv(SALES_FILE, index=False)
            st.rerun()

# --- 3. 全局搜索过滤 ---
st.write("### 🔍 SKU 快速筛选")
search_q = st.text_input("搜索产品名或颜色（会联动多选列表）", placeholder="例如：迷你杯...")

def get_filtered(df, q):
    if q and not df.empty:
        return df[df['商品名称'].str.contains(q, case=False, na=False) | df['颜色'].str.contains(q, case=False, na=False)]
    return df

# --- 4. 主界面布局 ---
st.title("🏙️ Takashimaya 零售管理系统")
t1, t2, t3 = st.tabs(["📊 库存看板", "💰 批量销售管理", "📈 周期利润报表"])

with t1:
    f_stock = get_filtered(df_stock, search_q)
    st.subheader("当前柜台分布")
    view_df = f_stock.copy()
    view_df['单件利润'] = view_df['售卖价格'] - view_df['进价成本']
    view_df['毛利率'] = ((view_df['单件利润'] / view_df['售卖价格']) * 100).fillna(0).map("{:.1f}%".format)
    show_cols = ['商品名称', '颜色', '售卖价格', '毛利率', '应收到数量', '已售出数量', '坏货数量', '展示数量', '货柜数量', '储物间数量', '总库存']
    st.dataframe(view_df[show_cols], use_container_width=True)
    # (保留 Tab 1 底部的信息修正模块...)

with t2:
    st.subheader("销售记账与批量操作")
    
    # 录入部分
    with st.expander("➕ 新增单笔销售记录", expanded=True):
        f_options = get_filtered(df_stock, search_q)
        if not f_options.empty:
            df_stock['label'] = df_stock['商品名称'] + " (" + df_stock['颜色'] + ")"
            with st.form("sales_form"):
                s_label = st.selectbox("售出商品", f_options['label'] if 'label' in f_options.columns else [])
                c_qty, c_pr = st.columns(2)
                s_qty = c_qty.number_input("数量", min_value=1, step=1)
                idx_p = df_stock[df_stock['label'] == s_label].index[0]
                s_price = c_pr.number_input("成交单价", value=float(df_stock.at[idx_p, '售卖价格']))
                sel_date = st.date_input("日期", value=datetime.now())
                if st.form_submit_button("确认记账"):
                    total = s_qty * s_price
                    new_sale = pd.DataFrame([[sel_date.strftime("%Y-%m-%d"), df_stock.at[idx_p, '商品名称'], df_stock.at[idx_p, '颜色'], s_qty, s_price, total]], columns=SALES_COLS)
                    pd.concat([new_sale, df_sales], ignore_index=True).to_csv(SALES_FILE, index=False)
                    # 联动库存
                    df_stock.at[idx_p, '货柜数量'] -= s_qty
                    df_stock.at[idx_p, '已售出数量'] += s_qty
                    df_stock.at[idx_p, '总库存'] = df_stock.iloc[idx_p][['展示数量', '货柜数量', '储物间数量', '坏货数量']].sum()
                    df_stock.drop(columns=['label']).to_csv(STOCK_FILE, index=False)
                    st.rerun()

    st.divider()
    
    # --- 核心更新：带复选框的批量删除列表 ---
    st.write("### 🧾 销售流水清单 (勾选以进行批量撤销)")
    
    f_sales = get_filtered(df_sales, search_q)
    
    if f_sales.empty:
        st.write("暂无匹配记录")
    else:
        # 为 DataFrame 添加一个“选择”列
        f_sales_with_select = f_sales.copy()
        f_sales_with_select.insert(0, "选择", False)
        
        # 使用 data_editor 显示表格，第一列是复选框
        edited_df = st.data_editor(
            f_sales_with_select,
            column_config={
                "选择": st.column_config.CheckboxColumn(
                    "选择",
                    help="勾选以批量撤销记录",
                    default=False,
                )
            },
            disabled=[col for col in f_sales.columns], # 除了选择列，其他都不允许编辑
            use_container_width=True,
            hide_index=True,
            key="sales_editor"
        )
        
        # 找出选中的行
        selected_rows = edited_df[edited_df["选择"] == True]
        
        if not selected_rows.empty:
            st.warning(f"⚠️ 您已选中 {len(selected_rows)} 条记录。")
            if st.button("🔴 批量撤销并回退库存", type="primary"):
                # 循环处理选中的每一行
                for idx, row in selected_rows.iterrows():
                    # 1. 寻找库存表中的对应 SKU
                    match = df_stock[(df_stock['商品名称'] == row['商品名称']) & (df_stock['颜色'] == row['颜色'])].index
                    if not match.empty:
                        s_idx = match[0]
                        # 2. 退还库存
                        df_stock.at[s_idx, '货柜数量'] += row['销售数量']
                        df_stock.at[s_idx, '已售出数量'] -= row['销售数量']
                        df_stock.at[s_idx, '总库存'] = df_stock.iloc[s_idx][['展示数量', '货柜数量', '储物间数量', '坏货数量']].sum()
                
                # 3. 从原始 df_sales 中删除这些行（通过原始索引或特征匹配）
                # 这里我们使用日期、名称、颜色、数量的多重匹配来确保准确性
                for idx, row in selected_rows.iterrows():
                    df_sales = df_sales[~(
                        (df_sales['日期'] == row['日期']) & 
                        (df_sales['商品名称'] == row['商品名称']) & 
                        (df_sales['颜色'] == row['颜色']) & 
                        (df_sales['销售数量'] == row['销售数量'])
                    )]
                
                # 4. 保存文件并刷新
                df_stock.to_csv(STOCK_FILE, index=False)
                df_sales.to_csv(SALES_FILE, index=False)
                st.success("批量撤销成功！库存已回退。")
                st.rerun()

with t3:
    # ... (保留之前的 Daily/Weekly/Monthly 利润报表逻辑)
    st.subheader("📊 财务报表")
    if not df_sales.empty:
        # 统计逻辑保持不变...
        st.write("报表会自动根据最新的销售流水实时生成。")
