import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
import gspread 
from gspread.exceptions import WorksheetNotFound
import json

# --- 1. 配置与云端数据库初始化 ---
st.set_page_config(page_title="Taka 零售终极管理系统", layout="wide")

try:
    key_dict = json.loads(st.secrets["google_key"])
    gc = gspread.service_account_from_dict(key_dict)
    sh = gc.open_by_url(st.secrets["sheet_url"]) 
except Exception as e:
    st.error(f"🔴 连接云端数据库失败！详细错误: {e}")
    st.stop()

STOCK_SHEET = "Stock"
SALES_SHEET = "Sales"
EMP_SHEET = "Employee"
ATT_SHEET = "Attendance"
B2B_SHEET = "B2B_Orders" 
FEEDBACK_SHEET = "Feedback"
RESTOCK_SHEET = "Restock_Log"

STOCK_COLS = ['商品名称', '颜色', '进价成本', '售卖价格', '应收到数量', '展示数量', '货柜数量', '储物间数量', '坏货数量', '已售出数量', '总库存']
# 🚀 核心升级：新增订单号字段
SALES_COLS = ['订单号', '日期', '商品名称', '颜色', '销售数量', '成交单价', '总营业额']
EMP_COLS = ['员工姓名', '职位', '时薪', '联系方式', '入职日期']
ATT_COLS = ['员工姓名', '日期', '开始时间', '结束时间', '工作时长', '核算薪资']
B2B_COLS = ['创建日期', '客户名称', '商品名称', '颜色', '采购数量', 'B2B单价', '总计应收', '货物成本', '物流成本', '关税', '已收定金', '待收尾款', '约定交期', '订单状态', '备注']
FEEDBACK_COLS = ['反馈日期', '商品名称', '客户画像', '反馈类型', '详细原话', '跟进状态']
RESTOCK_COLS = ['记录日期', '操作类型', '商品名称', '颜色', '变动数量', '库位详情', '单件成本', '备注']

if "sheet_versions" not in st.session_state:
    st.session_state.sheet_versions = {
        STOCK_SHEET: 0, SALES_SHEET: 0, EMP_SHEET: 0,
        ATT_SHEET: 0, B2B_SHEET: 0, FEEDBACK_SHEET: 0, RESTOCK_SHEET: 0
    }

# 🚀 购物车状态初始化
if "pos_cart" not in st.session_state:
    st.session_state.pos_cart = []

@st.cache_data(ttl=300, show_spinner=False)
def load_raw_data(sheet_name, version):
    try:
        worksheet = sh.worksheet(sheet_name)
        records = worksheet.get_all_records()
        if not records:
            return pd.DataFrame()
        return pd.DataFrame(records)
    except Exception as e:
        return pd.DataFrame()

def load_data(sheet_name, columns):
    ver = st.session_state.sheet_versions.get(sheet_name, 0)
    df = load_raw_data(sheet_name, ver)
    if df.empty:
        df = pd.DataFrame(columns=columns)
    for col in columns:
        if col not in df.columns: df[col] = 0
    return df[columns]

def save_data(df, sheet_name):
    try:
        worksheet = sh.worksheet(sheet_name)
    except WorksheetNotFound:
        worksheet = sh.add_worksheet(title=sheet_name, rows="1000", cols="20")
        
    worksheet.clear() 
    df_safe = df.fillna("").astype(str)
    data_to_upload = [df_safe.columns.values.tolist()] + df_safe.values.tolist()
    worksheet.update(values=data_to_upload, range_name='A1')
    
    st.session_state.sheet_versions[sheet_name] = st.session_state.sheet_versions.get(sheet_name, 0) + 1

def clean_date_col(df, col_name):
    if not df.empty and col_name in df.columns:
        formatted = pd.to_datetime(df[col_name], errors='coerce').dt.strftime('%Y/%m/%d')
        df[col_name] = formatted.fillna(df[col_name])
    return df

@st.cache_data(show_spinner=False)
def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8-sig')

df_stock = load_data(STOCK_SHEET, STOCK_COLS)
df_sales = clean_date_col(load_data(SALES_SHEET, SALES_COLS), '日期') 
# 🚀 历史数据兼容：给旧账本加上默认历史单号，防止报错
if not df_sales.empty:
    df_sales['订单号'] = df_sales['订单号'].astype(str).replace('0', '历史单').replace('', '历史单').replace('nan', '历史单')

df_employee = clean_date_col(load_data(EMP_SHEET, EMP_COLS), '入职日期') 
df_attendance = clean_date_col(load_data(ATT_SHEET, ATT_COLS), '日期') 
df_b2b = clean_date_col(clean_date_col(load_data(B2B_SHEET, B2B_COLS), '创建日期'), '约定交期')
df_feedback = clean_date_col(load_data(FEEDBACK_SHEET, FEEDBACK_COLS), '反馈日期')
df_restock = clean_date_col(load_data(RESTOCK_SHEET, RESTOCK_COLS), '记录日期')

if "stock_reset_key" not in st.session_state: st.session_state.stock_reset_key = 0
if "sales_reset_key" not in st.session_state: st.session_state.sales_reset_key = 0
if "emp_reset_key" not in st.session_state: st.session_state.emp_reset_key = 0
if "att_reset_key" not in st.session_state: st.session_state.att_reset_key = 0 
if "b2b_reset_key" not in st.session_state: st.session_state.b2b_reset_key = 0 
if "fb_reset_key" not in st.session_state: st.session_state.fb_reset_key = 0 

def clear_stock(): st.session_state.stock_reset_key += 1
def clear_sales(): st.session_state.sales_reset_key += 1
def clear_emp(): st.session_state.emp_reset_key += 1
def clear_att(): st.session_state.att_reset_key += 1
def clear_b2b(): st.session_state.b2b_reset_key += 1
def clear_fb(): st.session_state.fb_reset_key += 1

# --- 2. 侧边栏：核心管理 ---
with st.sidebar:
    st.header("🛠️ 核心管理")
    with st.expander("➕ 新增产品建档 (Add SKU)"):
        with st.form("new_sku"):
            n_name = st.text_input("产品名称")
            n_color = st.text_input("颜色")
            c1, c2, c3 = st.columns(3)
            n_cost, n_price, n_expect = c1.number_input("进价", format="%.2f"), c2.number_input("售价", format="%.2f"), c3.number_input("应收")
            i1, i2, i3, i4 = st.columns(4)
            n_disp, n_shelf, n_stor, n_dmg = i1.number_input("展示"), i2.number_input("货柜"), i3.number_input("储物"), i4.number_input("坏货")
            if st.form_submit_button("确认建档"):
                if n_name and n_color:
                    total = n_disp + n_shelf + n_stor 
                    new_r = pd.DataFrame([[n_name, n_color, n_cost, n_price, n_expect, n_disp, n_shelf, n_stor, n_dmg, 0, total]], columns=STOCK_COLS)
                    df_stock = pd.concat([df_stock, new_r], ignore_index=True)
                    
                    if total > 0 or n_dmg > 0:
                        log_date = datetime.now().strftime("%Y/%m/%d")
                        init_log = pd.DataFrame([[log_date, "初始建档", n_name, n_color, total+n_dmg, "多库位", n_cost, "侧边栏初始建档"]], columns=RESTOCK_COLS)
                        df_restock = pd.concat([init_log, df_restock], ignore_index=True)
                        save_data(df_restock, RESTOCK_SHEET)
                        
                    save_data(df_stock, STOCK_SHEET) 
                    st.success("✅ 云端建档成功！")
                    st.rerun()

    st.divider()
    st.write("### ☁️ 云端数据中心")
    st.info("💡 数据实时同步至 Google Sheets。")

# --- 3. 辅助功能 ---
q = st.text_input("🔍 快速筛选 (全局搜索)...", placeholder="搜商品/姓名/客户/反馈内容...")

def get_f(df, q):
    if q and not df.empty:
        mask = pd.Series(False, index=df.index)
        for col in df.columns:
            mask = mask | df[col].fillna('').astype(str).str.contains(q, case=False, regex=False)
        return df[mask]
    return df

# --- 4. 主界面布局 ---
st.title("🏙️ Takashimaya 零售管理系统 (云端同步版)")
t1, t2, t3, t4, t5, t6, t7, t8 = st.tabs(["📊 库存", "💰 销售", "📈 毛利", "👥 考勤", "💎 净利润", "🤝 B2B订单", "🗣️ 客户反馈", "🧠 战略(BI)"])

with t1:
    st.subheader("📦 专业 ERP 库存与货位管家")
    st.info("💡 双边账引擎已启动：禁止在此直接篡改库存数，系统将严格依据下方的【入库】、【调拨】、【盘点】通道进行自动化记账。")
    
    f_opts_stk = df_stock.copy()
    stock_list_labels = []
    if not f_opts_stk.empty:
        f_opts_stk['label'] = f_opts_stk['商品名称'].astype(str) + " (" + f_opts_stk['颜色'].astype(str) + ")"
        stock_list_labels = f_opts_stk['label'].tolist()
        
    t1_a, t1_b, t1_c = st.tabs(["📥 1. 补货入库 (Restock)", "🔄 2. 货位调拨 (Transfer)", "⚖️ 3. 盘点平账 (Adjust)"])
    
    with t1_a:
        with st.form("form_restock"):
            c1, c2, c3 = st.columns(3)
            r_sku = c1.selectbox("选择到货商品", stock_list_labels) if stock_list_labels else c1.selectbox("选择到货商品", ["请先在侧边栏新增商品"])
            r_date = c2.date_input("入库日期", value=datetime.now())
            r_loc = c3.selectbox("卸货存放至", ["储物间数量", "货柜数量", "展示数量"])
            
            c4, c5, c6 = st.columns(3)
            r_qty = c4.number_input("入库数量", min_value=1, step=1, value=50)
            r_cost = c5.number_input("此批单件进价 ($) - 留空不改", value=0.0, format="%.2f", help="若填写大于0的金额，将自动更新该商品的主数据成本！")
            r_note = c6.text_input("备注单号或说明", placeholder="如：国内空运第3批...")
            
            if st.form_submit_button("✅ 确认入库", type="primary", use_container_width=True):
                if stock_list_labels:
                    sel_name = r_sku.rsplit(" (", 1)[0]
                    sel_color = r_sku.rsplit(" (", 1)[1].replace(")", "")
                    idx = df_stock[(df_stock['商品名称'] == sel_name) & (df_stock['颜色'] == sel_color)].index[0]
                    
                    df_stock.at[idx, r_loc] = int(pd.to_numeric(df_stock.at[idx, r_loc], errors='coerce') or 0) + r_qty
                    df_stock.at[idx, '总库存'] = sum([int(pd.to_numeric(df_stock.at[idx, col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                    if r_cost > 0: df_stock.at[idx, '进价成本'] = r_cost 
                        
                    new_log = pd.DataFrame([[
                        r_date.strftime("%Y/%m/%d"), "入库", sel_name, sel_color, r_qty, 
                        f"存入: {r_loc.replace('数量','')}", r_cost, r_note
                    ]], columns=RESTOCK_COLS)
                    
                    df_restock = pd.concat([new_log, df_restock], ignore_index=True)
                    save_data(df_stock, STOCK_SHEET); save_data(df_restock, RESTOCK_SHEET)
                    st.success(f"🎉 补货成功！已入库 {r_qty} 件至【{r_loc.replace('数量','')}】。")
                    st.rerun()

    with t1_b:
        with st.form("form_transfer"):
            c1, c2, c3, c4 = st.columns(4)
            t_sku = c1.selectbox("选择调拨商品", stock_list_labels, key="t_sku") if stock_list_labels else c1.selectbox("选择", ["空"])
            t_src = c2.selectbox("从何处移出 (源)", ["储物间数量", "货柜数量", "展示数量"])
            t_dst = c3.selectbox("移到何处去 (目标)", ["货柜数量", "展示数量", "储物间数量"])
            t_qty = c4.number_input("移动数量", min_value=1, step=1, value=10)
            
            if st.form_submit_button("🔄 确认移库", type="primary", use_container_width=True):
                if stock_list_labels and t_src != t_dst:
                    sel_name = t_sku.rsplit(" (", 1)[0]
                    sel_color = t_sku.rsplit(" (", 1)[1].replace(")", "")
                    idx = df_stock[(df_stock['商品名称'] == sel_name) & (df_stock['颜色'] == sel_color)].index[0]
                    
                    curr_src_qty = int(pd.to_numeric(df_stock.at[idx, t_src], errors='coerce') or 0)
                    if curr_src_qty < t_qty:
                        st.error(f"⚠️ {t_src.replace('数量','')} 库存不足！仅剩 {curr_src_qty} 件。")
                    else:
                        df_stock.at[idx, t_src] = curr_src_qty - t_qty
                        df_stock.at[idx, t_dst] = int(pd.to_numeric(df_stock.at[idx, t_dst], errors='coerce') or 0) + t_qty
                        
                        new_log = pd.DataFrame([[
                            datetime.now().strftime("%Y/%m/%d"), "调拨", sel_name, sel_color, t_qty, 
                            f"{t_src.replace('数量','')} -> {t_dst.replace('数量','')}", 0, "内部货架整理"
                        ]], columns=RESTOCK_COLS)
                        
                        df_restock = pd.concat([new_log, df_restock], ignore_index=True)
                        save_data(df_stock, STOCK_SHEET); save_data(df_restock, RESTOCK_SHEET)
                        st.success("✅ 移库成功！总库存数量不变。")
                        st.rerun()

    with t1_c:
        with st.form("form_adjust"):
            c1, c2, c3, c4 = st.columns(4)
            a_sku = c1.selectbox("选择需平账商品", stock_list_labels, key="a_sku") if stock_list_labels else c1.selectbox("选择", ["空"])
            a_loc = c2.selectbox("发生差异的库位", ["货柜数量", "展示数量", "储物间数量", "坏货数量"])
            a_diff = c3.number_input("盘点差异 (+为盘盈, -为盘亏丢失)", value=-1, step=1, help="例如发现被偷了1件，填 -1")
            a_note = c4.text_input("平账原因 (必填)", placeholder="例如：盘点发现丢失...")
            
            if st.form_submit_button("⚖️ 确认记账", type="primary", use_container_width=True):
                if stock_list_labels and a_note.strip() != "" and a_diff != 0:
                    sel_name = a_sku.rsplit(" (", 1)[0]
                    sel_color = a_sku.rsplit(" (", 1)[1].replace(")", "")
                    idx = df_stock[(df_stock['商品名称'] == sel_name) & (df_stock['颜色'] == sel_color)].index[0]
                    
                    df_stock.at[idx, a_loc] = int(pd.to_numeric(df_stock.at[idx, a_loc], errors='coerce') or 0) + a_diff
                    if a_loc != '坏货数量':
                        df_stock.at[idx, '总库存'] = sum([int(pd.to_numeric(df_stock.at[idx, col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                    
                    adj_type = "盘盈" if a_diff > 0 else "盘亏"
                    new_log = pd.DataFrame([[
                        datetime.now().strftime("%Y/%m/%d"), adj_type, sel_name, sel_color, a_diff, 
                        f"库位: {a_loc.replace('数量','')}", 0, a_note
                    ]], columns=RESTOCK_COLS)
                    
                    df_restock = pd.concat([new_log, df_restock], ignore_index=True)
                    save_data(df_stock, STOCK_SHEET); save_data(df_restock, RESTOCK_SHEET)
                    st.success(f"✅ 盘点账目已抹平！记录类型：{adj_type}。")
                    st.rerun()

    st.divider()
    st.subheader("📊 实物库存全景快照 (Snapshot)")
    f_stock = get_f(df_stock, q)
    if not f_stock.empty:
        v_df = f_stock.copy()
        
        int_cols = ['应收到数量', '已售出数量', '总库存', '展示数量', '货柜数量', '储物间数量', '坏货数量']
        for col in int_cols: 
            v_df[col] = pd.to_numeric(v_df[col], errors='coerce').fillna(0).astype(int)
            
        v_df['进价成本'] = pd.to_numeric(v_df['进价成本'], errors='coerce').fillna(0.0)
        v_df['售卖价格'] = pd.to_numeric(v_df['售卖价格'], errors='coerce').fillna(0.0)
        
        def calc_margin(row):
            price = row['售卖价格']
            cost = row['进价成本']
            if price > 0:
                return f"{((price - cost) / price * 100):.1f}%"
            return "0.0%"
            
        v_df['单品毛利率'] = v_df.apply(calc_margin, axis=1)
        v_df.insert(0, "选择", False)
        
        display_cols = ['选择', '商品名称', '颜色', '应收到数量', '已售出数量', '总库存', '展示数量', '货柜数量', '储物间数量', '坏货数量', '售卖价格', '进价成本', '单品毛利率']
        display_df = v_df[display_cols]

        def highlight_low_stock(row):
            try:
                stock_val = int(row['总库存'])
                if stock_val <= 2:
                    return ['background-color: #ffe6e6; color: #cc0000; font-weight: bold;'] * len(row)
            except:
                pass
            return [''] * len(row)

        styled_df = display_df.style.format({'进价成本': '${:.2f}', '售卖价格': '${:.2f}'}).apply(highlight_low_stock, axis=1)
        
        disabled_cols = [c for c in display_cols if c != "选择"]
        editor_key = f"stock_editor_{st.session_state.stock_reset_key}"
        
        edited_stock = st.data_editor(
            styled_df,
            column_config={"选择": st.column_config.CheckboxColumn("选择", default=False)},
            disabled=disabled_cols,
            use_container_width=True, hide_index=True, 
            key=editor_key 
        )
        
        selected_stock = edited_stock[edited_stock["选择"] == True]
        
        if len(selected_stock) == 1:
            st.markdown("### ⚙️ SKU 档案修改与时间溯源机")
            st.info("💡 放心改！如果你修改了【名称】或【颜色】，系统会自动潜入数据库，把你所有历史流水账里的名字一并改掉，绝不留死账。")
            
            orig_name = str(selected_stock.iloc[0]['商品名称'])
            orig_color = str(selected_stock.iloc[0]['颜色'])
            
            raw_cost = str(selected_stock.iloc[0]['进价成本']).replace('$', '').replace(',', '')
            raw_price = str(selected_stock.iloc[0]['售卖价格']).replace('$', '').replace(',', '')
            
            orig_cost = float(raw_cost) if raw_cost else 0.0
            orig_price = float(raw_price) if raw_price else 0.0
            
            sku_logs = df_restock[(df_restock['商品名称'] == orig_name) & (df_restock['颜色'] == orig_color)]
            has_history = False
            if not sku_logs.empty:
                try:
                    first_date_str = sku_logs['记录日期'].min()
                    first_date = pd.to_datetime(first_date_str).date()
                    has_history = True
                except:
                    first_date = datetime.now().date()
            else:
                first_date = datetime.now().date()

            with st.form("edit_base_info"):
                ec1, ec2, ec3 = st.columns([1.5, 1.5, 2])
                e_name = ec1.text_input("商品名称", value=orig_name)
                e_color = ec2.text_input("颜色/规格", value=orig_color)
                e_date = ec3.date_input("📅 首次入库时间 (BI 动销率基准点)", value=first_date, help="如果你发现Tab8里的动销率算的不对，直接在这里把日期往前或往后调！")
                
                ec4, ec5, _ = st.columns([1.5, 1.5, 2])
                e_cost = ec4.number_input("单件进价成本 ($)", value=orig_cost, format="%.2f")
                e_price = ec5.number_input("终端售卖价格 ($)", value=orig_price, format="%.2f")
                
                if st.form_submit_button("💾 保存档案与时间修改", type="primary"):
                    idx = df_stock[(df_stock['商品名称'] == orig_name) & (df_stock['颜色'] == orig_color)].index[0]
                    df_stock.at[idx, '商品名称'] = e_name
                    df_stock.at[idx, '颜色'] = e_color
                    df_stock.at[idx, '进价成本'] = e_cost
                    df_stock.at[idx, '售卖价格'] = e_price
                    
                    if e_name != orig_name or e_color != orig_color:
                        if not df_sales.empty:
                            df_sales.loc[(df_sales['商品名称'] == orig_name) & (df_sales['颜色'] == orig_color), ['商品名称', '颜色']] = [e_name, e_color]
                            save_data(df_sales, SALES_SHEET)
                        if not df_restock.empty:
                            df_restock.loc[(df_restock['商品名称'] == orig_name) & (df_restock['颜色'] == orig_color), ['商品名称', '颜色']] = [e_name, e_color]
                        if not df_b2b.empty:
                            df_b2b.loc[(df_b2b['商品名称'] == orig_name) & (df_b2b['颜色'] == orig_color), ['商品名称', '颜色']] = [e_name, e_color]
                            save_data(df_b2b, B2B_SHEET)

                    date_str = e_date.strftime("%Y/%m/%d")
                    if has_history:
                        min_idx = sku_logs['记录日期'].idxmin()
                        df_restock.at[min_idx, '记录日期'] = date_str
                    else:
                        new_log = pd.DataFrame([[date_str, "初始建档", e_name, e_color, 0, "时间追溯", e_cost, "系统溯源建档"]], columns=RESTOCK_COLS)
                        df_restock = pd.concat([new_log, df_restock], ignore_index=True)
                    
                    save_data(df_stock, STOCK_SHEET)
                    save_data(df_restock, RESTOCK_SHEET)
                    
                    st.session_state.stock_reset_key += 1
                    st.success(f"✅ 【{e_name}】的档案和溯源时间已全局更新！Tab 8 的数据已重新校准。")
                    st.rerun()

        if not selected_stock.empty:
            col_btn1, col_btn2, _ = st.columns([1.5, 1.5, 4])
            with col_btn1:
                if st.button("🗑️ 危险：彻底删档选中", type="primary", key="del_stock"):
                    for _, row in selected_stock.iterrows():
                        df_stock = df_stock[~((df_stock['商品名称'] == row['商品名称']) & (df_stock['颜色'] == row['颜色']))]
                    save_data(df_stock, STOCK_SHEET) 
                    st.session_state.stock_reset_key += 1 
                    st.rerun()
            with col_btn2: st.button("🔄 取消选中", key="btn_cancel_stock", on_click=clear_stock)
            
    else:
        st.info("💡 暂无数据或没有找到符合搜索条件的记录。")
        
    with st.expander("📜 ERP底单：查看所有出入库/平账流水账 (绝密审计日志)", expanded=False):
        st.info("💡 这里记录了每一次库存加减的痕迹，犹如银行流水般不可篡改。如果当年发现改错了，请走『盘点』通道用红字冲回。")
        st.dataframe(get_f(df_restock, q), use_container_width=True)

with t2:
    st.subheader("🛒 智能 POS 收银台 (多件合并结账)")
    
    # 🚀 全新升级：双栏布局（左侧点单，右侧购物车）
    pos_col1, pos_col2 = st.columns([1.2, 1.5])
    
    f_opts = get_f(df_stock, "").copy() 
    if not f_opts.empty:
        f_opts['label'] = f_opts['商品名称'].astype(str) + " (" + f_opts['颜色'].astype(str) + ")" 
        
        with pos_col1:
            with st.container(border=True):
                st.markdown("#### 1️⃣ 扫码/点单区")
                s_l = st.selectbox("选择售出商品", f_opts['label'], key="pos_item")
                selected_row = f_opts[f_opts['label'] == s_l].iloc[0]
                base_price = float(pd.to_numeric(selected_row['售卖价格'], errors='coerce') or 0)
                
                c_q, c_d = st.columns(2)
                s_q = c_q.number_input("销售数量", min_value=1, value=1, step=1, key="pos_qty")
                discount_opts = {"无折扣 (原价)": 1.0, "95折": 0.95, "9折": 0.90, "85折": 0.85, "8折": 0.80, "75折": 0.75, "7折": 0.70, "5折 (半价)": 0.50}
                s_discount = c_d.selectbox("快捷折扣", list(discount_opts.keys()), key="pos_disc")
                
                auto_calc_price = base_price * discount_opts[s_discount]
                s_p = st.number_input("此单品最终成交价 ($)", value=float(auto_calc_price), format="%.2f", key="pos_price")
                
                if st.button("➕ 加入当前购物车", use_container_width=True):
                    item_dict = {
                        "商品名称": str(selected_row['商品名称']),
                        "颜色": str(selected_row['颜色']),
                        "数量": s_q,
                        "单价": s_p,
                        "小计": s_q * s_p
                    }
                    st.session_state.pos_cart.append(item_dict)
                    st.rerun()

        with pos_col2:
            with st.container(border=True):
                st.markdown("#### 2️⃣ 当前购物车")
                if not st.session_state.pos_cart:
                    st.info("🛒 购物车空空如也，请从左侧添加商品。")
                else:
                    cart_df = pd.DataFrame(st.session_state.pos_cart)
                    # 显示漂亮的小计
                    st.dataframe(
                        cart_df.style.format({'单价': '${:.2f}', '小计': '${:.2f}'}), 
                        use_container_width=True, hide_index=True
                    )
                    
                    cart_total_qty = cart_df['数量'].sum()
                    cart_total_amt = cart_df['小计'].sum()
                    
                    st.markdown(f"**🛍️ 本单共计:** `{cart_total_qty}` 件商品 &nbsp;&nbsp;|&nbsp;&nbsp; **💰 合计应收:** ` ${cart_total_amt:.2f}`")
                    
                    co_col1, co_col2 = st.columns([2, 1])
                    s_d = co_col1.date_input("交易日期 (可补录)", value=datetime.now(), key="pos_date")
                    
                    if co_col2.button("🗑️ 清空重点", use_container_width=True):
                        st.session_state.pos_cart = []
                        st.rerun()
                        
                    if st.button("💳 确认结账 (生成流水)", type="primary", use_container_width=True):
                        # 生成统一的订单号
                        order_id = "ORD-" + datetime.now().strftime("%Y%m%d-%H%M%S")
                        order_date = s_d.strftime("%Y/%m/%d")
                        
                        new_rows = []
                        for item in st.session_state.pos_cart:
                            # 1. 构建流水记录
                            new_rows.append([
                                order_id, order_date, item['商品名称'], item['颜色'], 
                                item['数量'], item['单价'], item['小计']
                            ])
                            # 2. 同步扣减库存
                            idx_p = df_stock[(df_stock['商品名称'] == item['商品名称']) & (df_stock['颜色'] == item['颜色'])].index
                            if not idx_p.empty:
                                i_p = idx_p[0]
                                df_stock.at[i_p, '货柜数量'] = int(pd.to_numeric(df_stock.at[i_p, '货柜数量'], errors='coerce') or 0) - item['数量']
                                df_stock.at[i_p, '已售出数量'] = int(pd.to_numeric(df_stock.at[i_p, '已售出数量'], errors='coerce') or 0) + item['数量']
                                df_stock.at[i_p, '总库存'] = sum([int(pd.to_numeric(df_stock.at[i_p, col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                        
                        # 批量插入新订单
                        new_sales_df = pd.DataFrame(new_rows, columns=SALES_COLS)
                        global df_sales
                        df_sales = pd.concat([new_sales_df, df_sales], ignore_index=True)
                        
                        save_data(df_sales, SALES_SHEET) 
                        save_data(df_stock, STOCK_SHEET) 
                        
                        # 结账完成后清空购物车
                        st.session_state.pos_cart = []
                        st.success(f"🎉 结账成功！流水号 {order_id} 已记录，库存已自动扣除。")
                        st.rerun()
                        
    else:
        st.info("请先在库存中添加商品。")

    with st.expander("🔄 客户换货处理 (Exchange) - 保证财务毛利准确", expanded=False):
        st.info("💡 系统会自动生成一条负数的退货流水和一条正数的新销售流水，完美自动冲销，不影响报表毛利率！")
        if not f_opts.empty:
            xc1, xc2 = st.columns(2)
            with xc1:
                st.markdown("### 🔙 客户退回的商品 (入库)")
                ex_ret_l = st.selectbox("1. 选择退回的商品", f_opts['label'], key="ex_ret_sku")
                ret_row = f_opts[f_opts['label'] == ex_ret_l].iloc[0]
                ret_base_p = float(pd.to_numeric(ret_row['售卖价格'], errors='coerce') or 0)
                ret_p = st.number_input("2. 当时成交单价 (退款额 $)", value=ret_base_p, format="%.2f", help="客人当时买这个杯子花了多少钱？")
                ret_dmg = st.checkbox("⚠️ 退回商品有瑕疵 (记入坏货库，不回上架)", value=False)

            with xc2:
                st.markdown("### 🆕 客户换购的商品 (出库)")
                ex_new_l = st.selectbox("1. 选择拿走的商品", f_opts['label'], key="ex_new_sku")
                new_row = f_opts[f_opts['label'] == ex_new_l].iloc[0]
                new_base_p = float(pd.to_numeric(new_row['售卖价格'], errors='coerce') or 0)
                new_p = st.number_input("2. 今日换购单价 (售价 $)", value=new_base_p, format="%.2f")

            st.markdown("---")
            
            c_date, c_diff = st.columns(2)
            with c_date:
                ex_date_input = st.date_input("📅 换货交易日期", value=datetime.now(), key="ex_date_input")
            
            with c_diff:
                diff = new_p - ret_p
                if diff > 0:
                    st.warning(f"💰 **需补差价：请向客户收取 ${diff:.2f}**")
                elif diff < 0:
                    st.success(f"💸 **需退差价：请退还客户 ${abs(diff):.2f}**")
                else:
                    st.info("🤝 **等价交换：无需补退差价**")

            if st.button("🔄 确认执行换货", type="primary", use_container_width=True):
                ex_date = ex_date_input.strftime("%Y/%m/%d")
                ex_order_id = "EXC-" + datetime.now().strftime("%Y%m%d-%H%M%S") # 换货专用订单号
                
                idx_ret = df_stock[(df_stock['商品名称'] == ret_row['商品名称']) & (df_stock['颜色'] == ret_row['颜色'])].index[0]
                s_ret = pd.DataFrame([[ex_order_id, ex_date, df_stock.at[idx_ret,'商品名称'], df_stock.at[idx_ret,'颜色'], -1, ret_p, -1 * ret_p]], columns=SALES_COLS)
                
                idx_new = df_stock[(df_stock['商品名称'] == new_row['商品名称']) & (df_stock['颜色'] == new_row['颜色'])].index[0]
                s_new = pd.DataFrame([[ex_order_id, ex_date, df_stock.at[idx_new,'商品名称'], df_stock.at[idx_new,'颜色'], 1, new_p, 1 * new_p]], columns=SALES_COLS)
                
                df_sales = pd.concat([s_new, s_ret, df_sales], ignore_index=True)
                
                if ret_dmg:
                    df_stock.at[idx_ret, '坏货数量'] = int(pd.to_numeric(df_stock.at[idx_ret, '坏货数量'], errors='coerce') or 0) + 1
                else:
                    df_stock.at[idx_ret, '货柜数量'] = int(pd.to_numeric(df_stock.at[idx_ret, '货柜数量'], errors='coerce') or 0) + 1
                    df_stock.at[idx_ret, '总库存'] = sum([int(pd.to_numeric(df_stock.at[idx_ret, col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                df_stock.at[idx_ret, '已售出数量'] = int(pd.to_numeric(df_stock.at[idx_ret, '已售出数量'], errors='coerce') or 0) - 1
                
                df_stock.at[idx_new, '货柜数量'] = int(pd.to_numeric(df_stock.at[idx_new, '货柜数量'], errors='coerce') or 0) - 1
                df_stock.at[idx_new, '已售出数量'] = int(pd.to_numeric(df_stock.at[idx_new, '已售出数量'], errors='coerce') or 0) + 1
                df_stock.at[idx_new, '总库存'] = sum([int(pd.to_numeric(df_stock.at[idx_new, col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                
                save_data(df_sales, SALES_SHEET) 
                save_data(df_stock, STOCK_SHEET) 
                st.success(f"🎉 换货成功！已按日期 {ex_date} 自动入库/出库，并冲销流水。")
                st.rerun()

    st.divider()
    f_sl = get_f(df_sales, q)
    if not f_sl.empty:
        f_sl_sel = f_sl.copy(); f_sl_sel.insert(0, "选择", False)
        
        f_sl_sel['成交单价'] = pd.to_numeric(f_sl_sel['成交单价'], errors='coerce').fillna(0.0)
        f_sl_sel['总营业额'] = pd.to_numeric(f_sl_sel['总营业额'], errors='coerce').fillna(0.0)
        styled_sl = f_sl_sel.style.format({'成交单价': '${:.2f}', '总营业额': '${:.2f}'})
        
        edt = st.data_editor(styled_sl, column_config={"选择": st.column_config.CheckboxColumn("选择", default=False)}, disabled=f_sl.columns, use_container_width=True, hide_index=True, key=f"sales_editor_{st.session_state.sales_reset_key}")
        sel = edt[edt["选择"] == True]
        
        if not sel.empty:
            sc1, sc2, _ = st.columns([1.5, 1.5, 4])
            with sc1:
                if st.button("🔴 批量撤销流水", type="primary"):
                    for _, r in sel.iterrows():
                        m = df_stock[(df_stock['商品名称']==r['商品名称']) & (df_stock['颜色']==r['颜色'])].index
                        if not m.empty:
                            df_stock.at[m[0], '货柜数量'] = int(pd.to_numeric(df_stock.at[m[0], '货柜数量'], errors='coerce') or 0) + int(pd.to_numeric(r['销售数量'], errors='coerce') or 0)
                            df_stock.at[m[0], '已售出数量'] = int(pd.to_numeric(df_stock.at[m[0], '已售出数量'], errors='coerce') or 0) - int(pd.to_numeric(r['销售数量'], errors='coerce') or 0)
                            df_stock.at[m[0], '总库存'] = sum([int(pd.to_numeric(df_stock.at[m[0], col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                    for _, r in sel.iterrows():
                        df_sales = df_sales[~((df_sales['日期']==r['日期']) & (df_sales['商品名称']==r['商品名称']) & (df_sales['颜色']==r['颜色']) & (df_sales['销售数量']==r['销售数量']))]
                    save_data(df_stock, STOCK_SHEET); save_data(df_sales, SALES_SHEET)
                    st.session_state.sales_reset_key += 1
                    st.rerun()
            with sc2: st.button("🔄 取消所有选中", key="btn_cancel_sales", on_click=clear_sales)
            
            if len(sel) == 1:
                st.write("### ⚙️ 编辑选中流水记录 (修改将自动同步修正库存)")
                orig_idx = sel.index[0] 
                
                old_name = str(df_sales.at[orig_idx, '商品名称'])
                old_color = str(df_sales.at[orig_idx, '颜色'])
                curr_label = f"{old_name} ({old_color})"
                
                prod_list = []
                if not df_stock.empty:
                    prod_list = (df_stock['商品名称'].astype(str) + " (" + df_stock['颜色'].astype(str) + ")").tolist()
                if curr_label not in prod_list:
                    prod_list.insert(0, curr_label)
                    
                with st.form("edit_sale_form"):
                    e_c1, e_c2, e_c3, e_c4 = st.columns(4)
                    
                    try:
                        parsed_date = pd.to_datetime(df_sales.at[orig_idx, '日期']).date()
                    except:
                        parsed_date = datetime.now().date()
                        
                    e_date = e_c1.date_input("交易日期", value=parsed_date)
                    e_prod = e_c2.selectbox("修改款式/颜色", prod_list, index=prod_list.index(curr_label))
                    e_qty = e_c3.number_input("销售数量", value=int(df_sales.at[orig_idx, '销售数量']))
                    e_price = e_c4.number_input("成交单价 ($)", value=float(df_sales.at[orig_idx, '成交单价']), format="%.2f")
                    
                    if st.form_submit_button("💾 保存流水修改", type="primary", use_container_width=True):
                        old_qty = int(df_sales.at[orig_idx, '销售数量'])
                        
                        old_m = df_stock[(df_stock['商品名称'] == old_name) & (df_stock['颜色'] == old_color)].index
                        if not old_m.empty:
                            o_idx = old_m[0]
                            df_stock.at[o_idx, '货柜数量'] = int(pd.to_numeric(df_stock.at[o_idx, '货柜数量'], errors='coerce') or 0) + old_qty
                            df_stock.at[o_idx, '已售出数量'] = int(pd.to_numeric(df_stock.at[o_idx, '已售出数量'], errors='coerce') or 0) - old_qty
                            df_stock.at[o_idx, '总库存'] = sum([int(pd.to_numeric(df_stock.at[o_idx, col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                        
                        new_name = e_prod.rsplit(" (", 1)[0]
                        new_color = e_prod.rsplit(" (", 1)[1].replace(")", "")
                        new_qty = e_qty
                        
                        new_m = df_stock[(df_stock['商品名称'] == new_name) & (df_stock['颜色'] == new_color)].index
                        if not new_m.empty:
                            n_idx = new_m[0]
                            df_stock.at[n_idx, '货柜数量'] = int(pd.to_numeric(df_stock.at[n_idx, '货柜数量'], errors='coerce') or 0) - new_qty
                            df_stock.at[n_idx, '已售出数量'] = int(pd.to_numeric(df_stock.at[n_idx, '已售出数量'], errors='coerce') or 0) + new_qty
                            df_stock.at[n_idx, '总库存'] = sum([int(pd.to_numeric(df_stock.at[n_idx, col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                        
                        df_sales.at[orig_idx, '日期'] = e_date.strftime("%Y/%m/%d")
                        df_sales.at[orig_idx, '商品名称'] = new_name
                        df_sales.at[orig_idx, '颜色'] = new_color
                        df_sales.at[orig_idx, '销售数量'] = new_qty
                        df_sales.at[orig_idx, '成交单价'] = e_price
                        df_sales.at[orig_idx, '总营业额'] = new_qty * e_price
                        
                        save_data(df_stock, STOCK_SHEET)
                        save_data(df_sales, SALES_SHEET)
                        st.session_state.sales_reset_key += 1
                        st.rerun()

    else:
        st.info("💡 暂无流水记录或没有找到符合条件的流水。")

with t3:
    st.subheader("📊 财务与客流报表 (含连带率分析)")
    if not df_sales.empty:
        df_sales['日期_dt'] = pd.to_datetime(df_sales['日期'], errors='coerce')
        df_sales_clean = df_sales.dropna(subset=['日期_dt']).copy()
        
        if not df_sales_clean.empty:
            sel_range = st.date_input("选择查看时间段", value=[df_sales_clean['日期_dt'].min().date(), df_sales_clean['日期_dt'].max().date()])
            if len(sel_range) == 2:
                start, end = sel_range
                f_sales_range = df_sales_clean[(df_sales_clean['日期_dt'] >= pd.Timestamp(start)) & (df_sales_clean['日期_dt'] <= pd.Timestamp(end))].copy()
                
                f_sales_range['销售数量'] = pd.to_numeric(f_sales_range['销售数量'], errors='coerce').fillna(0)
                f_sales_range['总营业额'] = pd.to_numeric(f_sales_range['总营业额'], errors='coerce').fillna(0.0)
                
                # 🚀 核心升级：增加客流单数核算
                tot_rev = f_sales_range['总营业额'].sum()
                tot_items = f_sales_range['销售数量'].sum()
                
                # 算有多少个独立的新订单 (过滤掉换货单和历史单)
                valid_orders = f_sales_range[
                    (~f_sales_range['订单号'].str.contains('历史单', na=False)) & 
                    (~f_sales_range['订单号'].str.contains('EXC-', na=False))
                ]
                order_count = valid_orders['订单号'].nunique()
                
                # 算历史单的粗略笔数（1行算1笔）用来兜底显示
                legacy_orders = f_sales_range[f_sales_range['订单号'].str.contains('历史单', na=False)]
                total_order_count = order_count + len(legacy_orders)
                
                acv = tot_rev / total_order_count if total_order_count > 0 else 0
                upt = tot_items / total_order_count if total_order_count > 0 else 0
                
                period = st.radio("维度", ["Daily", "Weekly", "Monthly"], horizontal=True)
                if "Daily" in period: f_sales_range['周期'] = f_sales_range['日期_dt'].dt.strftime('%Y/%m/%d')
                elif "Weekly" in period: f_sales_range['周期'] = (f_sales_range['日期_dt'] - pd.to_timedelta(f_sales_range['日期_dt'].dt.dayofweek, unit='D')).dt.strftime('Week of %b %d')
                else: f_sales_range['周期'] = f_sales_range['日期_dt'].dt.strftime('%Y/%m')
                
                summ = f_sales_range.groupby(['周期', '商品名称', '颜色']).agg({'销售数量':'sum', '总营业额':'sum'}).reset_index()
                
                df_stock_calc = df_stock[['商品名称', '颜色', '进价成本']].copy()
                df_stock_calc['进价成本'] = pd.to_numeric(df_stock_calc['进价成本'], errors='coerce').fillna(0.0)
                
                summ = summ.merge(df_stock_calc, on=['商品名称', '颜色'], how='left')
                summ['具体毛利'] = summ['总营业额'] - (summ['销售数量'] * summ['进价成本'])
                
                filtered_summ = get_f(summ, q) 
                
                if not filtered_summ.empty:
                    delta_days = (end - start).days + 1
                    
                    st.markdown("### 🏬 门店核心客流漏斗")
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("总营业额", f"${tot_rev:.2f}")
                    m2.metric("💳 交易单数 (客流)", f"{total_order_count} 单", help="包含多件合并的新系统订单以及过往的历史单行数")
                    m3.metric("🛒 平均客单价 (ACV)", f"${acv:.2f}", help="平均每个结账的客人花多少钱 (总营收/总单数)")
                    m4.metric("🛍️ 连带率 (UPT)", f"{upt:.2f} 件/单", help="平均每个客人一次买走几件东西 (总件数/总单数)")
                    
                    st.divider()
                    
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("具体毛利", f"${filtered_summ['具体毛利'].sum():.2f}")
                    c2.metric("总售出件数", f"{int(tot_items)} 件")
                    
                    avg_m = filtered_summ['具体毛利'].sum() / tot_rev * 100 if tot_rev > 0 else 0
                    c3.metric("平均毛利率", f"{avg_m:.1f}%")
                    
                    avg_daily = tot_rev / delta_days if delta_days > 0 else 0
                    c4.metric("日均坪效 (每日营收)", f"${avg_daily:.2f}")
                    
                    st.divider()
                    st.markdown("### 📈 营收与毛利走势")
                    chart_data_t3 = filtered_summ.groupby('周期')[['总营业额', '具体毛利']].sum().sort_index(ascending=True)
                    st.bar_chart(chart_data_t3, use_container_width=True)

                    dl_c1, dl_c2 = st.columns([1, 4])
                    with dl_c1:
                        csv_t3 = convert_df_to_csv(filtered_summ)
                        st.download_button(
                            label="⬇️ 一键导出毛利报表 (CSV)",
                            data=csv_t3,
                            file_name=f"Takashimaya_毛利报表_{datetime.now().strftime('%Y%m%d')}.csv",
                            mime="text/csv",
                            type="primary"
                        )
                    
                    st.dataframe(filtered_summ.sort_values('周期', ascending=False).style.format({'总营业额':"${:.2f}", '具体毛利':"${:.2f}", '销售数量':"{:d}"}), use_container_width=True)
                else:
                    st.info("💡 在选定时间段内没有找到符合搜索条件的销售记录。")
        else:
            st.info("流水表中没有有效的日期数据。")

with t4:
    st.subheader("👥 员工档案管理")
    with st.expander("➕ 新增员工档案", expanded=False):
        with st.form("add_employee"):
            c1, c2 = st.columns(2)
            e_name = c1.text_input("员工姓名")
            e_role = c2.selectbox("职位", ["店长", "全职店员", "兼职店员", "实习生", "其他"])
            c3, c4, c5 = st.columns(3)
            e_wage = c3.number_input("时薪 ($/小时)", min_value=0.0, step=0.5, value=12.0, format="%.2f")
            e_phone = c4.text_input("联系方式 (选填)")
            e_date = c5.date_input("入职日期", value=datetime.now())
            if st.form_submit_button("保存员工信息"):
                if e_name.strip() == "": st.warning("⚠️ 员工姓名不能为空！")
                elif e_name in df_employee['员工姓名'].values: st.warning(f"⚠️ 员工 {e_name} 已经存在！")
                else:
                    new_emp = pd.DataFrame([[e_name, e_role, e_wage, e_phone, e_date.strftime("%Y/%m/%d")]], columns=EMP_COLS)
                    df_employee = pd.concat([df_employee, new_emp], ignore_index=True)
                    save_data(df_employee, EMP_SHEET) 
                    st.session_state.emp_reset_key += 1
                    st.rerun()

    f_employee = get_f(df_employee, q) 
    if not f_employee.empty:
        v_emp = f_employee.copy()
        v_emp.insert(0, "选择", False)
        
        v_emp['时薪'] = pd.to_numeric(v_emp['时薪'], errors='coerce').fillna(0.0)
        styled_emp = v_emp.style.format({'时薪': '${:.2f}'})
        
        edited_emp = st.data_editor(styled_emp, column_config={"选择": st.column_config.CheckboxColumn("选择", default=False)}, disabled=f_employee.columns.tolist(), use_container_width=True, hide_index=True, key=f"emp_editor_{st.session_state.emp_reset_key}")
        selected_emp = edited_emp[edited_emp["选择"] == True]
        
        if not selected_emp.empty:
            col_btn1, col_btn2, _ = st.columns([1.5, 1.5, 4])
            with col_btn1:
                if st.button("🗑️ 批量删除员工", type="primary", key="del_emp"):
                    for _, row in selected_emp.iterrows():
                        df_employee = df_employee[df_employee['员工姓名'] != row['员工姓名']]
                    save_data(df_employee, EMP_SHEET)
                    st.session_state.emp_reset_key += 1; st.rerun()
            with col_btn2: st.button("🔄 取消所有选中", key="btn_cancel_emp", on_click=clear_emp)

    st.divider()
    st.subheader("⏰ 排班与打卡记录")
    
    if df_employee.empty:
        st.info("💡 请先在上方添加至少一名员工，才能开始记录考勤。")
    else:
        with st.expander("➕ 登记工作排班/打卡", expanded=True):
            with st.form("add_attendance"):
                c1, c2 = st.columns(2)
                att_name = c1.selectbox("选择员工", df_employee['员工姓名'].astype(str).tolist())
                att_date = c2.date_input("工作日期", value=datetime.now())
                
                c3, c4 = st.columns(2)
                att_start = c3.time_input("上班时间", value=time(10, 0))
                att_end = c4.time_input("下班时间", value=time(18, 0))
                
                if st.form_submit_button("确认记录考勤"):
                    dt_start = datetime.combine(att_date, att_start)
                    dt_end = datetime.combine(att_date, att_end)
                    if dt_end < dt_start: dt_end += timedelta(days=1)
                        
                    duration_hours = (dt_end - dt_start).total_seconds() / 3600.0
                    
                    wage_val = df_employee[df_employee['员工姓名'] == att_name]['时薪'].iloc[0]
                    hourly_wage = float(pd.to_numeric(wage_val, errors='coerce') or 0.0)
                    total_wage = duration_hours * hourly_wage
                    
                    new_att = pd.DataFrame([[
                        att_name, att_date.strftime("%Y/%m/%d"), 
                        att_start.strftime("%H:%M"), att_end.strftime("%H:%M"), 
                        round(duration_hours, 2), round(total_wage, 2)
                    ]], columns=ATT_COLS)
                    
                    df_attendance = pd.concat([new_att, df_attendance], ignore_index=True)
                    save_data(df_attendance, ATT_SHEET) 
                    
                    st.success(f"已记录 {att_name} 的工时: {round(duration_hours, 1)} 小时，核算薪资: ${round(total_wage, 2)}")
                    st.rerun()

        f_att = get_f(df_attendance, q)
        if not f_att.empty:
            v_att = f_att.copy()
            v_att.insert(0, "选择", False)
            
            v_att['核算薪资'] = pd.to_numeric(v_att['核算薪资'], errors='coerce').fillna(0.0)
            styled_att = v_att.style.format({'核算薪资': '${:.2f}'})
            
            edited_att = st.data_editor(
                styled_att, 
                column_config={"选择": st.column_config.CheckboxColumn("选择", default=False)}, 
                disabled=f_att.columns.tolist(), 
                use_container_width=True, hide_index=True, 
                key=f"att_editor_{st.session_state.att_reset_key}"
            )
            selected_att = edited_att[edited_att["选择"] == True]
            
            if not selected_att.empty:
                col_btn1, col_btn2, _ = st.columns([1.5, 1.5, 4])
                with col_btn1:
                    if st.button("🗑️ 删除选中打卡记录", type="primary", key="del_att"):
                        for _, row in selected_att.iterrows():
                            df_attendance = df_attendance[~((df_attendance['员工姓名'] == row['员工姓名']) & (df_attendance['日期'] == row['日期']) & (df_attendance['开始时间'] == row['开始时间']))]
                        save_data(df_attendance, ATT_SHEET)
                        st.session_state.att_reset_key += 1 
                        st.rerun()
                with col_btn2: st.button("🔄 取消所有选中", key="btn_cancel_att", on_click=clear_att)
            
            st.divider()
            total_hours = pd.to_numeric(f_att['工作时长'], errors='coerce').fillna(0).sum()
            total_wage = pd.to_numeric(f_att['核算薪资'], errors='coerce').fillna(0).sum()
            
            c_t1, c_t2, c_t3 = st.columns([2, 1, 1])
            c_t1.markdown(f"**🧾 列表总计** (共 {len(f_att)} 条记录)")
            c_t2.metric("当前列表总工时", f"{total_hours:.1f} 小时")
            c_t3.metric("当前列表总薪资支出", f"${total_wage:.2f}")

with t5:
    st.subheader("💎 真实净利润核算 (Net Profit)")
    st.info("💡 此页仅核算高岛屋【零售流水】。净利润 = 总营业额 - 高岛屋抽成(36%) - 进价成本 - 打卡工资。")

    if not df_sales.empty:
        df_s_np = df_sales.copy()
        df_s_np['日期_dt'] = pd.to_datetime(df_s_np['日期'], errors='coerce')
        df_s_np = df_s_np.dropna(subset=['日期_dt'])

        df_a_np = df_attendance.copy()
        if not df_a_np.empty:
            df_a_np['日期_dt'] = pd.to_datetime(df_a_np['日期'], errors='coerce')
            df_a_np = df_a_np.dropna(subset=['日期_dt'])
        else:
            df_a_np['日期_dt'] = pd.Series(dtype='datetime64[ns]')

        if not df_s_np.empty:
            min_date = df_s_np['日期_dt'].min().date()
            max_date = df_s_np['日期_dt'].max().date()
            if not df_a_np.empty:
                min_date = min(min_date, df_a_np['日期_dt'].min().date())
                max_date = max(max_date, df_a_np['日期_dt'].max().date())

            np_range = st.date_input("选择核算时间段", value=[min_date, max_date], key="np_date_range")

            if len(np_range) == 2:
                start_d, end_d = np_range
                
                fs = df_s_np[(df_s_np['日期_dt'] >= pd.Timestamp(start_d)) & (df_s_np['日期_dt'] <= pd.Timestamp(end_d))].copy()
                fa = df_a_np[(df_a_np['日期_dt'] >= pd.Timestamp(start_d)) & (df_a_np['日期_dt'] <= pd.Timestamp(end_d))].copy()

                fs['销售数量'] = pd.to_numeric(fs['销售数量'], errors='coerce').fillna(0)
                fs['总营业额'] = pd.to_numeric(fs['总营业额'], errors='coerce').fillna(0.0)

                df_stock_cost = df_stock[['商品名称', '颜色', '进价成本']].copy()
                df_stock_cost['进价成本'] = pd.to_numeric(df_stock_cost['进价成本'], errors='coerce').fillna(0.0)
                fs = fs.merge(df_stock_cost, on=['商品名称', '颜色'], how='left')
                fs['总进价成本'] = fs['销售数量'] * fs['进价成本']

                fs['日期_str'] = fs['日期_dt'].dt.strftime('%Y/%m/%d')
                daily_sales = fs.groupby('日期_str').agg({'总营业额': 'sum', '总进价成本': 'sum'}).reset_index()

                if not fa.empty:
                    fa['核算薪资'] = pd.to_numeric(fa['核算薪资'], errors='coerce').fillna(0.0)
                    fa['日期_str'] = fa['日期_dt'].dt.strftime('%Y/%m/%d')
                    daily_att = fa.groupby('日期_str').agg({'核算薪资': 'sum'}).reset_index()
                    daily_att.rename(columns={'核算薪资': '人工成本'}, inplace=True)
                else:
                    daily_att = pd.DataFrame(columns=['日期_str', '人工成本'])

                daily_np = pd.merge(daily_sales, daily_att, on='日期_str', how='outer').fillna(0.0)
                daily_np = daily_np.sort_values('日期_str', ascending=False)

                daily_np['商场抽成(36%)'] = daily_np['总营业额'] * 0.36
                daily_np['扣点后营收'] = daily_np['总营业额'] - daily_np['商场抽成(36%)']
                daily_np['毛利润'] = daily_np['扣点后营收'] - daily_np['总进价成本']
                daily_np['真实净利润'] = daily_np['毛利润'] - daily_np['人工成本']

                tot_rev = daily_np['总营业额'].sum()
                tot_comm = daily_np['商场抽成(36%)'].sum()
                tot_cogs = daily_np['总进价成本'].sum()
                tot_wage = daily_np['人工成本'].sum()
                tot_net = daily_np['真实净利润'].sum()

                pct_comm = (tot_comm / tot_rev * 100) if tot_rev > 0 else 0
                pct_cogs = (tot_cogs / tot_rev * 100) if tot_rev > 0 else 0
                pct_wage = (tot_wage / tot_rev * 100) if tot_rev > 0 else 0
                pct_net = (tot_net / tot_rev * 100) if tot_rev > 0 else 0

                st.markdown("### 📊 阶段性核心指标")
                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("💰 总营业额", f"${tot_rev:.2f}", delta="100.0% (营收基准)", delta_color="off")
                m2.metric("🏢 商场抽成 (36%)", f"${tot_comm:.2f}", delta=f"占比: {pct_comm:.1f}%", delta_color="off")
                m3.metric("📦 商品成本", f"${tot_cogs:.2f}", delta=f"占比: {pct_cogs:.1f}%", delta_color="off")
                m4.metric("👥 人工成本", f"${tot_wage:.2f}", delta=f"占比: {pct_wage:.1f}%", delta_color="off")
                m5.metric("💎 真实净利润", f"${tot_net:.2f}", delta=f"净利率: {pct_net:.1f}%", delta_color="off")

                st.divider()
                st.markdown("### 📈 每日营收 vs 净利润趋势")
                chart_data_t5 = daily_np.set_index('日期_str')[['总营业额', '真实净利润']].sort_index(ascending=True)
                st.bar_chart(chart_data_t5, use_container_width=True)

                st.markdown("### 📅 每日盈亏明细榜 (Daily P&L)")
                dl_c3, dl_c4 = st.columns([1.5, 4])
                with dl_c3:
                    csv_t5 = convert_df_to_csv(daily_np)
                    st.download_button(
                        label="⬇️ 一键导出净利润明细 (CSV)",
                        data=csv_t5,
                        file_name=f"Takashimaya_净利明细_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        type="primary"
                    )

                show_np = daily_np.rename(columns={'日期_str': '日期'})
                
                def color_net_profit(val):
                    try:
                        val = float(val)
                        if val > 0: return 'background-color: #e6ffe6; color: #006600; font-weight: bold;'
                        elif val < 0: return 'background-color: #ffe6e6; color: #cc0000; font-weight: bold;'
                    except: pass
                    return ''
                
                try:
                    styled_np = show_np.style.format({
                        '总营业额': '${:.2f}', '商场抽成(36%)': '${:.2f}', '扣点后营收': '${:.2f}',
                        '总进价成本': '${:.2f}', '人工成本': '${:.2f}',
                        '毛利润': '${:.2f}', '真实净利润': '${:.2f}'
                    }).map(color_net_profit, subset=['真实净利润'])
                except AttributeError:
                    styled_np = show_np.style.format({
                        '总营业额': '${:.2f}', '商场抽成(36%)': '${:.2f}', '扣点后营收': '${:.2f}',
                        '总进价成本': '${:.2f}', '人工成本': '${:.2f}',
                        '毛利润': '${:.2f}', '真实净利润': '${:.2f}'
                    }).applymap(color_net_profit, subset=['真实净利润'])

                st.dataframe(styled_np, use_container_width=True, hide_index=True)
        else:
            st.info("暂无有效销售数据进行核算。")
    else:
        st.info("💡 目前没有流水记录，无法计算利润。")

with t6:
    st.subheader("🤝 B2B 大客户与企采订单管理")
    st.info("💡 B2B订单独立核算，免收快闪店抽成！支持【单一商品】与【多件组合套装】双模式。")

    if not df_b2b.empty:
        for num_col in ['总计应收', '已收定金', '货物成本', '物流成本', '关税']:
            df_b2b[num_col] = pd.to_numeric(df_b2b[num_col], errors='coerce').fillna(0.0)
            
        df_b2b['待收尾款'] = df_b2b['总计应收'] - df_b2b['已收定金']
        df_b2b['B2B净利润'] = df_b2b['总计应收'] - df_b2b['货物成本'] - df_b2b['物流成本'] - df_b2b['关税']
        
        df_b2b['预估净利率'] = df_b2b.apply(lambda r: f"{(r['B2B净利润'] / r['总计应收'] * 100):.1f}%" if r['总计应收'] > 0 else "0.0%", axis=1)
        
        tot_b2b_val = df_b2b['总计应收'].sum()
        tot_b2b_collected = df_b2b['已收定金'].sum()
        tot_b2b_pending = df_b2b['待收尾款'].sum()
        tot_b2b_profit = df_b2b['B2B净利润'].sum()
        
        pct_b2b_profit = (tot_b2b_profit / tot_b2b_val * 100) if tot_b2b_val > 0 else 0.0
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💼 B2B 总合同额", f"${tot_b2b_val:.2f}")
        c2.metric("💰 已回款金额", f"${tot_b2b_collected:.2f}")
        c3.metric("⏳ 待结清尾款", f"${tot_b2b_pending:.2f}")
        c4.metric("💎 B2B 预估净利润", f"${tot_b2b_profit:.2f}", delta=f"净利率: {pct_b2b_profit:.1f}%", delta_color="off")

    with st.expander("➕ 录入全新 B2B 订单", expanded=False):
        col1, col2 = st.columns(2)
        b2b_client = col1.text_input("🏢 客户/企业名称 (必填)", placeholder="例如：NGS")
        b2b_date = col2.date_input("📅 建单日期", value=datetime.now())

        order_mode = st.radio("🛒 选择订单商品模式", ["🎯 单一商品 (常规下单)", "📦 多件组合 / 礼盒套装"], horizontal=True)

        final_name = ""
        final_color = ""
        final_qty = 0
        final_price = 0.0
        final_total = 0.0
        final_notes = ""

        if order_mode == "🎯 单一商品 (常规下单)":
            st.write("📦 **商品信息 (二选一)**")
            f_opts_b2b = get_f(df_stock, "").copy() 
            stock_list = []
            if not f_opts_b2b.empty:
                f_opts_b2b['label'] = f_opts_b2b['商品名称'].astype(str) + " (" + f_opts_b2b['颜色'].astype(str) + ")" 
                stock_list = f_opts_b2b['label'].tolist()
                
            col_sel, col_cust_name, col_cust_color = st.columns([2, 1.5, 1])
            b2b_prod = col_sel.selectbox("方式A：选择现有商品", ["(不选择)"] + stock_list)
            b2b_custom_prod = col_cust_name.text_input("方式B：手动输入定制商品", placeholder="填写此项将覆盖左侧")
            b2b_custom_color = col_cust_color.text_input("定制颜色", placeholder="选填")

            c_q, c_p = st.columns(2)
            b2b_qty = c_q.number_input("采购数量", min_value=1, value=100, step=10)
            b2b_price = c_p.number_input("B2B 批发单价 ($)", format="%.2f", min_value=0.0)

            final_total = b2b_qty * b2b_price
            final_qty = b2b_qty
            final_price = b2b_price

            if b2b_custom_prod.strip() != "":
                final_name = b2b_custom_prod.strip()
                final_color = b2b_custom_color.strip()
            else:
                if b2b_prod != "(不选择)":
                    sel_row = f_opts_b2b[f_opts_b2b['label'] == b2b_prod].iloc[0]
                    final_name = sel_row['商品名称']
                    final_color = sel_row['颜色']
                else:
                    final_name = ""

        else:
            combo_name = st.text_input("📦 组合大单名称 (必填)", placeholder="例如：NGS 100件定制混装礼盒")
            st.write("👇 **请在下方表格中录入组合包含的商品明细 (可自由添加多行)**")
            
            default_df = pd.DataFrame([{"商品或定制名称": "钛杯", "颜色/规格": "默认", "单价($)": 0.0, "数量": 1}])
            
            edited_cart = st.data_editor(
                default_df, 
                num_rows="dynamic", 
                use_container_width=True, 
                key="b2b_combo_cart",
                column_config={
                    "单价($)": st.column_config.NumberColumn(format="%.2f", min_value=0.0), 
                    "数量": st.column_config.NumberColumn(min_value=1, step=1)
                }
            )

            desc_items = []
            for cart_idx, cart_row in edited_cart.iterrows():
                try:
                    cart_p = float(cart_row["单价($)"])
                    cart_q = int(cart_row["数量"])
                    cart_n = str(cart_row["商品或定制名称"]).strip()
                    cart_c = str(cart_row["颜色/规格"]).strip()
                    if cart_n:
                        final_total += cart_p * cart_q
                        final_qty += cart_q
                        item_str = f"{cart_n}({cart_c})x{cart_q}" if cart_c else f"{cart_n}x{cart_q}"
                        desc_items.append(item_str)
                except:
                    pass

            st.info(f"🧮 **系统实时核算：** 此组合共计 **{final_qty}** 件物品，总金额 **${final_total:.2f}**")
            final_name = f"【组合】{combo_name.strip()}"
            final_color = "多件混装"
            final_price = 0.0 
            combo_details_str = " + ".join(desc_items)

        st.markdown("---")
        st.write("🚚 **履约成本与交易状态**")
        c10, c11, c12, c13 = st.columns(4)
        b2b_deposit = c10.number_input("已收定金/首款 ($)", format="%.2f", min_value=0.0)
        b2b_cogs = c11.number_input("预估总货物成本 ($)", format="%.2f", min_value=0.0)
        b2b_shipping = c12.number_input("预估物流总成本 ($)", format="%.2f", min_value=0.0)
        b2b_tax = c13.number_input("预估关税 ($)", format="%.2f", min_value=0.0)

        c8, c9, c_dead = st.columns([1, 1.5, 1])
        b2b_status = c8.selectbox("当前状态", ["意向/沟通中", "已付定金/备货中", "已发货/待结尾款", "✅ 订单已完成"])
        b2b_notes = c9.text_input("附加备注信息", placeholder="发货要求等...")
        b2b_deadline = c_dead.date_input("约定交货日期", value=datetime.now() + timedelta(days=30))

        if st.button("🚀 确认创建 B2B 订单", type="primary", use_container_width=True):
            if b2b_client.strip() == "":
                st.error("⚠️ 请填写客户/企业名称！")
            elif not final_name or final_name == "【组合】":
                st.error("⚠️ 请正确选择商品或填写组合名称！")
            else:
                balance = final_total - b2b_deposit
                if order_mode == "📦 多件组合 / 礼盒套装":
                    final_notes_combined = f"明细: {combo_details_str} | 备注: {b2b_notes}"
                else:
                    final_notes_combined = b2b_notes

                new_b2b = pd.DataFrame([[
                    b2b_date.strftime("%Y/%m/%d"), b2b_client, final_name, final_color,
                    final_qty, final_price, final_total, b2b_cogs, b2b_shipping, b2b_tax, b2b_deposit, balance,
                    b2b_deadline.strftime("%Y/%m/%d"), b2b_status, final_notes_combined
                ]], columns=B2B_COLS)

                df_b2b = pd.concat([new_b2b, df_b2b], ignore_index=True)
                save_data(df_b2b, B2B_SHEET)
                st.success(f"✅ B2B 订单创建成功！客户：{b2b_client}")
                st.rerun()

    st.divider()
    st.markdown("### 📋 B2B 订单明细榜 (全字段解禁，可直接双击涂改)")
    
    f_b2b = get_f(df_b2b, q)
    if not f_b2b.empty:
        v_b2b = f_b2b.copy()
        v_b2b.insert(0, "选择", False)
        
        disabled_cols = ['待收尾款', 'B2B净利润', '预估净利率']
        
        styled_b2b = v_b2b.style.format({
            'B2B单价': '${:.2f}', '总计应收': '${:.2f}', 
            '货物成本': '${:.2f}', '物流成本': '${:.2f}', '关税': '${:.2f}',
            '已收定金': '${:.2f}', '待收尾款': '${:.2f}', 'B2B净利润': '${:.2f}'
        })
        
        editor_key = f"b2b_editor_{st.session_state.b2b_reset_key}"
        edited_b2b = st.data_editor(
            styled_b2b, 
            column_config={
                "选择": st.column_config.CheckboxColumn("选择", default=False),
                "订单状态": st.column_config.SelectboxColumn("订单状态", options=["意向/沟通中", "已付定金/备货中", "已发货/待结尾款", "✅ 订单已完成"])
            }, 
            disabled=disabled_cols, 
            use_container_width=True, hide_index=True, 
            key=editor_key
        )
        
        editor_state = st.session_state.get(editor_key, {})
        if editor_state.get("edited_rows"):
            has_real_edits = False
            for idx, row in edited_b2b.iterrows():
                editable_cols = ['货物成本', '物流成本', '关税', '已收定金', '订单状态', '约定交期', '备注']
                is_changed = False
                for c in editable_cols:
                    if str(row[c]) != str(v_b2b.loc[idx, c]):
                        is_changed = True
                        break
                
                if is_changed:
                    has_real_edits = True
                    for col in B2B_COLS:
                        if col in row:
                            df_b2b.at[idx, col] = row[col]
                    
                    total_receivable = float(row['总计应收'] or 0)
                    deposit = float(row['已收定金'] or 0)
                    df_b2b.at[idx, '待收尾款'] = total_receivable - deposit
                    
            if has_real_edits:
                save_data(df_b2b[B2B_COLS], B2B_SHEET) 
                st.success("✅ B2B 订单修改已全量精准保存！")
                st.session_state.b2b_reset_key += 1
                st.rerun()

        selected_b2b = edited_b2b[edited_b2b["选择"] == True]
        if not selected_b2b.empty:
            bc1, bc2, _ = st.columns([1.5, 1.5, 4])
            with bc1:
                if st.button("🗑️ 删除选中订单", type="primary", key="del_b2b"):
                    for _, row in selected_b2b.iterrows():
                        df_b2b = df_b2b[~((df_b2b['客户名称'] == row['客户名称']) & (df_b2b['商品名称'] == row['商品名称']) & (df_b2b['创建日期'] == row['创建日期']))]
                    save_data(df_b2b[B2B_COLS], B2B_SHEET)
                    st.session_state.b2b_reset_key += 1 
                    st.rerun()
            with bc2: st.button("🔄 取消选中", key="btn_cancel_b2b", on_click=clear_b2b)
    else:
        st.info("💡 暂无 B2B 订单记录或没有找到符合搜索条件的订单。")

with t7:
    st.subheader("🗣️ 新加坡本地客户产品反馈池")
    st.info("💡 收集一线真实声音：不论是产品性能还是非产品的本土化优化，都是下一步行动的数据支撑！")

    fb_type_options = [
        "产品功能性", "产品优化", 
        "保温保冷效能", "外观颜值 / 颜色", "材质手感 / 重量", 
        "清洗 / 异味问题", "杯盖 / 密封性", "价格因素", 
        "🌏 本土化优化 (非产品)", "夸奖 / 好评", "其他建议"
    ]
    fb_customer_options = ["本地散客", "VIP / 老客复购", "送礼需求", "游客", "B2B企业客户"]
    fb_status_options = ["🚨 待处理 / 待评估", "📝 已记录 / 待反馈工厂", "✅ 已解决 / 已采纳"]

    with st.expander("➕ 快速录入新反馈", expanded=True):
        f_opts_fb = get_f(df_stock, "").copy()
        with st.form("add_feedback"):
            c1, c2 = st.columns(2)
            fb_date = c1.date_input("反馈日期", value=datetime.now())
            if not f_opts_fb.empty:
                fb_prod = c2.selectbox("提及的商品", f_opts_fb['商品名称'].unique().tolist() + ["全系产品 / 通用"])
            else:
                fb_prod = c2.text_input("提及的商品", "全系产品 / 通用")

            c3, c4 = st.columns(2)
            fb_type = c3.selectbox("反馈痛点 / 类型", fb_type_options)
            fb_customer = c4.selectbox("客户画像", fb_customer_options)

            fb_detail = st.text_area("🗣️ 客户原话或详细描述 (越具体越好)", placeholder="例如：客人觉得杯盖拧起来有点紧，或者希望包装袋能换成本地人更喜欢的材质...")

            fb_status = st.selectbox("当前跟进状态", fb_status_options)

            if st.form_submit_button("保存客户反馈", type="primary", use_container_width=True):
                if fb_detail.strip() == "":
                    st.warning("⚠️ 详细反馈内容不能为空！")
                else:
                    new_fb = pd.DataFrame([[
                        fb_date.strftime("%Y/%m/%d"), fb_prod, fb_customer, fb_type, fb_detail, fb_status
                    ]], columns=FEEDBACK_COLS)
                    df_feedback = pd.concat([new_fb, df_feedback], ignore_index=True)
                    save_data(df_feedback, FEEDBACK_SHEET)
                    st.success("✅ 宝贵的一线反馈已入库！")
                    st.rerun()

    st.divider()
    
    f_fb = get_f(df_feedback, q)
    if not f_fb.empty:
        fb_c1, fb_c2 = st.columns(2)
        with fb_c1:
            st.markdown("**📌 哪些痛点被疯狂吐槽？(分类雷达)**")
            type_counts = f_fb['反馈类型'].value_counts()
            st.bar_chart(type_counts)
        with fb_c2:
            st.markdown("**📌 哪款产品话题度最高？(商品雷达)**")
            prod_counts = f_fb['商品名称'].value_counts()
            st.bar_chart(prod_counts)

        st.markdown("### 📋 客户反馈追踪处理台 (可直接涂改所有项目)")
        v_fb = f_fb.copy()
        v_fb.insert(0, "选择", False)

        editor_key = f"fb_editor_{st.session_state.fb_reset_key}"
        edited_fb = st.data_editor(
            v_fb,
            column_config={
                "选择": st.column_config.CheckboxColumn("选择", default=False),
                "跟进状态": st.column_config.SelectboxColumn("跟进状态", options=fb_status_options),
                "反馈类型": st.column_config.SelectboxColumn("反馈类型", options=fb_type_options),
                "客户画像": st.column_config.SelectboxColumn("客户画像", options=fb_customer_options)
            },
            disabled=[], 
            use_container_width=True, hide_index=True,
            key=editor_key
        )

        editor_state = st.session_state.get(editor_key, {})
        if editor_state.get("edited_rows"):
            has_real_edits = False
            for idx, row in edited_fb.iterrows():
                is_changed = False
                for c in FEEDBACK_COLS:
                    if str(row[c]) != str(v_fb.loc[idx, c]):
                        is_changed = True
                        break
                if is_changed:
                    has_real_edits = True
                    for col in FEEDBACK_COLS:
                        df_feedback.at[idx, col] = row[col]
            if has_real_edits:
                save_data(df_feedback, FEEDBACK_SHEET)
                st.success("✅ 客户反馈修改已全量精准保存！")
                st.session_state.fb_reset_key += 1
                st.rerun()

        selected_fb = edited_fb[edited_fb["选择"] == True]
        if not selected_fb.empty:
            fbc1, fbc2, _ = st.columns([1.5, 1.5, 4])
            with fbc1:
                if st.button("🗑️ 删除选中反馈", type="primary", key="del_fb"):
                    for _, row in selected_fb.iterrows():
                        df_feedback = df_feedback[~((df_feedback['详细原话'] == row['详细原话']) & (df_feedback['反馈日期'] == row['反馈日期']) & (df_feedback['商品名称'] == row['商品名称']))]
                    save_data(df_feedback, FEEDBACK_SHEET)
                    st.session_state.fb_reset_key += 1
                    st.rerun()
            with fbc2: st.button("🔄 取消选中", key="btn_cancel_fb", on_click=clear_fb)
    else:
        st.info("💡 暂无客户反馈记录或没有找到符合条件的反馈。")

with t8:
    st.subheader("📈 选品与战略决策盘 (SKU 矩阵分析)")
    st.info("💡 系统基于全局时间加权动销率和库存深度，自动为你诊断商品健康度，拒绝纸面富贵，定位真实爆款。")
    
    c_launch, _ = st.columns([1, 3])
    launch_date = c_launch.date_input("🏬 快闪店/专柜开业日期 (基准起算日)", value=datetime(2026, 3, 4).date())

    if not df_sales.empty and not df_stock.empty:
        df_s_bi = df_sales.copy()
        df_s_bi['日期_dt'] = pd.to_datetime(df_s_bi['日期'], errors='coerce')
        df_s_bi['销售数量'] = pd.to_numeric(df_s_bi['销售数量'], errors='coerce').fillna(0)
        df_s_bi['总营业额'] = pd.to_numeric(df_s_bi['总营业额'], errors='coerce').fillna(0.0)

        bi_sales = df_s_bi.groupby(['商品名称', '颜色']).agg({
            '销售数量': 'sum',
            '总营业额': 'sum'
        }).reset_index()

        df_stk_bi = df_stock[['商品名称', '颜色', '进价成本', '总库存']].copy()
        df_stk_bi['进价成本'] = pd.to_numeric(df_stk_bi['进价成本'], errors='coerce').fillna(0.0)
        df_stk_bi['总库存'] = pd.to_numeric(df_stk_bi['总库存'], errors='coerce').fillna(0)

        bi_df = pd.merge(df_stk_bi, bi_sales, on=['商品名称', '颜色'], how='left')
        bi_df['销售数量'] = bi_df['销售数量'].fillna(0)
        bi_df['总营业额'] = bi_df['总营业额'].fillna(0.0)

        if not df_restock.empty:
            first_restock = df_restock[df_restock['操作类型'].isin(['入库', '初始建档'])].groupby(['商品名称', '颜色'])['记录日期'].min().reset_index()
            first_restock.rename(columns={'记录日期': '首批入库日期'}, inplace=True)
            first_restock['首批入库日期'] = pd.to_datetime(first_restock['首批入库日期'], errors='coerce').dt.date
            bi_df = pd.merge(bi_df, first_restock, on=['商品名称', '颜色'], how='left')
        else:
            bi_df['首批入库日期'] = pd.NaT

        today = datetime.now().date()
        
        def get_days(row):
            start_date = row['首批入库日期'] if pd.notnull(row['首批入库日期']) else launch_date
            days = (today - start_date).days
            return max(days, 1) 
            
        bi_df['在店天数'] = bi_df.apply(get_days, axis=1)
        bi_df['日均动销率'] = bi_df['销售数量'] / bi_df['在店天数']
        
        bi_df['总进价成本'] = bi_df['销售数量'] * bi_df['进价成本']
        bi_df['具体毛利'] = bi_df['总营业额'] - bi_df['总进价成本']
        bi_df['毛利率(%)'] = (bi_df['具体毛利'] / bi_df['总营业额'] * 100).fillna(0.0)
        
        bi_df['售罄率(%)'] = (bi_df['销售数量'] / (bi_df['销售数量'] + bi_df['总库存']) * 100).fillna(0.0)

        def calc_cover(row):
            if row['日均动销率'] > 0:
                return int(row['总库存'] / row['日均动销率'])
            return 999 
        bi_df['可售天数'] = bi_df.apply(calc_cover, axis=1)

        active_skus = bi_df[bi_df['销售数量'] > 0]
        if not active_skus.empty:
            med_vel = active_skus['日均动销率'].median()
            med_mar = active_skus['毛利率(%)'].median()
        else:
            med_vel, med_mar = 0.1, 0.1

        def get_tag(row):
            if row['总库存'] <= 2 and row['售罄率(%)'] >= 80 and row['销售数量'] > 0:
                return "🔥 秒空断货王 (低估需求)"
            elif row['日均动销率'] >= med_vel and row['毛利率(%)'] >= med_mar:
                return "⭐ 绝对明星 (死保库存)"
            elif row['日均动销率'] >= med_vel and row['毛利率(%)'] < med_mar:
                return "🧲 赚吆喝引流款 (建议搭配)"
            elif row['日均动销率'] < med_vel and row['毛利率(%)'] >= med_mar:
                return "🐢 伪需求高利款 (占压资金)"
            else:
                return "☠️ 清仓废柴 (果断斩仓)"

        bi_df['诊断标签'] = bi_df.apply(get_tag, axis=1)
        bi_df['商品规格'] = bi_df['商品名称'].astype(str) + " (" + bi_df['颜色'].astype(str) + ")"
        
        st.markdown("### 🎯 动销率 vs 盈利能力 雷达图")
        st.scatter_chart(
            bi_df,
            x='日均动销率',
            y='毛利率(%)',
            color='诊断标签',
            height=400
        )
        
        st.markdown("### 📋 智能选品行动指南表")
        
        display_bi_df = bi_df[['商品规格', '诊断标签', '日均动销率', '毛利率(%)', '可售天数', '总库存', '总营业额']].sort_values(by=['诊断标签', '日均动销率'], ascending=[True, False])
        
        styled_bi = display_bi_df.style.format({
            '总营业额': '${:.2f}', 
            '日均动销率': '{:.2f} 件/天',
            '毛利率(%)': '{:.1f}%',
            '可售天数': lambda x: '> 半年' if x == 999 else f"{x} 天"
        })
        
        st.dataframe(styled_bi, use_container_width=True, hide_index=True)
        
    else:
        st.warning("⚠️ 需要有充足的【库存进价】和【销售流水】数据才能生成战略罗盘，快去多记两笔账吧！")
