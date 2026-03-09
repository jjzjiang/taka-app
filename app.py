import streamlit as st
import pandas as pd
import os

# --- 1. 配置与文件初始化 ---
st.set_page_config(page_title="高岛屋库存管理系统", layout="wide")
DATA_FILE = "taka_stock_pro.csv"

# 初始化更详细的表格结构
if not os.path.exists(DATA_FILE):
    df = pd.DataFrame(columns=[
        '商品名称', '颜色', '展示数量', '货柜数量', '储物间数量', '总库存'
    ])
    # 预设几个你的主打产品作为例子
    init_rows = [
        ['TAIC钛杯-经典款', '钛色', 2, 5, 20, 27],
        ['BlackInTi-商务款', '哑光黑', 1, 3, 15, 19]
    ]
    df = pd.DataFrame(init_rows, columns=df.columns)
    df.to_csv(DATA_FILE, index=False)

df = pd.read_csv(DATA_FILE)

# --- 2. 侧边栏：新增 SKU 模块 ---
st.sidebar.header("➕ 新增产品 (Add SKU)")
with st.sidebar.expander("点击展开录入表单"):
    with st.form("add_sku_form"):
        new_name = st.text_input("产品名称 (如：TAIC 咖啡杯)")
        new_color = st.text_input("颜色 (如：极光色)")
        new_display = st.number_input("初始展示数量", min_value=0, value=0)
        new_shelf = st.number_input("初始货柜数量", min_value=0, value=0)
        new_storage = st.number_input("初始储物间数量", min_value=0, value=0)
        
        if st.form_submit_button("确认添加"):
            if new_name:
                total = new_display + new_shelf + new_storage
                new_data = [new_name, new_color, new_display, new_shelf, new_storage, total]
                new_df = pd.DataFrame([new_data], columns=df.columns)
                df = pd.concat([df, new_df], ignore_index=True)
                df.to_csv(DATA_FILE, index=False)
                st.success(f"已成功添加：{new_name} ({new_color})")
                st.rerun()
            else:
                st.error("请填入产品名称")

st.sidebar.divider()

# --- 3. 侧边栏：库存变动更新 ---
st.sidebar.header("🔄 库存数据更新")
with st.sidebar.form("update_form"):
    # 为了方便区分颜色，我们将名称和颜色合并显示在下拉菜单
    df['display_label'] = df['商品名称'] + " - " + df['颜色']
    target_label = st.selectbox("选择要修改的产品", df['display_label'])
    
    col_to_edit = st.selectbox("修改位置", ["展示数量", "货柜数量", "储物间数量"])
    new_val = st.number_input("更新后的准确数量", min_value=0, step=1)
    
    if st.form_submit_button("提交修改"):
        idx = df[df['display_label'] == target_label].index[0]
        df.at[idx, col_to_edit] = new_val
        # 重新计算该行的总库存
        df.at[idx, '总库存'] = df.at[idx, '展示数量'] + df.at[idx, '货柜数量'] + df.at[idx, '储物间数量']
        
        # 删除辅助列并保存
        save_df = df.drop(columns=['display_label'])
        save_df.to_csv(DATA_FILE, index=False)
        st.success("数据已同步！")
        st.rerun()

# --- 4. 主界面：数据显示 ---
st.title("🏙️ Takashimaya 每日库存实录")

# 统计总览卡片
total_all = df['总库存'].sum()
st.metric("柜台总货值（件数）", f"{int(total_all)} Pcs")

# 显示表格（去掉辅助列）
display_df = df.drop(columns=['display_label']) if 'display_label' in df.columns else df
st.subheader("各位置详细分布表")
st.dataframe(display_df, use_container_width=True)

# 导出功能
st.download_button(
    "📥 导出今日盘点表", 
    display_df.to_csv(index=False).encode('utf-8'), 
    "Taka_Daily_Inventory.csv"
)
