import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
import gspread 
from gspread.exceptions import WorksheetNotFound
import json
import plotly.express as px

st.set_page_config(page_title="Taka 零售终极管理系统", layout="wide")

try:
    key_dict = json.loads(st.secrets["google_key"])
    gc = gspread.service_account_from_dict(key_dict)
    sh = gc.open_by_url(st.secrets["sheet_url"]) 
except Exception as e:
    st.error(f"🔴 数据库连接失败 Database connection failed! Error: {e}")
    st.stop()

# ================= 🚀 国际化双语翻译引擎 =================
if "lang" not in st.session_state: st.session_state.lang = "cn"
def t(cn_text, en_text): return cn_text if st.session_state.lang == "cn" else en_text

col_map = {
    '商品名称': 'Product', '颜色': 'Variant', '进价成本': 'Cost', '售卖价格': 'Price',
    '应收到数量': 'Expected', '展示数量': 'Display', '货柜数量': 'Cabinet', '储物间数量': 'Storage', 
    '坏货数量': 'Damaged', '已售出数量': 'Total Sold', '总库存': 'Total Stock', '期间售出': 'Period Sales',
    '订单号': 'Order ID', '日期': 'Date', '收银员': 'Cashier', '销售数量': 'Qty', '成交单价': 'Unit Price', 
    '总营业额': 'Total Amount', '小计': 'Subtotal', '有效客流': 'Traffic',
    '员工姓名': 'Staff Name', '职位': 'Role', '时薪': 'Hourly Wage', '状态': 'Status',
    '创建日期': 'Create Date', '客户名称': 'Client', '采购数量': 'Purchase Qty', 'B2B单价': 'B2B Price',
    '总计应收': 'Total Recv.', '已收定金': 'Deposit', '待收尾款': 'Balance', '约定交期': 'Deadline', '订单状态': 'Order Status', '备注': 'Notes',
    '记录日期': 'Log Date', '操作类型': 'Operation', '变动数量': 'Change Qty', '库位详情': 'Location Det.',
    '开始时间': 'Start Time', '结束时间': 'End Time', '工作时长': 'Hours', '核算薪资': 'Est. Wage'
}

val_map_cn_to_en = {
    "黑": "Black", "金缮": "Kintsugi", "墨金": "Ink Gold", "银霜": "Silver", "黑玉": "Black Jade",
    "陨星黑": "Meteorite Black", "陨星": "Meteorite", "天蓝": "Sky Blue", 
    "金色": "Gold", "蓝色": "Blue", "灰色": "Grey", "银色": "Silver", "黑色": "Black", "默认": "Default", "多件混装": "Mixed Combo",
    "粉色": "Pink", "绿色": "Green", "紫色": "Purple", "枫叶红": "Maple Red",
    "口红杯": "Lipstick Cup", "咖啡吸管杯 480ml": "Coffee Cup With Straw 480 ML", "臻享 焖茶壶": "Brew Bottle", "冲锋壶680ML": "Canteen Bottle 680ML",
    "焖茶杯": "Brew Bottle", "纯钛酒壶": "Pure Ti Wine Flask", "直滤杯": "Flat Bottom", "冲锋壶": "Canteen",
    "咖啡杯": "Coffee Cup With Straw", "口袋杯": "Pocket Cup", "筷子": "Chopstick", "保温壶": "Thermal Flask",
    "托盘": "Tray", "盘子": "Plate", "叶碟": "Leaf Plate", "随心杯": "Easy Cup", "主人杯": "Host Cup",
    "迷你杯": "Mini Cup", "钛艺T杯": "Ti Artisan Bottle", "圆融杯": "Round cup",
    "钛杯": "Titanium Cup", "常规水杯": "Standard Cup", "低价配件": "Accessories", "T杯": "T-Cup", "钛碗": "Titanium Bowl",
    "在职": "Active", "离职": "Resigned", "店长": "Manager", "全职店员": "Full-time", "兼职店员": "Part-time", "实习生": "Intern", "合作厂商": "Supplier", "其他": "Other",
    "意向/沟通中": "In Communication", "已付定金/备货中": "Deposit Paid", "已发货/待结尾款": "Shipped/Pending", "✅ 订单已完成": "✅ Completed",
    "入库": "Inbound", "调拨": "Transfer", "盘盈": "Surplus (+)", "盘亏": "Shortage (-)", "初始建档": "Initial Setup"
}
val_map_en_to_cn = {v: k for k, v in val_map_cn_to_en.items()}

def t_val(val, to_lang):
    if pd.isna(val): return ""
    vs = str(val).strip()
    return val_map_cn_to_en.get(vs, vs) if to_lang == 'en' else val_map_en_to_cn.get(vs, vs)

def translate_series(series):
    s = series.fillna('').astype(str)
    return s.map(lambda x: val_map_cn_to_en.get(x.strip(), x.strip())) if st.session_state.lang == 'en' else s

# ================= 🚀 数据定义与初始化 =================
STOCK_SHEET, SALES_SHEET, EMP_SHEET = "Stock", "Sales", "Employee"
ATT_SHEET, B2B_SHEET, FEEDBACK_SHEET = "Attendance", "B2B_Orders", "Feedback"
RESTOCK_SHEET, TRAFFIC_SHEET, CAMP_SHEET = "Restock_Log", "Traffic_Log", "Campaigns"

STOCK_COLS = ['商品名称', '颜色', '进价成本', '售卖价格', '应收到数量', '展示数量', '货柜数量', '储物间数量', '坏货数量', '已售出数量', '总库存']
SALES_COLS = ['订单号', '日期', '收银员', '商品名称', '颜色', '销售数量', '成交单价', '总营业额']
EMP_COLS = ['员工姓名', '职位', '时薪', '联系方式', '入职日期', '登录密码', '状态']
ATT_COLS = ['员工姓名', '日期', '开始时间', '结束时间', '工作时长', '核算薪资']
B2B_COLS = ['创建日期', '客户名称', '商品名称', '颜色', '采购数量', 'B2B单价', '总计应收', '货物成本', '物流成本', '关税', '已收定金', '待收尾款', '约定交期', '订单状态', '备注']
FEEDBACK_COLS = ['反馈日期', '商品名称', '客户画像', '反馈类型', '详细原话', '跟进状态']
RESTOCK_COLS = ['记录日期', '操作类型', '商品名称', '颜色', '变动数量', '库位详情', '单件成本', '备注']
TRAFFIC_COLS = ['日期', '有效客流']
CAMP_COLS = ['档期名称', '开始日期', '结束日期']

all_sht = [STOCK_SHEET, SALES_SHEET, EMP_SHEET, ATT_SHEET, B2B_SHEET, FEEDBACK_SHEET, RESTOCK_SHEET, TRAFFIC_SHEET, CAMP_SHEET]
if "sheet_versions" not in st.session_state: st.session_state.sheet_versions = {s: 0 for s in all_sht}
if "pos_cart" not in st.session_state: st.session_state.pos_cart = []

@st.cache_data(ttl=300, show_spinner=False)
def load_raw_data(sheet_name, version):
    try:
        recs = sh.worksheet(sheet_name).get_all_records()
        return pd.DataFrame(recs) if recs else pd.DataFrame()
    except Exception: return pd.DataFrame()

def load_data(sheet_name, columns):
    df = load_raw_data(sheet_name, st.session_state.sheet_versions.get(sheet_name, 0))
    if df.empty: df = pd.DataFrame(columns=columns)
    for c in columns:
        if c not in df.columns: df[c] = "" 
    return df[columns]

def save_data(df, sheet_name):
    try: ws = sh.worksheet(sheet_name)
    except WorksheetNotFound: ws = sh.add_worksheet(title=sheet_name, rows="1000", cols="20")
    ws.clear() 
    df_s = df.fillna("").astype(str)
    ws.update(values=[df_s.columns.values.tolist()] + df_s.values.tolist(), range_name='A1')
    st.session_state.sheet_versions[sheet_name] = st.session_state.sheet_versions.get(sheet_name, 0) + 1

def clean_date_col(df, col_name):
    if not df.empty and col_name in df.columns: df[col_name] = pd.to_datetime(df[col_name], errors='coerce').dt.strftime('%Y/%m/%d').fillna('')
    return df

def load_safe_sales():
    df = clean_date_col(load_data(SALES_SHEET, SALES_COLS), '日期')
    if not df.empty:
        df['订单号'] = df['订单号'].fillna('').astype(str).replace(['0','','nan'], '历史单')
        df['收银员'] = df['收银员'].fillna('').astype(str).replace(['0','','nan'], '店长/历史') if '收银员' in df.columns else '店长/历史'
    return df

def load_safe_emp():
    df = clean_date_col(load_data(EMP_SHEET, EMP_COLS), '入职日期') 
    if not df.empty:
        df['状态'] = df['状态'].fillna('').astype(str).replace(['0','','nan'], '在职')
        df['登录密码'] = df['登录密码'].fillna('').astype(str).replace(['0','nan'], '')
    return df

def JIT_fetch(sheets_to_fetch):
    st.cache_data.clear() 
    r = {}
    if STOCK_SHEET in sheets_to_fetch: r[STOCK_SHEET] = load_data(STOCK_SHEET, STOCK_COLS)
    if SALES_SHEET in sheets_to_fetch: r[SALES_SHEET] = load_safe_sales()
    if RESTOCK_SHEET in sheets_to_fetch: r[RESTOCK_SHEET] = clean_date_col(load_data(RESTOCK_SHEET, RESTOCK_COLS), '记录日期')
    if B2B_SHEET in sheets_to_fetch: r[B2B_SHEET] = clean_date_col(clean_date_col(load_data(B2B_SHEET, B2B_COLS), '创建日期'), '约定交期')
    if FEEDBACK_SHEET in sheets_to_fetch: r[FEEDBACK_SHEET] = clean_date_col(load_data(FEEDBACK_SHEET, FEEDBACK_COLS), '反馈日期')
    if EMP_SHEET in sheets_to_fetch: r[EMP_SHEET] = load_safe_emp()
    if ATT_SHEET in sheets_to_fetch: r[ATT_SHEET] = clean_date_col(load_data(ATT_SHEET, ATT_COLS), '日期')
    if TRAFFIC_SHEET in sheets_to_fetch: r[TRAFFIC_SHEET] = clean_date_col(load_data(TRAFFIC_SHEET, TRAFFIC_COLS), '日期')
    return r

@st.cache_data(show_spinner=False)
def convert_df_to_csv(df): return df.to_csv(index=False).encode('utf-8-sig')

df_stock = load_data(STOCK_SHEET, STOCK_COLS)
df_sales = load_safe_sales()
df_employee = load_safe_emp()
df_attendance = clean_date_col(load_data(ATT_SHEET, ATT_COLS), '日期') 
df_b2b = clean_date_col(clean_date_col(load_data(B2B_SHEET, B2B_COLS), '创建日期'), '约定交期')
df_feedback = clean_date_col(load_data(FEEDBACK_SHEET, FEEDBACK_COLS), '反馈日期')
df_restock = clean_date_col(load_data(RESTOCK_SHEET, RESTOCK_COLS), '记录日期')
df_traffic = clean_date_col(load_data(TRAFFIC_SHEET, TRAFFIC_COLS), '日期')
df_camp = clean_date_col(clean_date_col(load_data(CAMP_SHEET, CAMP_COLS), '开始日期'), '结束日期')

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

manager_password = "taka888"

# 🚀 门禁与全局档期
if "role" not in st.session_state:
    q_role, q_user = st.query_params.get("role"), st.query_params.get("user")
    if q_role == "admin": st.session_state.role, st.session_state.current_user = "admin", "店长"
    elif q_role in ["employee", "supplier"] and q_user: st.session_state.role, st.session_state.current_user = q_role, q_user
    else: st.session_state.role = st.session_state.current_user = None

if "camp_start" not in st.session_state: st.session_state.camp_start = datetime(2026, 3, 26).date()
if "camp_end" not in st.session_state: st.session_state.camp_end = datetime.now().date()
if "camp_name" not in st.session_state: st.session_state.camp_name = "默认全局"

# ================= 🚀 侧边栏 =================
with st.sidebar:
    st.header(t("🔐 系统门禁", "🔐 System Access"))
    if st.session_state.role is not None:
        emoji = "👑" if st.session_state.role == "admin" else ("🏭" if st.session_state.role == "supplier" else "🧑‍💼")
        st.success(t(f"{emoji} 欢迎回来：{st.session_state.current_user}", f"{emoji} Welcome: {st.session_state.current_user}"))
        if st.button(t("🚪 退出系统", "🚪 Logout"), use_container_width=True):
            st.session_state.role = st.session_state.current_user = None
            st.query_params.clear(); st.rerun()
            
        if st.session_state.role == "admin":
            st.divider()
            st.header("🎯 全局档期基准台")
            opts = df_camp['档期名称'].dropna().unique().tolist() if not df_camp.empty else []
            def on_c():
                sel = st.session_state.camp_selector
                if sel != "手动自定义区间" and not df_camp.empty:
                    row = df_camp[df_camp['档期名称'] == sel].iloc[0]
                    try:
                        c_start, c_end = pd.to_datetime(row['开始日期']).date(), pd.to_datetime(row['结束日期']).date()
                        st.session_state.camp_start, st.session_state.camp_end, st.session_state.camp_name = c_start, c_end, sel
                    except: pass
                else: st.session_state.camp_name = "手动自定义区间"
            st.selectbox("📌 选择基准档期", ["手动自定义区间"] + opts, key="camp_selector", on_change=on_c)
            st.write(f"**当前基准区间:** `{st.session_state.camp_start}` 至 `{st.session_state.camp_end}`")
                
            with st.expander("⚙️ 管理/自建档期名录", expanded=False):
                v_camp = df_camp.copy()
                if v_camp.empty: v_camp = pd.DataFrame(columns=CAMP_COLS)
                ed_camp = st.data_editor(v_camp, num_rows="dynamic", use_container_width=True)
                if st.button("💾 保存档期名录", type="primary", use_container_width=True):
                    ed_camp['开始日期'] = pd.to_datetime(ed_camp['开始日期'], errors='coerce').dt.strftime('%Y/%m/%d').fillna('')
                    ed_camp['结束日期'] = pd.to_datetime(ed_camp['结束日期'], errors='coerce').dt.strftime('%Y/%m/%d').fillna('')
                    save_data(ed_camp[ed_camp['档期名称'].fillna('').astype(str).str.strip() != ''], CAMP_SHEET)
                    st.success("✅ 更新成功！"); st.rerun()
            
            st.divider()
            st.header("🛠️ 核心管理")
            with st.expander("➕ 新增产品建档 (Add SKU)"):
                with st.form("new_sku"):
                    n_name, n_color = st.text_input("产品名称"), st.text_input("颜色")
                    c1, c2, c3 = st.columns(3)
                    n_cost, n_price, n_expect = c1.number_input("进价", format="%.2f"), c2.number_input("售价", format="%.2f"), c3.number_input("应收")
                    i1, i2, i3, i4 = st.columns(4)
                    n_disp, n_shelf, n_stor, n_dmg = i1.number_input("展示"), i2.number_input("货柜"), i3.number_input("储物"), i4.number_input("坏货")
                    if st.form_submit_button("确认建档") and n_name and n_color:
                        f = JIT_fetch([STOCK_SHEET, RESTOCK_SHEET]); ls, lr = f[STOCK_SHEET], f[RESTOCK_SHEET]
                        tot = n_disp + n_shelf + n_stor 
                        nr = pd.DataFrame([[n_name, n_color, n_cost, n_price, n_expect, n_disp, n_shelf, n_stor, n_dmg, 0, tot]], columns=STOCK_COLS)
                        ls = pd.concat([ls, nr], ignore_index=True)
                        if tot > 0 or n_dmg > 0:
                            nl = pd.DataFrame([[datetime.now().strftime("%Y/%m/%d"), "初始建档", n_name, n_color, tot+n_dmg, "多库位", n_cost, "系统建档"]], columns=RESTOCK_COLS)
                            lr = pd.concat([nl, lr], ignore_index=True); save_data(lr, RESTOCK_SHEET)
                        save_data(ls, STOCK_SHEET); st.success("✅ 建档成功！"); st.rerun()
    else:
        l_type = st.radio(t("请选择您的身份", "Select Role"), [t("🧑‍💼 店员/厂商", "🧑‍💼 Staff/Supplier"), t("👑 店长", "👑 Admin")], horizontal=True)
        if l_type == t("👑 店长", "👑 Admin"):
            pwd = st.text_input(t("输入授权密码", "Admin Password"), type="password")
            if st.button(t("🔓 登录后台", "🔓 Login"), use_container_width=True):
                if pwd == manager_password: st.session_state.role, st.session_state.current_user = "admin", "店长"; st.rerun()
                else: st.error(t("❌ 密码错误！", "❌ Incorrect Password!"))
        else:
            if df_employee.empty: st.warning(t("⚠️ 无人员档案。", "⚠️ No staff records."))
            else:
                act = df_employee[df_employee['状态'] != '离职']['员工姓名'].tolist()
                if not act: st.warning(t("⚠️ 无在职人员。", "⚠️ No active staff."))
                else:
                    e_sel = st.selectbox(t("选择您的名字", "Select Name"), act)
                    e_row = df_employee[df_employee['员工姓名'] == e_sel].iloc[0]
                    e_pwd = str(e_row['登录密码']).strip()
                    r_assign = "supplier" if str(e_row.get('职位', '')).strip() == '合作厂商' else "employee"
                    if e_pwd == "":
                        st.info(t("🌟 首次登录请设置 PIN 码。", "🌟 First time login, set PIN."))
                        n_pwd = st.text_input(t("设置登录密码", "Set PIN"), type="password")
                        if st.button(t("💾 保存并进入", "💾 Save & Login"), use_container_width=True) and n_pwd.strip():
                            fe = JIT_fetch([EMP_SHEET])[EMP_SHEET]
                            fe.at[fe[fe['员工姓名'] == e_sel].index[0], '登录密码'] = n_pwd
                            save_data(fe, EMP_SHEET)
                            st.session_state.role, st.session_state.current_user = r_assign, e_sel; st.rerun()
                    else:
                        inp = st.text_input(t("输入您的 PIN 码", "Enter PIN"), type="password")
                        if st.button(t("🔑 打卡/登录", "🔑 Login"), use_container_width=True):
                            if inp == e_pwd: st.session_state.role, st.session_state.current_user = r_assign, e_sel; st.rerun()
                            else: st.error(t("❌ 密码不匹配！", "❌ Incorrect PIN!"))

if st.session_state.role is None:
    c_t, c_l = st.columns([8, 2])
    with c_t: st.title(t("🏙️ Takashimaya 零售管理系统", "🏙️ Takashimaya Retail System"))
    with c_l:
        l_c = st.radio("🌐 Language", ["中文", "English"], index=0 if st.session_state.lang == 'cn' else 1, horizontal=True)
        if (l_c == "中文" and st.session_state.lang != "cn") or (l_c == "English" and st.session_state.lang != "en"):
            st.session_state.lang = 'cn' if l_c == "中文" else 'en'; st.rerun()
    st.info(t("👈 请在左侧选择您的身份并完成登录。", "👈 Please select your role on the left menu to login."))
    st.stop()  

# ================= 🚀 主界面 =================
c_t, c_l = st.columns([8, 2])
with c_t: st.title(t("🏙️ Takashimaya 零售管理系统 (云端同步版)", "🏙️ Takashimaya Retail System (Cloud Sync)"))
with c_l:
    l_c = st.radio("🌐 Language", ["中文", "English"], index=0 if st.session_state.lang == 'cn' else 1, horizontal=True)
    if (l_c == "中文" and st.session_state.lang != "cn") or (l_c == "English" and st.session_state.lang != "en"):
        st.session_state.lang = 'cn' if l_c == "中文" else 'en'; st.rerun()

q = st.text_input(t("🔍 快速筛选 (全局搜索)...", "🔍 Quick Search..."), placeholder=t("搜商品/单号/客户...", "Search items/orders/customers..."))
def get_f(df, q):
    if q and not df.empty:
        m = pd.Series(False, index=df.index); q_cn = t_val(q, 'cn')
        for c in df.columns: m = m | df[c].fillna('').astype(str).str.contains(q, case=False, regex=False) | df[c].fillna('').astype(str).str.contains(q_cn, case=False, regex=False)
        return df[m]
    return df

is_admin, is_supplier, is_employee = st.session_state.role == "admin", st.session_state.role == "supplier", st.session_state.role == "employee"

if is_admin: t1, t2, t3, t4, t5, t6, t7, t8 = st.tabs([t("📊 库存", "📊 Inventory"), t("💰 销售", "💰 Sales"), t("📈 毛利", "📈 Margin"), t("👥 考勤", "👥 Staff"), t("💎 净利润", "💎 Net Profit"), t("🤝 B2B订单", "🤝 B2B"), t("🗣️ 客户反馈", "🗣️ Feedback"), t("🧠 战略(BI)", "🧠 BI")])
elif is_supplier: t1, t2, t3, t4 = st.tabs([t("📊 实时库存快照", "📊 Inventory Snapshot"), t("💰 销售报表对账", "💰 Sales Report"), t("📦 进货对账 (ERP流水)", "📦 Inbound Records"), t("🤝 B2B订单对账", "🤝 B2B Orders")])
else: t1, t2, t3 = st.tabs([t("📊 实时库存查询", "📊 Inventory Snapshot"), t("🛒 智能POS收银台", "🛒 Smart POS"), t("⏰ 考勤打卡", "⏰ Timeclock")])


# =========================================================================================
# ================================== 🚀 Admin (店长) 面板 ==================================
# =========================================================================================
if is_admin:
    with t1:
        f_opts_stk = df_stock.copy()
        stock_list_labels = []
        if not f_opts_stk.empty:
            f_opts_stk['dn'] = translate_series(f_opts_stk['商品名称']).fillna('').astype(str)
            f_opts_stk['dc'] = translate_series(f_opts_stk['颜色']).fillna('').astype(str)
            f_opts_stk['label'] = f_opts_stk['dn'] + " (" + f_opts_stk['dc'] + ")"
            stock_list_labels = f_opts_stk['label'].tolist()
            
        st.subheader("📦 专业 ERP 库存与货位管家")
        t1_a, t1_b, t1_c = st.tabs(["📥 1. 补货入库 (Restock)", "🔄 2. 货位调拨 (Transfer)", "⚖️ 3. 盘点平账 (Adjust)"])
        with t1_a:
            with st.form("form_restock"):
                c1, c2, c3 = st.columns(3)
                r_sku = c1.selectbox("选择到货商品", stock_list_labels) if stock_list_labels else c1.selectbox("选择到货商品", ["请先在侧边栏新增商品"])
                r_date, r_loc = c2.date_input("入库日期", value=datetime.now()), c3.selectbox("卸货存放至", ["储物间数量", "货柜数量", "展示数量"])
                c4, c5, c6 = st.columns(3)
                r_qty, r_cost, r_note = c4.number_input("入库数量", min_value=1, step=1, value=50), c5.number_input("进价 ($)", value=0.0, format="%.2f"), c6.text_input("备注单号")
                if st.form_submit_button("✅ 确认入库", type="primary", use_container_width=True) and stock_list_labels:
                    f = JIT_fetch([STOCK_SHEET, RESTOCK_SHEET]); ls, lr = f[STOCK_SHEET], f[RESTOCK_SHEET]
                    dn, dc = r_sku.rsplit(" (", 1); rn, rc = t_val(dn, 'cn'), t_val(dc.replace(")", ""), 'cn')
                    idx = ls[(ls['商品名称'].astype(str).str.strip() == str(rn).strip()) & (ls['颜色'].astype(str).str.strip() == str(rc).strip())].index[0]
                    ls.at[idx, r_loc] = int(pd.to_numeric(ls.at[idx, r_loc], errors='coerce') or 0) + r_qty
                    ls.at[idx, '总库存'] = sum([int(pd.to_numeric(ls.at[idx, c], errors='coerce') or 0) for c in ['展示数量', '货柜数量', '储物间数量']])
                    if r_cost > 0: ls.at[idx, '进价成本'] = r_cost 
                    nl = pd.DataFrame([[r_date.strftime("%Y/%m/%d"), "入库", rn, rc, r_qty, f"存入: {r_loc.replace('数量','')}", r_cost, r_note]], columns=RESTOCK_COLS)
                    save_data(ls, STOCK_SHEET); save_data(pd.concat([nl, lr], ignore_index=True), RESTOCK_SHEET); st.success(f"🎉 补货成功！"); st.rerun()

        with t1_b:
            with st.form("form_transfer"):
                c1, c2, c3, c4 = st.columns(4)
                t_sku = c1.selectbox("选择调拨商品", stock_list_labels, key="t_sku") if stock_list_labels else c1.selectbox("选择", ["空"])
                t_src, t_dst, t_qty = c2.selectbox("From", ["储物间数量", "货柜数量", "展示数量"]), c3.selectbox("To", ["货柜数量", "展示数量", "储物间数量"]), c4.number_input("Qty", min_value=1, step=1, value=10)
                if st.form_submit_button("🔄 确认移库", type="primary", use_container_width=True) and stock_list_labels and t_src != t_dst:
                    f = JIT_fetch([STOCK_SHEET, RESTOCK_SHEET]); ls, lr = f[STOCK_SHEET], f[RESTOCK_SHEET]
                    dn, dc = t_sku.rsplit(" (", 1); rn, rc = t_val(dn, 'cn'), t_val(dc.replace(")", ""), 'cn')
                    idx = ls[(ls['商品名称'].astype(str).str.strip() == str(rn).strip()) & (ls['颜色'].astype(str).str.strip() == str(rc).strip())].index[0]
                    curr_q = int(pd.to_numeric(ls.at[idx, t_src], errors='coerce') or 0)
                    if curr_q < t_qty: st.error(f"⚠️ 库存不足！")
                    else:
                        ls.at[idx, t_src] = curr_q - t_qty
                        ls.at[idx, t_dst] = int(pd.to_numeric(ls.at[idx, t_dst], errors='coerce') or 0) + t_qty
                        nl = pd.DataFrame([[datetime.now().strftime("%Y/%m/%d"), "调拨", rn, rc, t_qty, f"{t_src.replace('数量','')} -> {t_dst.replace('数量','')}", 0, "内部整理"]], columns=RESTOCK_COLS)
                        save_data(ls, STOCK_SHEET); save_data(pd.concat([nl, lr], ignore_index=True), RESTOCK_SHEET); st.success("✅ 移库成功！"); st.rerun()

        with t1_c:
            with st.form("form_adjust"):
                c1, c2, c3, c4 = st.columns(4)
                a_sku = c1.selectbox("需平账商品", stock_list_labels, key="a_sku") if stock_list_labels else c1.selectbox("选择", ["空"])
                a_loc, a_diff, a_note = c2.selectbox("发生差异的库位", ["货柜数量", "展示数量", "储物间数量", "坏货数量"]), c3.number_input("差异 (+为盘盈, -为盘亏)", value=-1, step=1), c4.text_input("平账原因")
                if st.form_submit_button("⚖️ 确认记账", type="primary", use_container_width=True) and stock_list_labels and a_note.strip() != "" and a_diff != 0:
                    f = JIT_fetch([STOCK_SHEET, RESTOCK_SHEET]); ls, lr = f[STOCK_SHEET], f[RESTOCK_SHEET]
                    dn, dc = a_sku.rsplit(" (", 1); rn, rc = t_val(dn, 'cn'), t_val(dc.replace(")", ""), 'cn')
                    idx = ls[(ls['商品名称'].astype(str).str.strip() == str(rn).strip()) & (ls['颜色'].astype(str).str.strip() == str(rc).strip())].index[0]
                    ls.at[idx, a_loc] = int(pd.to_numeric(ls.at[idx, a_loc], errors='coerce') or 0) + a_diff
                    if a_loc != '坏货数量': ls.at[idx, '总库存'] = sum([int(pd.to_numeric(ls.at[idx, c], errors='coerce') or 0) for c in ['展示数量', '货柜数量', '储物间数量']])
                    adj_t = "盘盈" if a_diff > 0 else "盘亏"
                    nl = pd.DataFrame([[datetime.now().strftime("%Y/%m/%d"), adj_t, rn, rc, a_diff, f"库位: {a_loc.replace('数量','')}", 0, a_note]], columns=RESTOCK_COLS)
                    save_data(ls, STOCK_SHEET); save_data(pd.concat([nl, lr], ignore_index=True), RESTOCK_SHEET); st.success(f"✅ 平账成功！"); st.rerun()
        st.divider()

        st.subheader(t(f"📊 实时库存与期间动销快照", f"📊 Real-time Inventory & Sales Snapshot"))
        dr = st.date_input(t("⏳ 选择要分析的销售区间：", "⏳ Select Date Range:"), value=[st.session_state.camp_start, st.session_state.camp_end], key="t1_dr")
        t1_s, t1_e = (dr[0], dr[1]) if len(dr) == 2 else (dr[0], dr[0])
            
        f_stk = get_f(df_stock, q)
        if not f_stk.empty:
            v_df = f_stk.copy()
            ps = pd.DataFrame()
            if not df_sales.empty:
                ds1 = df_sales.copy(); ds1['dt'] = pd.to_datetime(ds1['日期'], errors='coerce')
                fs1 = ds1[(ds1['dt'] >= pd.Timestamp(t1_s)) & (ds1['dt'] <= pd.Timestamp(t1_e))]
                if not fs1.empty:
                    fs1['销售数量'] = pd.to_numeric(fs1['销售数量'], errors='coerce').fillna(0)
                    ps = fs1.groupby(['商品名称', '颜色'])['销售数量'].sum().reset_index().rename(columns={'销售数量': '期间售出'})
            
            if not ps.empty: v_df = v_df.merge(ps, on=['商品名称', '颜色'], how='left')
            else: v_df['期间售出'] = 0
                
            v_df['期间售出'] = v_df['期间售出'].fillna(0).astype(int)
            for c in ['应收到数量', '已售出数量', '总库存', '展示数量', '货柜数量', '储物间数量', '坏货数量', '期间售出']: 
                if c in v_df.columns: v_df[c] = pd.to_numeric(v_df[c], errors='coerce').fillna(0).astype(int)
            v_df['进价成本'], v_df['售卖价格'] = pd.to_numeric(v_df['进价成本'], errors='coerce').fillna(0.0), pd.to_numeric(v_df['售卖价格'], errors='coerce').fillna(0.0)
            v_df['单品毛利率'] = v_df.apply(lambda r: f"{((r['售卖价格'] - r['进价成本']) / r['售卖价格'] * 100):.1f}%" if r['售卖价格'] > 0 else "0.0%", axis=1)
            v_df.insert(0, "选择", False)
            v_df['商品名称'], v_df['颜色'] = translate_series(v_df['商品名称']), translate_series(v_df['颜色'])
            
            d_cols = ['选择', '商品名称', '颜色', '期间售出', '已售出数量', '总库存', '展示数量', '货柜数量', '储物间数量', '坏货数量', '售卖价格', '进价成本', '单品毛利率']
            df_disp = v_df[d_cols].copy()
            if st.session_state.lang == 'en': df_disp.rename(columns=col_map, inplace=True)
            p_c, c_c, stk_c = ('Price', 'Cost', 'Total Stock') if st.session_state.lang == 'en' else ('售卖价格', '进价成本', '总库存')
            
            def hl(row):
                try:
                    if int(row[stk_c]) <= 2: return ['background-color: #ffe6e6; color: #cc0000; font-weight: bold;'] * len(row)
                except: pass
                return [''] * len(row)
            
            sel_col_name = "Sel" if st.session_state.lang == 'en' else "选择"
            d_disable = [c for c in df_disp.columns if c not in ["选择", "Sel"]]
            
            sd = df_disp.style.format({c_c: '${:.2f}', p_c: '${:.2f}'}).apply(hl, axis=1)
            ed = st.data_editor(sd, column_config={sel_col_name: st.column_config.CheckboxColumn("Sel" if st.session_state.lang == 'en' else "选择", default=False)}, disabled=d_disable, use_container_width=True, hide_index=True, key=f"s_ed_{st.session_state.stock_reset_key}")
            sel = ed[ed[sel_col_name] == True] if sel_col_name in ed.columns else pd.DataFrame()

            if len(sel) == 1:
                st.markdown("### ⚙️ SKU 档案修改机")
                o_n = str(sel.iloc[0]['Product' if st.session_state.lang == 'en' else '商品名称'])
                o_c = str(sel.iloc[0]['Variant' if st.session_state.lang == 'en' else '颜色'])
                r_o_n, r_o_c = t_val(o_n, 'cn'), t_val(o_c, 'cn')
                rcst, rprc = str(sel.iloc[0][c_c]).replace('$','').replace(',',''), str(sel.iloc[0][p_c]).replace('$','').replace(',','')
                
                with st.form("edit_base_info"):
                    ec1, ec2 = st.columns(2)
                    e_n, e_c = ec1.text_input("Name (CN)", value=r_o_n), ec2.text_input("Color (CN)", value=r_o_c)
                    ec4, ec5 = st.columns(2)
                    e_cost, e_price = ec4.number_input("Cost ($)", value=float(rcst) if rcst else 0.0), ec5.number_input("Price ($)", value=float(rprc) if rprc else 0.0)
                    if st.form_submit_button("💾 Save Changes", type="primary"):
                        f = JIT_fetch([STOCK_SHEET, SALES_SHEET, B2B_SHEET, RESTOCK_SHEET])
                        ls, lsal, lb, lr = f[STOCK_SHEET], f[SALES_SHEET], f[B2B_SHEET], f[RESTOCK_SHEET]
                        
                        idx_m = ls[(ls['商品名称'].astype(str).str.strip() == str(r_o_n).strip()) & (ls['颜色'].astype(str).str.strip() == str(r_o_c).strip())].index
                        if not idx_m.empty:
                            idx = idx_m[0]
                            ls.loc[idx, ['商品名称', '颜色', '进价成本', '售卖价格']] = [e_n, e_c, e_cost, e_price]
                            if e_n != r_o_n or e_c != r_o_c:
                                if not lsal.empty: lsal.loc[(lsal['商品名称'].astype(str).str.strip() == str(r_o_n).strip()) & (lsal['颜色'].astype(str).str.strip() == str(r_o_c).strip()), ['商品名称', '颜色']] = [e_n, e_c]
                                if not lr.empty: lr.loc[(lr['商品名称'].astype(str).str.strip() == str(r_o_n).strip()) & (lr['颜色'].astype(str).str.strip() == str(r_o_c).strip()), ['商品名称', '颜色']] = [e_n, e_c]
                                if not lb.empty: lb.loc[(lb['商品名称'].astype(str).str.strip() == str(r_o_n).strip()) & (lb['颜色'].astype(str).str.strip() == str(r_o_c).strip()), ['商品名称', '颜色']] = [e_n, e_c]
                                save_data(lsal, SALES_SHEET); save_data(lr, RESTOCK_SHEET); save_data(lb, B2B_SHEET)
                            save_data(ls, STOCK_SHEET); st.session_state.stock_reset_key += 1; st.success(f"✅ Updated!"); st.rerun()

                if not sel.empty:
                    c_b1, c_b2, _ = st.columns([1.5, 1.5, 4])
                    if c_b1.button("🗑️ 彻底删档选中 (Delete)", type="primary"):
                        fs_s = JIT_fetch([STOCK_SHEET])[STOCK_SHEET]
                        for _, r in sel.iterrows(): 
                            d_n, d_c = t_val(r['Product' if st.session_state.lang == 'en' else '商品名称'], 'cn'), t_val(r['Variant' if st.session_state.lang == 'en' else '颜色'], 'cn')
                            fs_s = fs_s[~((fs_s['商品名称'].astype(str).str.strip() == str(d_n).strip()) & (fs_s['颜色'].astype(str).str.strip() == str(d_c).strip()))]
                        save_data(fs_s, STOCK_SHEET); st.session_state.stock_reset_key += 1; st.rerun()
                    c_b2.button("🔄 取消选中", on_click=clear_stock)
            
            with st.expander("📜 ERP底单：查看所有出入库流水账", expanded=False):
                drd = get_f(df_restock, q).copy()
                drd['操作类型'], drd['商品名称'], drd['颜色'] = translate_series(drd['操作类型']), translate_series(drd['商品名称']), translate_series(drd['颜色'])
                if st.session_state.lang == 'en': drd.rename(columns=col_map, inplace=True)
                st.dataframe(drd, use_container_width=True)

    with t2:
        st.subheader("🛒 智能 POS 收银台 (多件合并结账)")
        c_l, c_r = st.columns([1.2, 1.5])
        fo = get_f(df_stock, "").copy() 
        if not fo.empty:
            fo['dn'] = translate_series(fo['商品名称']).astype(str)
            fo['dc'] = translate_series(fo['颜色']).astype(str)
            fo['label'] = fo['dn'] + " (" + fo['dc'] + ")" 
            with c_l:
                with st.container(border=True):
                    st.markdown(t("#### 1️⃣ 扫码/点单区", "#### 1️⃣ Scan / Order"))
                    
                    # 🔥 超级秒搜输入框
                    search_kw_admin = st.text_input(t("🔍 键盘输入搜商品 (自动过滤下拉框)", "🔍 Type to search item"), key="pos_search_admin")
                    filtered_opts_admin = fo[fo['label'].str.contains(search_kw_admin, case=False, na=False)] if search_kw_admin else fo
                    
                    if not filtered_opts_admin.empty:
                        s_l = st.selectbox(t("选择商品", "Select Item"), filtered_opts_admin['label'], key="pos_item_admin")
                        row = filtered_opts_admin[filtered_opts_admin['label'] == s_l].iloc[0]
                        bp = float(pd.to_numeric(row['售卖价格'], errors='coerce') or 0)
                        cq, cd = st.columns(2)
                        sq = cq.number_input(t("数量", "Qty"), min_value=1, value=1, step=1, key="pos_qty_admin")
                        d_opts = {"无折扣 (原价)": 1.0, "95折": 0.95, "9折": 0.90, "85折": 0.85, "8折": 0.80, "75折": 0.75, "7折": 0.70, "5折 (半价)": 0.50} if st.session_state.lang == 'cn' else {"No Discount": 1.0, "5% Off": 0.95, "10% Off": 0.90, "15% Off": 0.85, "20% Off": 0.80, "25% Off": 0.75, "30% Off": 0.70, "50% Off": 0.50}
                        sd = cd.selectbox(t("折扣", "Discount"), list(d_opts.keys()), key="pos_disc_admin")
                        sp = st.number_input(t("最终成交单价 ($)", "Final Price ($)"), value=float(bp * d_opts[sd]), format="%.2f", key="pos_final_p_admin")
                        if st.button(t("➕ 加入购物车", "➕ Add to Cart"), use_container_width=True, key="pos_add_admin"):
                            st.session_state.pos_cart.append({"rn": str(row['商品名称']), "rc": str(row['颜色']), "dn": str(row['dn']), "dc": str(row['dc']), "q": sq, "p": sp})
                            st.rerun()

            with c_r:
                with st.container(border=True):
                    st.markdown(t("#### 2️⃣ 当前购物车", "#### 2️⃣ Current Cart"))
                    if not st.session_state.pos_cart: st.info(t("🛒 空空如也。", "🛒 Empty."))
                    else:
                        cdf = pd.DataFrame(st.session_state.pos_cart)
                        df_disp = cdf[['dn', 'dc', 'q', 'p']].copy()
                        df_disp.columns = ['Product', 'Variant', 'Qty', 'Price'] if st.session_state.lang == 'en' else ['商品名称', '颜色', '数量', '单价']
                        uc = 'Price' if st.session_state.lang == 'en' else '单价'
                        st.dataframe(df_disp.style.format({uc: '${:.2f}'}), use_container_width=True, hide_index=True)
                        st.markdown(f"**{t('🛍️ 共计:', '🛍️ Total Qty:')}** `{cdf['q'].sum()}` | **{t('💰 应收:', '💰 Total Pay:')}** ` ${cdf['q'].dot(cdf['p']):.2f}`")
                        cc1, cc2 = st.columns([2, 1])
                        sdt = cc1.date_input(t("交易日期", "Transaction Date"), value=datetime.now(), key="pos_dt_admin")
                        if cc2.button(t("🗑️ 清空", "🗑️ Clear"), use_container_width=True, key="pos_clear_admin"): st.session_state.pos_cart = []; st.rerun()
                        if st.button(t("💳 确认结账 (生成流水)", "💳 Checkout"), type="primary", use_container_width=True, key="pos_co_admin"):
                            f = JIT_fetch([STOCK_SHEET, SALES_SHEET]); ls, lsal = f[STOCK_SHEET], f[SALES_SHEET]
                            oid, odt, usr = "ORD-" + datetime.now().strftime("%Y%m%d-%H%M%S"), sdt.strftime("%Y/%m/%d"), st.session_state.get("current_user", "Unknown")
                            new = []
                            for i in st.session_state.pos_cart:
                                new.append([oid, odt, usr, i['rn'], i['rc'], i['q'], i['p'], i['q'] * i['p']])
                                idx = ls[(ls['商品名称'].astype(str).str.strip() == str(i['rn']).strip()) & (ls['颜色'].astype(str).str.strip() == str(i['rc']).strip())].index
                                if not idx.empty:
                                    ls.at[idx[0], '货柜数量'] = int(pd.to_numeric(ls.at[idx[0], '货柜数量'], errors='coerce') or 0) - i['q']
                                    ls.at[idx[0], '已售出数量'] = int(pd.to_numeric(ls.at[idx[0], '已售出数量'], errors='coerce') or 0) + i['q']
                                    ls.at[idx[0], '总库存'] = sum([int(pd.to_numeric(ls.at[idx[0], c], errors='coerce') or 0) for c in ['展示数量', '货柜数量', '储物间数量']])
                            save_data(ls, STOCK_SHEET); save_data(pd.concat([pd.DataFrame(new, columns=SALES_COLS), lsal], ignore_index=True), SALES_SHEET)
                            st.session_state.pos_cart = []; st.success(t(f"🎉 成功！单号 {oid}", f"🎉 Success! ID: {oid}")); st.rerun()

        st.divider()
        with st.expander(t("🚶‍♂️ 录入/修正每日有效客流", "🚶‍♂️ Daily Traffic Log"), expanded=False):
            with st.form("traffic_form"):
                tc1, tc2 = st.columns(2)
                tr_date, tr_num = tc1.date_input(t("📅 客流日期", "📅 Date"), value=datetime.now()), tc2.number_input(t("👁️ 有效咨询人数", "👁️ Traffic"), min_value=0, step=1, value=0)
                if st.form_submit_button(t("💾 保存客流", "💾 Save"), type="primary", use_container_width=True):
                    ft = JIT_fetch([TRAFFIC_SHEET])[TRAFFIC_SHEET]
                    tds = tr_date.strftime("%Y/%m/%d")
                    idx = ft[ft['日期'].astype(str).str.strip() == tds].index
                    if not idx.empty: ft.at[idx[0], '有效客流'] = tr_num
                    else: ft = pd.concat([pd.DataFrame([[tds, tr_num]], columns=TRAFFIC_COLS), ft], ignore_index=True)
                    save_data(ft, TRAFFIC_SHEET); st.success("✅ Saved!"); st.rerun()

        with st.expander(t("🔄 客户换货处理 (Exchange)", "🔄 Item Exchange"), expanded=False):
            if not fo.empty:
                xc1, xc2 = st.columns(2)
                with xc1:
                    rl = st.selectbox("1. Return Item", fo['label'], key="ex_ret_sku")
                    rr = fo[fo['label'] == rl].iloc[0]
                    rp = st.number_input("2. Return Value ($)", value=float(pd.to_numeric(rr['售卖价格'], errors='coerce') or 0), format="%.2f")
                    rd = st.checkbox(t("⚠️ 退回商品有瑕疵", "⚠️ Damaged"), value=False)
                with xc2:
                    nl = st.selectbox("1. New Item", fo['label'], key="ex_new_sku")
                    nr = fo[fo['label'] == nl].iloc[0]
                    np = st.number_input("2. New Item Price ($)", value=float(pd.to_numeric(nr['售卖价格'], errors='coerce') or 0), format="%.2f")
                c_date, c_diff = st.columns(2)
                with c_date: ex_date = st.date_input("📅 Date", value=datetime.now(), key="ex_date_input")
                with c_diff:
                    diff = np - rp
                    if diff > 0: st.warning(t(f"💰 需补差价：${diff:.2f}", f"💰 Pay: ${diff:.2f}"))
                    elif diff < 0: st.success(t(f"💸 需退差价：${abs(diff):.2f}", f"💸 Refund: ${abs(diff):.2f}"))
                    else: st.info(t("🤝 等价交换", "🤝 Even"))
                if st.button(t("🔄 确认执行换货", "🔄 Confirm Exchange"), type="primary", use_container_width=True):
                    f = JIT_fetch([STOCK_SHEET, SALES_SHEET]); ls, lsal = f[STOCK_SHEET], f[SALES_SHEET]
                    edt, oid, usr = ex_date.strftime("%Y/%m/%d"), "EXC-" + datetime.now().strftime("%Y%m%d-%H%M%S"), st.session_state.get("current_user", "Unknown")
                    rn, rc, nn, nc = str(rr['商品名称']), str(rr['颜色']), str(nr['商品名称']), str(nr['颜色'])
                    
                    ir = ls[(ls['商品名称'].astype(str).str.strip() == rn.strip()) & (ls['颜色'].astype(str).str.strip() == rc.strip())].index[0]
                    sr = pd.DataFrame([[oid, edt, usr, rn, rc, -1, rp, -rp]], columns=SALES_COLS)
                    
                    in_ = ls[(ls['商品名称'].astype(str).str.strip() == nn.strip()) & (ls['颜色'].astype(str).str.strip() == nc.strip())].index[0]
                    sn = pd.DataFrame([[oid, edt, usr, nn, nc, 1, np, np]], columns=SALES_COLS)
                    
                    lsal = pd.concat([sn, sr, lsal], ignore_index=True)
                    if rd: ls.at[ir, '坏货数量'] = int(pd.to_numeric(ls.at[ir, '坏货数量'], errors='coerce') or 0) + 1
                    else: 
                        ls.at[ir, '货柜数量'] = int(pd.to_numeric(ls.at[ir, '货柜数量'], errors='coerce') or 0) + 1
                        ls.at[ir, '总库存'] = sum([int(pd.to_numeric(ls.at[ir, c], errors='coerce') or 0) for c in ['展示数量', '货柜数量', '储物间数量']])
                    ls.at[ir, '已售出数量'] = int(pd.to_numeric(ls.at[ir, '已售出数量'], errors='coerce') or 0) - 1
                    ls.at[in_, '货柜数量'] = int(pd.to_numeric(ls.at[in_, '货柜数量'], errors='coerce') or 0) - 1
                    ls.at[in_, '已售出数量'] = int(pd.to_numeric(ls.at[in_, '已售出数量'], errors='coerce') or 0) + 1
                    ls.at[in_, '总库存'] = sum([int(pd.to_numeric(ls.at[in_, c], errors='coerce') or 0) for c in ['展示数量', '货柜数量', '储物间数量']])
                    save_data(lsal, SALES_SHEET); save_data(ls, STOCK_SHEET); st.success("✅ Done!"); st.rerun()

        st.divider()
        st.markdown("### 📝 销售流水编辑与防飞单机制")
        fsl = get_f(df_sales, q)
        if not fsl.empty:
            fsl_sel = fsl.copy(); fsl_sel.insert(0, "Sel", False)
            fsl_sel['成交单价'] = pd.to_numeric(fsl_sel['成交单价'], errors='coerce').fillna(0.0)
            fsl_sel['总营业额'] = pd.to_numeric(fsl_sel['总营业额'], errors='coerce').fillna(0.0)
            
            fsl_sel['商品名称'] = translate_series(fsl_sel['商品名称'])
            fsl_sel['颜色'] = translate_series(f_sl_sel['颜色'])
            if st.session_state.lang == 'en': fsl_sel.rename(columns=col_map, inplace=True)
            
            u_col = 'Unit Price' if st.session_state.lang == 'en' else '成交单价'
            t_col = 'Total Amount' if st.session_state.lang == 'en' else '总营业额'
            sel_col_name = "Sel" if st.session_state.lang == 'en' else "Sel"
            
            # 🔥 极强防弹：精准解除复选框禁用
            d_disable = [c for c in fsl_sel.columns if c not in ["Sel", "选择"]]
            
            ed = st.data_editor(
                fsl_sel.style.format({u_col: '${:.2f}', t_col: '${:.2f}'}), 
                column_config={"Sel": st.column_config.CheckboxColumn("Sel", default=False)}, 
                disabled=d_disable, 
                use_container_width=True, hide_index=True, 
                key=f"se_{st.session_state.sales_reset_key}"
            )
            
            sel = ed[ed["Sel"] == True] if "Sel" in ed.columns else pd.DataFrame()
            
            if not sel.empty:
                sc1, sc2, _ = st.columns([1.5, 1.5, 4])
                if sc1.button("🔴 批量撤销流水", type="primary"):
                    f = JIT_fetch([STOCK_SHEET, SALES_SHEET]); ls, lsal = f[STOCK_SHEET], f[SALES_SHEET]
                    for _, r in sel.iterrows():
                        real_n = t_val(r['Product' if st.session_state.lang == 'en' else '商品名称'], 'cn')
                        real_c = t_val(r['Variant' if st.session_state.lang == 'en' else '颜色'], 'cn')
                        q_val = int(pd.to_numeric(r['Qty' if st.session_state.lang == 'en' else '销售数量'], errors='coerce') or 0)
                        
                        m = ls[(ls['商品名称'].astype(str).str.strip() == str(real_n).strip()) & (ls['颜色'].astype(str).str.strip() == str(real_c).strip())].index
                        if not m.empty:
                            ls.at[m[0], '货柜数量'] = int(pd.to_numeric(ls.at[m[0], '货柜数量'], errors='coerce') or 0) + q_val
                            ls.at[m[0], '已售出数量'] = int(pd.to_numeric(ls.at[m[0], '已售出数量'], errors='coerce') or 0) - q_val
                            ls.at[m[0], '总库存'] = sum([int(pd.to_numeric(ls.at[m[0], c], errors='coerce') or 0) for c in ['展示数量', '货柜数量', '储物间数量']])
                        
                        o_id = str(r['Order ID' if st.session_state.lang == 'en' else '订单号']).strip()
                        o_dt = str(r['Date' if st.session_state.lang == 'en' else '日期']).strip()
                        
                        # 🔥 数字强制转换再比对，一删一个准！
                        cond = (lsal['订单号'].astype(str).str.strip() == o_id) & \
                               (lsal['商品名称'].astype(str).str.strip() == str(real_n).strip()) & \
                               (lsal['颜色'].astype(str).str.strip() == str(real_c).strip()) & \
                               (pd.to_numeric(lsal['销售数量'], errors='coerce').fillna(0).astype(int) == q_val)
                        lsal = lsal[~cond]
                        
                    save_data(ls, STOCK_SHEET); save_data(lsal, SALES_SHEET); st.session_state.sales_reset_key += 1; st.rerun()
                sc2.button("🔄 取消所有选中", on_click=clear_sales)
                
                # 🔥 单条修改复活
                if len(sel) == 1:
                    st.markdown("### ⚙️ 修改此笔流水 (Edit Log)")
                    r = sel.iloc[0]
                    real_n = t_val(r['Product' if st.session_state.lang == 'en' else '商品名称'], 'cn')
                    real_c = t_val(r['Variant' if st.session_state.lang == 'en' else '颜色'], 'cn')
                    o_id = str(r['Order ID' if st.session_state.lang == 'en' else '订单号']).strip()
                    o_dt = str(r['Date' if st.session_state.lang == 'en' else '日期']).strip()
                    o_qty = int(pd.to_numeric(r['Qty' if st.session_state.lang == 'en' else '销售数量'], errors='coerce') or 0)
                    o_prc = float(pd.to_numeric(r['Unit Price' if st.session_state.lang == 'en' else '成交单价'], errors='coerce') or 0.0)

                    f_opts_stk = df_stock.copy()
                    f_opts_stk['dn'] = translate_series(f_opts_stk['商品名称']).fillna('').astype(str)
                    f_opts_stk['dc'] = translate_series(f_opts_stk['颜色']).fillna('').astype(str)
                    f_opts_stk['label'] = f_opts_stk['dn'] + " (" + f_opts_stk['dc'] + ")"
                    stk_lbls = f_opts_stk['label'].tolist()
                    
                    curr_lbl = f"{t_val(real_n, 'en' if st.session_state.lang == 'en' else 'cn')} ({t_val(real_c, 'en' if st.session_state.lang == 'en' else 'cn')})"
                    if curr_lbl not in stk_lbls: stk_lbls.insert(0, curr_lbl)
                    
                    with st.form("edit_sale_form_admin"):
                        e_c1, e_c2, e_c3, e_c4 = st.columns(4)
                        try: parsed_date = pd.to_datetime(o_dt).date()
                        except: parsed_date = datetime.now().date()
                        
                        e_date = e_c1.date_input("交易日期 Date", value=parsed_date)
                        e_prod = e_c2.selectbox("商品 Product", stk_lbls, index=stk_lbls.index(curr_lbl))
                        e_qty = e_c3.number_input("数量 Qty", value=o_qty, min_value=1)
                        e_price = e_c4.number_input("单价 Price ($)", value=o_prc, format="%.2f")
                        
                        if st.form_submit_button("💾 保存修改 (Save)", type="primary"):
                            fresh = JIT_fetch([STOCK_SHEET, SALES_SHEET])
                            ls, lsal = fresh[STOCK_SHEET], fresh[SALES_SHEET]
                            
                            cond = (lsal['订单号'].astype(str).str.strip() == o_id) & \
                                   (lsal['商品名称'].astype(str).str.strip() == str(real_n).strip()) & \
                                   (lsal['颜色'].astype(str).str.strip() == str(real_c).strip()) & \
                                   (pd.to_numeric(lsal['销售数量'], errors='coerce').fillna(0).astype(int) == o_qty)
                            
                            true_idx = lsal[cond].index
                            if not true_idx.empty:
                                t_idx = true_idx[0]
                                m_old = ls[(ls['商品名称'].astype(str).str.strip() == str(real_n).strip()) & (ls['颜色'].astype(str).str.strip() == str(real_c).strip())].index
                                if not m_old.empty:
                                    ls.at[m_old[0], '货柜数量'] = int(pd.to_numeric(ls.at[m_old[0], '货柜数量'], errors='coerce') or 0) + o_qty
                                    ls.at[m_old[0], '已售出数量'] = int(pd.to_numeric(ls.at[m_old[0], '已售出数量'], errors='coerce') or 0) - o_qty
                                    ls.at[m_old[0], '总库存'] = sum([int(pd.to_numeric(ls.at[m_old[0], col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                                    
                                new_n = t_val(e_prod.rsplit(" (", 1)[0], 'cn')
                                new_c = t_val(e_prod.rsplit(" (", 1)[1].replace(")", ""), 'cn')
                                
                                m_new = ls[(ls['商品名称'].astype(str).str.strip() == str(new_n).strip()) & (ls['颜色'].astype(str).str.strip() == str(new_c).strip())].index
                                if not m_new.empty:
                                    ls.at[m_new[0], '货柜数量'] = int(pd.to_numeric(ls.at[m_new[0], '货柜数量'], errors='coerce') or 0) - e_qty
                                    ls.at[m_new[0], '已售出数量'] = int(pd.to_numeric(ls.at[m_new[0], '已售出数量'], errors='coerce') or 0) + e_qty
                                    ls.at[m_new[0], '总库存'] = sum([int(pd.to_numeric(ls.at[m_new[0], col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                                    
                                lsal.at[t_idx, '日期'] = e_date.strftime("%Y/%m/%d")
                                lsal.at[t_idx, '商品名称'] = new_n
                                lsal.at[t_idx, '颜色'] = new_c
                                lsal.at[t_idx, '销售数量'] = e_qty
                                lsal.at[t_idx, '成交单价'] = e_price
                                lsal.at[t_idx, '总营业额'] = e_qty * e_price
                                
                                save_data(ls, STOCK_SHEET)
                                save_data(lsal, SALES_SHEET)
                                st.session_state.sales_reset_key += 1
                                st.success("✅ 修改成功！"); st.rerun()
                            else: st.error("⚠️ 未在云端找到该流水！可能是已被删除或数量有偏差。")

    with t3:
        st.subheader("📊 财务与客流报表")
        dr = st.date_input("⏳ 分析时间段：", value=[st.session_state.camp_start, st.session_state.camp_end], key="t3_dp")
        t3s, t3e = (dr[0], dr[1]) if len(dr) == 2 else (dr[0], dr[0])
        ds = df_sales.copy(); ds['dt'] = pd.to_datetime(ds['日期'], errors='coerce'); ds = ds.dropna(subset=['dt'])
        if not ds.empty:
            fs = ds[(ds['dt'].dt.date >= t3s) & (ds['dt'].dt.date <= t3e)].copy()
            fs['销售数量'] = pd.to_numeric(fs['销售数量'], errors='coerce').fillna(0)
            fs['总营业额'] = pd.to_numeric(fs['总营业额'], errors='coerce').fillna(0.0)
            dc = df_stock[['商品名称', '颜色', '进价成本']].copy(); dc['进价成本'] = pd.to_numeric(dc['进价成本'], errors='coerce').fillna(0.0)
            fs = fs.merge(dc, on=['商品名称', '颜色'], how='left')
            fs['具体毛利'] = fs['总营业额'] - (fs['销售数量'] * fs['进价成本'])
            fs = get_f(fs, q)
            if not fs.empty:
                tr, ti, tm = fs['总营业额'].sum(), fs['销售数量'].sum(), fs['具体毛利'].sum()
                vo = fs[(~fs['订单号'].str.contains('历史单', na=False)) & (~fs['订单号'].str.contains('EXC-', na=False))]['订单号'].nunique() + len(fs[fs['订单号'].str.contains('历史单', na=False)])
                
                dtf = df_traffic.copy(); dtf['dt'] = pd.to_datetime(dtf['日期'], errors='coerce')
                ftf = dtf[(dtf['dt'].dt.date >= t3s) & (dtf['dt'].dt.date <= t3e)]
                tt = pd.to_numeric(ftf['有效客流'], errors='coerce').fillna(0).sum() if not ftf.empty else 0
                
                cr = (vo / tt * 100) if tt > 0 else 0.0
                acv, upt = (tr / vo if vo > 0 else 0), (ti / vo if vo > 0 else 0)
                
                per = st.radio("维度", ["Daily", "Weekly", "Monthly"], horizontal=True)
                if "Daily" in per: fs['周期'] = fs['dt'].dt.strftime('%Y/%m/%d')
                elif "Weekly" in per: fs['周期'] = (fs['dt'] - pd.to_timedelta(fs['dt'].dt.dayofweek, unit='D')).dt.strftime('Wk %b %d')
                else: fs['周期'] = fs['dt'].dt.strftime('%Y/%m')
                
                sm = fs.groupby(['周期', '商品名称', '颜色']).agg({'销售数量':'sum', '总营业额':'sum', '具体毛利':'sum'}).reset_index()
                dd = (t3e - t3s).days + 1
                
                st.markdown("### 🏬 核心客流漏斗矩阵")
                c1, c2, c3 = st.columns(3)
                c1.metric("👁️ 有效总客流", f"{int(tt)} 人"); c2.metric("💳 交易单数", f"{vo} 单"); c3.metric("🔄 购买转化率", f"{cr:.1f}%")
                st.divider()
                c4, c5, c6 = st.columns(3)
                c4.metric("💰 总营业额", f"${tr:.2f}"); c5.metric("🛒 平均客单价 (ACV)", f"${acv:.2f}"); c6.metric("🛍️ 连带率 (UPT)", f"{upt:.2f}")
                st.divider()
                c7, c8, c9, c10 = st.columns(4)
                c7.metric("具体毛利", f"${tm:.2f}"); c8.metric("总售出件数", f"{int(ti)} 件")
                c9.metric("平均毛利率", f"{(tm/tr*100) if tr>0 else 0:.1f}%"); c10.metric("日均坪效", f"${(tr/dd) if dd>0 else 0:.2f}")
                
                st.divider()
                st.markdown("### 📈 营收与毛利走势")
                st.bar_chart(sm.groupby('周期')[['总营业额', '具体毛利']].sum().sort_index(ascending=True), use_container_width=True)
                
                cl1, cl2 = st.columns([1, 4])
                cl1.download_button("⬇️ 导出报表 (CSV)", convert_df_to_csv(sm), f"Margin_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv", type="primary")
                st.dataframe(sm.sort_values('周期', ascending=False).style.format({'总营业额':"${:.2f}", '具体毛利':"${:.2f}"}), use_container_width=True)

    with t4:
        st.subheader("👥 员工档案与门禁管理")
        with st.expander("➕ 新增人员档案", expanded=False):
            with st.form("add_emp"):
                c1, c2 = st.columns(2)
                e_nm = c1.text_input("姓名")
                e_rl = c2.selectbox("角色", ["店长", "全职店员", "兼职店员", "实习生", "合作厂商", "其他"])
                c3, c4, c5 = st.columns(3)
                e_wg = c3.number_input("时薪 ($)", min_value=0.0, step=0.5, value=12.0)
                e_ph = c4.text_input("联系方式")
                e_dt = c5.date_input("入职日期", value=datetime.now())
                if st.form_submit_button("保存"):
                    if e_nm.strip() == "": st.warning("⚠️ 姓名为空！")
                    else:
                        fe = JIT_fetch([EMP_SHEET])[EMP_SHEET]
                        nl = pd.DataFrame([[e_nm, e_rl, e_wg, e_ph, e_dt.strftime("%Y/%m/%d"), "", "在职"]], columns=EMP_COLS)
                        save_data(pd.concat([fe, nl], ignore_index=True), EMP_SHEET); st.session_state.emp_reset_key += 1; st.rerun()

        f_emp = get_f(df_employee, q) 
        if not f_emp.empty:
            v_emp = f_emp.copy(); v_emp.insert(0, "选择", False)
            v_emp['时薪'] = pd.to_numeric(v_emp['时薪'], errors='coerce').fillna(0.0)
            ed_emp = st.data_editor(v_emp.style.format({'时薪': '${:.2f}'}), column_config={"选择": st.column_config.CheckboxColumn("选择", default=False), "状态": st.column_config.SelectboxColumn("状态", options=["在职", "离职"])}, disabled=['员工姓名', '入职日期'], use_container_width=True, hide_index=True, key=f"e_ed_{st.session_state.emp_reset_key}")
            
            if st.session_state.get(f"e_ed_{st.session_state.emp_reset_key}", {}).get("edited_rows"):
                he = False; fe = JIT_fetch([EMP_SHEET])[EMP_SHEET]
                for idx, r in ed_emp.iterrows():
                    for c in EMP_COLS:
                        if str(r[c]) != str(v_emp.loc[idx, c]): he = True; fe.at[idx, c] = r[c]
                if he: save_data(fe, EMP_SHEET); st.success("✅ 保存成功！"); st.session_state.emp_reset_key += 1; st.rerun()
            
            sel_e = ed_emp[ed_emp["选择"] == True]
            if not sel_e.empty:
                cb1, cb2, _ = st.columns([1.5, 1.5, 4])
                if cb1.button("🗑️ 彻底删除人员", type="primary"):
                    fe = JIT_fetch([EMP_SHEET])[EMP_SHEET]
                    for _, r in sel_e.iterrows(): fe = fe[fe['员工姓名'].astype(str).str.strip() != str(r['员工姓名']).strip()]
                    save_data(fe, EMP_SHEET); st.session_state.emp_reset_key += 1; st.rerun()

        st.divider()
        st.subheader("⏰ 排班与打卡记录")
        with st.expander("➕ 帮员工补录打卡", expanded=True):
            with st.form("a_att"):
                c1, c2 = st.columns(2)
                an = c1.selectbox("选择员工", df_employee['员工姓名'].astype(str).tolist() if not df_employee.empty else ["Empty"])
                ad = c2.date_input("工作日期", value=datetime.now())
                c3, c4 = st.columns(2)
                ast = c3.time_input("上班时间", value=time(10, 0)); aen = c4.time_input("下班时间", value=time(18, 0))
                if st.form_submit_button("确认记录"):
                    fa = JIT_fetch([ATT_SHEET])[ATT_SHEET]
                    dts, dte = datetime.combine(ad, ast), datetime.combine(ad, aen)
                    if dte < dts: dte += timedelta(days=1)
                    dh = (dte - dts).total_seconds() / 3600.0
                    wg = df_employee[df_employee['员工姓名'] == an]['时薪'].iloc[0] if not df_employee.empty else 0
                    tw = dh * float(pd.to_numeric(wg, errors='coerce') or 0.0)
                    nl = pd.DataFrame([[an, ad.strftime("%Y/%m/%d"), ast.strftime("%H:%M"), aen.strftime("%H:%M"), round(dh, 2), round(tw, 2)]], columns=ATT_COLS)
                    save_data(pd.concat([nl, fa], ignore_index=True), ATT_SHEET); st.rerun()

        fa = get_f(df_attendance, q)
        if not fa.empty:
            va = fa.copy(); va.insert(0, "选择", False)
            va['核算薪资'] = pd.to_numeric(va['核算薪资'], errors='coerce').fillna(0.0)
            eda = st.data_editor(va.style.format({'核算薪资': '${:.2f}'}), column_config={"选择": st.column_config.CheckboxColumn("选择", default=False)}, disabled=fa.columns.tolist(), use_container_width=True, hide_index=True, key=f"a_ed_{st.session_state.att_reset_key}")
            sel_a = eda[eda["选择"] == True]
            if not sel_a.empty:
                cb1, cb2, _ = st.columns([1.5, 1.5, 4])
                if cb1.button("🗑️ 删除打卡记录", type="primary"):
                    fra = JIT_fetch([ATT_SHEET])[ATT_SHEET]
                    for _, r in sel_a.iterrows(): fra = fra[~((fra['员工姓名'].astype(str).str.strip() == str(r['员工姓名']).strip()) & (fra['日期'].astype(str).str.strip() == str(r['日期']).strip()) & (fra['开始时间'].astype(str).str.strip() == str(r['开始时间']).strip()))]
                    save_data(fra, ATT_SHEET); st.session_state.att_reset_key += 1 ; st.rerun()
            st.divider()
            ct1, ct2, ct3 = st.columns([2, 1, 1])
            ct1.markdown(f"**🧾 列表总计** (共 {len(fa)} 条记录)")
            ct2.metric("当前列表总工时", f"{pd.to_numeric(fa['工作时长'], errors='coerce').fillna(0).sum():.1f} 小时")
            ct3.metric("当前列表总薪资支出", f"${pd.to_numeric(fa['核算薪资'], errors='coerce').fillna(0).sum():.2f}")

    with t5:
        st.subheader(f"💎 真实净利润核算 (9% GST 剥离版)")
        sr_t5 = st.date_input("⏳ 分析区间：", value=[st.session_state.camp_start, st.session_state.camp_end], key="t5_dp")
        t5_s, t5_e = (sr_t5[0], sr_t5[1]) if len(sr_t5) == 2 else (sr_t5[0], sr_t5[0])

        if not df_sales.empty:
            dsnp = df_sales.copy(); dsnp['dt'] = pd.to_datetime(dsnp['日期'], errors='coerce'); dsnp = dsnp.dropna(subset=['dt'])
            danp = df_attendance.copy(); danp['dt'] = pd.to_datetime(danp['日期'], errors='coerce'); danp = danp.dropna(subset=['dt']) if not danp.empty else pd.DataFrame(columns=['dt'])

            if not dsnp.empty:
                fs = dsnp[(dsnp['dt'].dt.date >= t5_s) & (dsnp['dt'].dt.date <= t5_e)].copy()
                fa = danp[(danp['dt'].dt.date >= t5_s) & (danp['dt'].dt.date <= t5_e)].copy()

                fs['销售数量'] = pd.to_numeric(fs['销售数量'], errors='coerce').fillna(0)
                fs['总营业额'] = pd.to_numeric(fs['总营业额'], errors='coerce').fillna(0.0)

                dc = df_stock[['商品名称', '颜色', '进价成本']].copy(); dc['进价成本'] = pd.to_numeric(dc['进价成本'], errors='coerce').fillna(0.0)
                fs = fs.merge(dc, on=['商品名称', '颜色'], how='left')
                fs['总进价成本'] = fs['销售数量'] * fs['进价成本']

                fs['d_str'] = fs['dt'].dt.strftime('%Y/%m/%d')
                ds_agg = fs.groupby('d_str').agg({'总营业额': 'sum', '总进价成本': 'sum'}).reset_index()

                if not fa.empty:
                    fa['核算薪资'] = pd.to_numeric(fa['核算薪资'], errors='coerce').fillna(0.0)
                    fa['d_str'] = fa['dt'].dt.strftime('%Y/%m/%d')
                    da_agg = fa.groupby('d_str').agg({'核算薪资': 'sum'}).reset_index().rename(columns={'核算薪资': '人工成本'})
                else: da_agg = pd.DataFrame(columns=['d_str', '人工成本'])

                dnp = pd.merge(ds_agg, da_agg, on='d_str', how='outer').fillna(0.0).sort_values('d_str', ascending=False)
                dnp['免税净营业额'] = dnp['总营业额'] / 1.09
                dnp['代扣GST(9%)'] = dnp['总营业额'] - dnp['免税净营业额']
                dnp['商场抽成(36%)'] = dnp['免税净营业额'] * 0.36
                dnp['商场实际回款'] = dnp['免税净营业额'] - dnp['商场抽成(36%)']
                dnp['毛利润'] = dnp['商场实际回款'] - dnp['总进价成本']
                dnp['真实净利润'] = dnp['毛利润'] - dnp['人工成本']

                t_grs = dnp['总营业额'].sum()
                t_gst = dnp['代扣GST(9%)'].sum()
                t_com = dnp['商场抽成(36%)'].sum()
                t_set = dnp['商场实际回款'].sum()
                t_cog = dnp['总进价成本'].sum()
                t_wg = dnp['人工成本'].sum()
                t_net = dnp['真实净利润'].sum()

                p_gst = (t_gst / t_grs * 100) if t_grs > 0 else 0
                p_com = (t_com / t_grs * 100) if t_grs > 0 else 0
                p_cog = (t_cog / t_grs * 100) if t_grs > 0 else 0
                p_wg = (t_wg / t_grs * 100) if t_grs > 0 else 0
                p_net = (t_net / t_grs * 100) if t_grs > 0 else 0

                st.info("💡 财务脱水逻辑：含税总额剥离 9% GST -> 免税净额扣除 36% 高岛屋抽成 -> 实际回款减去货品进价与打卡工资 = 真实净利。")
                
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("💰 选中期间总营业额", f"${t_grs:.2f}", delta="100.0% (营收基准)", delta_color="off")
                m2.metric("🏛️ 剥离 GST (9%)", f"${t_gst:.2f}", delta=f"占比: {p_gst:.1f}%", delta_color="off")
                m3.metric("📉 商场抽成 (36%)", f"${t_com:.2f}", delta=f"占比: {p_com:.1f}%", delta_color="off")
                m4.metric("💵 商场实际回款", f"${t_set:.2f}")
                st.divider()
                m5, m6, m7, m8 = st.columns(4)
                m5.metric("📦 商品进价成本", f"${t_cog:.2f}", delta=f"占比: {p_cog:.1f}%", delta_color="off")
                m6.metric("👥 打卡人工成本", f"${t_wg:.2f}", delta=f"占比: {p_wg:.1f}%", delta_color="off")
                m7.metric("💎 选中期间纯利润", f"${t_net:.2f}", delta=f"含税净利率: {p_net:.1f}%", delta_color="normal")
                m8.empty()

                st.divider()
                st.markdown("### 📈 每日营收 vs 净利润趋势")
                st.bar_chart(dnp.set_index('d_str')[['总营业额', '真实净利润']].sort_index(ascending=True), use_container_width=True)

                st.markdown("### 📅 每日盈亏明细榜 (Daily P&L)")
                dl1, dl2 = st.columns([1.5, 4])
                dl1.download_button("⬇️ 一键导出明细 (CSV)", convert_df_to_csv(dnp), f"Taka_Profit_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv", type="primary")

                snp = dnp.rename(columns={'d_str': '日期'})
                def cnp(val):
                    try:
                        v = float(val)
                        if v > 0: return 'background-color: #e6ffe6; color: #006600; font-weight: bold;'
                        elif v < 0: return 'background-color: #ffe6e6; color: #cc0000; font-weight: bold;'
                    except: pass
                    return ''
                fd = {'总营业额':'${:.2f}', '免税净营业额':'${:.2f}', '代扣GST(9%)':'${:.2f}', '商场抽成(36%)':'${:.2f}', '商场实际回款':'${:.2f}', '总进价成本':'${:.2f}', '人工成本':'${:.2f}', '毛利润':'${:.2f}', '真实净利润':'${:.2f}'}
                try: sty_np = snp.style.format(fd).map(cnp, subset=['真实净利润'])
                except: sty_np = snp.style.format(fd).applymap(cnp, subset=['真实净利润'])
                st.dataframe(sty_np, use_container_width=True, hide_index=True)

    with t6:
        st.subheader("🤝 B2B 大客户与企采订单管理")
        st.info("💡 B2B订单独立核算，免收快闪店抽成！支持【单一商品】与【多件组合套装】双模式。")

        if not df_b2b.empty:
            for c in ['总计应收', '已收定金', '货物成本', '物流成本', '关税']: df_b2b[c] = pd.to_numeric(df_b2b[c], errors='coerce').fillna(0.0)
            df_b2b['待收尾款'] = df_b2b['总计应收'] - df_b2b['已收定金']
            df_b2b['B2B净利润'] = df_b2b['总计应收'] - df_b2b['货物成本'] - df_b2b['物流成本'] - df_b2b['关税']
            
            tbv = df_b2b['总计应收'].sum()
            tbc = df_b2b['已收定金'].sum()
            tbp = df_b2b['待收尾款'].sum()
            tbpr = df_b2b['B2B净利润'].sum()
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("💼 B2B 总合同额", f"${tbv:.2f}"); c2.metric("💰 已回款金额", f"${tbc:.2f}")
            c3.metric("⏳ 待结清尾款", f"${tbp:.2f}"); c4.metric("💎 B2B 预估净利润", f"${tbpr:.2f}", delta=f"净利率: {(tbpr / tbv * 100) if tbv > 0 else 0.0:.1f}%", delta_color="off")

        with st.expander("➕ 录入全新 B2B 订单", expanded=False):
            c1, c2 = st.columns(2)
            bc = c1.text_input("🏢 客户/企业名称 (必填)", placeholder="例如：NGS")
            bd = c2.date_input("📅 建单日期", value=datetime.now())

            om = st.radio("🛒 选择订单商品模式", ["🎯 单一商品 (常规下单)", "📦 多件组合 / 礼盒套装"], horizontal=True)

            fn, fc, fq, fp, ft, fnote = "", "", 0, 0.0, 0.0, ""

            if om == "🎯 单一商品 (常规下单)":
                fb2 = get_f(df_stock, "").copy() 
                sl = []
                if not fb2.empty:
                    fb2['dn'] = translate_series(fb2['商品名称']).fillna('').astype(str)
                    fb2['dc'] = translate_series(fb2['颜色']).fillna('').astype(str)
                    sl = (fb2['dn'] + " (" + fb2['dc'] + ")").tolist()
                cs1, cs2, cs3 = st.columns([2, 1.5, 1])
                bp = cs1.selectbox("选现有商品", ["(不选择)"] + sl)
                bcp = cs2.text_input("手动输入定制商品")
                bcc = cs3.text_input("定制颜色")
                cq, cp = st.columns(2)
                bq = cq.number_input("采购数量", min_value=1, value=100)
                bpr = cp.number_input("B2B 批发单价 ($)", format="%.2f", min_value=0.0)
                ft, fq, fp = bq * bpr, bq, bpr
                if bcp.strip(): fn, fc = bcp.strip(), bcc.strip()
                elif bp != "(不选择)": fn, fc = t_val(bp.rsplit(" (", 1)[0], 'cn'), t_val(bp.rsplit(" (", 1)[1].replace(")", ""), 'cn')

            else:
                cnm = st.text_input("📦 组合大单名称", placeholder="例如：NGS 100件定制混装礼盒")
                ed_c = st.data_editor(pd.DataFrame([{"名称": "杯子", "颜色": "默认", "单价($)": 0.0, "数量": 1}]), num_rows="dynamic", use_container_width=True)
                di = []
                for _, r in ed_c.iterrows():
                    try:
                        p, q_ = float(r["单价($)"]), int(r["数量"])
                        n, c_ = str(r["名称"]).strip(), str(r["颜色"]).strip()
                        if n:
                            ft += p * q_; fq += q_
                            di.append(f"{n}({c_})x{q_}" if c_ else f"{n}x{q_}")
                    except: pass
                st.info(f"🧮 此组合共计 **{fq}** 件，总金额 **${ft:.2f}**")
                fn, fc, fp = f"【组合】{cnm.strip()}", "多件混装", 0.0 
                fnote = " + ".join(di)

            c10, c11, c12, c13 = st.columns(4)
            bdep = c10.number_input("已收定金/首款 ($)", format="%.2f")
            bcog = c11.number_input("预估总货物成本 ($)", format="%.2f")
            bshp = c12.number_input("预估物流总成本 ($)", format="%.2f")
            btax = c13.number_input("预估关税 ($)", format="%.2f")

            c8, c9, c_dead = st.columns([1, 1.5, 1])
            bsts = c8.selectbox("当前状态", ["意向/沟通中", "已付定金/备货中", "已发货/待结尾款", "✅ 订单已完成"])
            bnt = c9.text_input("附加备注")
            bdl = c_dead.date_input("约定交货日期", value=datetime.now() + timedelta(days=30))

            if st.button("🚀 确认创建 B2B 订单", type="primary", use_container_width=True):
                if not bc.strip(): st.error("⚠️ 请填写客户/企业名称！")
                elif not fn or fn == "【组合】": st.error("⚠️ 请正确选择商品！")
                else:
                    frb = JIT_fetch([B2B_SHEET])[B2B_SHEET]
                    bal = ft - bdep
                    fnc = f"明细: {fnote} | 备注: {bnt}" if om == "📦 多件组合 / 礼盒套装" else bnt
                    nb = pd.DataFrame([[bd.strftime("%Y/%m/%d"), bc, fn, fc, fq, fp, ft, bcog, bshp, btax, bdep, bal, bdl.strftime("%Y/%m/%d"), bsts, fnc]], columns=B2B_COLS)
                    save_data(pd.concat([nb, frb], ignore_index=True), B2B_SHEET)
                    st.success(f"✅ B2B 订单创建成功！"); st.rerun()

        st.divider()
        fb2b = get_f(df_b2b, q)
        if not fb2b.empty:
            vb = fb2b.copy(); vb.insert(0, "选择", False)
            sb = vb.style.format({'B2B单价':'${:.2f}', '总计应收':'${:.2f}', '货物成本':'${:.2f}', '物流成本':'${:.2f}', '关税':'${:.2f}', '已收定金':'${:.2f}', '待收尾款':'${:.2f}'})
            edb = st.data_editor(sb, column_config={"选择": st.column_config.CheckboxColumn("选择", default=False), "订单状态": st.column_config.SelectboxColumn("订单状态", options=["意向/沟通中", "已付定金/备货中", "已发货/待结尾款", "✅ 订单已完成"])}, disabled=['待收尾款', 'B2B净利润', '预估净利率'], use_container_width=True, hide_index=True, key=f"b2b_e_{st.session_state.b2b_reset_key}")
            
            if st.session_state.get(f"b2b_e_{st.session_state.b2b_reset_key}", {}).get("edited_rows"):
                he = False
                frb = JIT_fetch([B2B_SHEET])[B2B_SHEET]
                for idx, row in edb.iterrows():
                    for c in ['货物成本', '物流成本', '关税', '已收定金', '订单状态', '约定交期', '备注']:
                        if str(row[c]) != str(vb.loc[idx, c]):
                            he = True; frb.at[idx, c] = row[c]
                            frb.at[idx, '待收尾款'] = float(row['总计应收'] or 0) - float(row['已收定金'] or 0)
                if he: save_data(frb[B2B_COLS], B2B_SHEET); st.success("✅ 修改已保存！"); st.session_state.b2b_reset_key += 1; st.rerun()

            selb = edb[edb["选择"] == True]
            if not selb.empty:
                cb1, cb2, _ = st.columns([1.5, 1.5, 4])
                if cb1.button("🗑️ 删除选中订单", type="primary"):
                    frb = JIT_fetch([B2B_SHEET])[B2B_SHEET]
                    for _, r in selb.iterrows(): frb = frb[~((frb['客户名称'].astype(str).str.strip() == str(r['客户名称']).strip()) & (frb['商品名称'].astype(str).str.strip() == str(r['商品名称']).strip()) & (frb['创建日期'].astype(str).str.strip() == str(r['创建日期']).strip()))]
                    save_data(frb[B2B_COLS], B2B_SHEET); st.session_state.b2b_reset_key += 1; st.rerun()

    with t7:
        st.subheader("🗣️ 新加坡本地客户产品反馈池")
        fops = ["产品功能性", "产品优化", "保温保冷效能", "外观颜值 / 颜色", "材质手感 / 重量", "清洗 / 异味问题", "杯盖 / 密封性", "价格因素", "🌏 本土化优化 (非产品)", "夸奖 / 好评", "其他建议"]
        cops = ["本地散客", "VIP / 老客复购", "送礼需求", "游客", "B2B企业客户"]
        sops = ["🚨 待处理 / 待评估", "📝 已记录 / 待反馈工厂", "✅ 已解决 / 已采纳"]

        with st.expander("➕ 快速录入新反馈", expanded=True):
            with st.form("add_fb"):
                c1, c2 = st.columns(2)
                fbd = c1.date_input("反馈日期", value=datetime.now())
                fbp = c2.selectbox("提及的商品", df_stock['商品名称'].unique().tolist() + ["全系产品 / 通用"]) if not df_stock.empty else c2.text_input("商品")
                c3, c4 = st.columns(2)
                fbt, fbc = c3.selectbox("反馈痛点 / 类型", fops), c4.selectbox("客户画像", cops)
                fbdt = st.text_area("🗣️ 详细描述", placeholder="客人觉得...")
                fbs = st.selectbox("跟进状态", sops)
                if st.form_submit_button("保存反馈", type="primary", use_container_width=True) and fbdt.strip():
                    ffb = JIT_fetch([FEEDBACK_SHEET])[FEEDBACK_SHEET]
                    nf = pd.DataFrame([[fbd.strftime("%Y/%m/%d"), fbp, fbc, fbt, fbdt, fbs]], columns=FEEDBACK_COLS)
                    save_data(pd.concat([nf, ffb], ignore_index=True), FEEDBACK_SHEET); st.success("✅ 录入成功！"); st.rerun()

        st.divider()
        ff = get_f(df_feedback, q)
        if not ff.empty:
            fc1, fc2 = st.columns(2)
            fc1.markdown("**📌 哪些痛点被疯狂吐槽？**"); fc1.bar_chart(ff['反馈类型'].value_counts())
            fc2.markdown("**📌 哪款产品话题度最高？**"); fc2.bar_chart(ff['商品名称'].value_counts())

            vf = ff.copy(); vf.insert(0, "选择", False)
            edf = st.data_editor(vf, column_config={"选择": st.column_config.CheckboxColumn("选择", default=False), "跟进状态": st.column_config.SelectboxColumn("状态", options=sops), "反馈类型": st.column_config.SelectboxColumn("类型", options=fops), "客户画像": st.column_config.SelectboxColumn("画像", options=cops)}, use_container_width=True, hide_index=True, key=f"f_ed_{st.session_state.fb_reset_key}")
            
            if st.session_state.get(f"f_ed_{st.session_state.fb_reset_key}", {}).get("edited_rows"):
                he = False
                frf = JIT_fetch([FEEDBACK_SHEET])[FEEDBACK_SHEET]
                for idx, r in edf.iterrows():
                    for c in FEEDBACK_COLS:
                        if str(r[c]) != str(vf.loc[idx, c]): he = True; frf.at[idx, c] = r[c]
                if he: save_data(frf, FEEDBACK_SHEET); st.success("✅ 修改保存！"); st.session_state.fb_reset_key += 1; st.rerun()

            selfb = edf[edf["选择"] == True]
            if not selfb.empty and st.button("🗑️ 删除反馈", type="primary"):
                frf = JIT_fetch([FEEDBACK_SHEET])[FEEDBACK_SHEET]
                for _, r in selfb.iterrows(): frf = frf[~((frf['详细原话'].astype(str).str.strip() == str(r['详细原话']).strip()) & (frf['反馈日期'].astype(str).str.strip() == str(r['反馈日期']).strip()) & (frf['商品名称'].astype(str).str.strip() == str(r['商品名称']).strip()))]
                save_data(frf, FEEDBACK_SHEET); st.session_state.fb_reset_key += 1; st.rerun()

    with t8:
        st.subheader(f"📈 选品与战略决策盘 (锁定基准档期: {st.session_state.camp_name})")
        st.info(f"💡 罗盘已锁定【{st.session_state.camp_start} 至 {st.session_state.camp_end}】进行计算。气泡大小=压货金额。")

        if not df_sales.empty and not df_stock.empty:
            dsbi = df_sales.copy(); dsbi['dt'] = pd.to_datetime(dsbi['日期'], errors='coerce')
            fsbi = dsbi[(dsbi['dt'].dt.date >= st.session_state.camp_start) & (dsbi['dt'].dt.date <= st.session_state.camp_end)].copy()
            fsbi['销售数量'] = pd.to_numeric(fsbi['销售数量'], errors='coerce').fillna(0)
            fsbi['总营业额'] = pd.to_numeric(fsbi['总营业额'], errors='coerce').fillna(0.0)

            bs = fsbi.groupby(['商品名称', '颜色']).agg({'销售数量': 'sum', '总营业额': 'sum'}).reset_index()

            dk = df_stock[['商品名称', '颜色', '进价成本', '总库存']].copy()
            dk['进价成本'] = pd.to_numeric(dk['进价成本'], errors='coerce').fillna(0.0)
            dk['总库存'] = pd.to_numeric(dk['总库存'], errors='coerce').fillna(0)

            bi = pd.merge(dk, bs, on=['商品名称', '颜色'], how='left').fillna(0)
            bi['压货金额'] = bi['总库存'] * bi['进价成本']

            tdy = datetime.now().date()
            if tdy < st.session_state.camp_start: dip = 1
            else: dip = max((min(tdy, st.session_state.camp_end) - st.session_state.camp_start).days + 1, 1)
            
            bi['日均动销率'] = bi['销售数量'] / dip
            bi['总进价成本'] = bi['销售数量'] * bi['进价成本']
            bi['具体毛利'] = bi['总营业额'] - bi['总进价成本']
            bi['毛利率(%)'] = ((bi['具体毛利'] / bi['总营业额']) * 100).fillna(0.0)

            bi['可售天数'] = bi.apply(lambda r: int(r['总库存'] / r['日均动销率']) if r['日均动销率'] > 0 else 999, axis=1)
            bi = bi.sort_values(by='总营业额', ascending=False)
            trv = bi['总营业额'].sum()
            bi['累计营收占比'] = bi['总营业额'].cumsum() / trv if trv > 0 else 0
            
            def get_abc(p):
                if p <= 0.7: return "👑 A类 (70%业绩)"
                elif p <= 0.9: return "🌟 B类 (20%业绩)"
                else: return "📦 C类 (10%业绩)"
            bi['ABC等级'] = bi['累计营收占比'].apply(get_abc)
            
            def ghl(r):
                c, s = r['可售天数'], r['总库存']
                if s == 0 and r['销售数量'] > 0: return "⚫ 彻底断货"
                elif c <= 7 and s > 0: return "🔴 濒临断货"
                elif c > 60 and s > 0: return "🔴 严重积压"
                elif 30 < c <= 60: return "🟡 偏高预警"
                elif 7 < c <= 15: return "🟡 偏低预警"
                else: return "🟢 健康周转"
            bi['风控灯'] = bi.apply(ghl, axis=1)

            med_m = bi[bi['销售数量'] > 0]['毛利率(%)'].median() if not bi[bi['销售数量'] > 0].empty else 50.0

            def gtg(r):
                v, m, s, c = r['日均动销率'], r['毛利率(%)'], r['总库存'], r['可售天数']
                if s <= 2 and r['销售数量'] > 0 and c <= 7: return "🚨 爆款流血断货 (紧急空运)"
                elif v < 0.167 and c > 30 and s > 0: return "📦 积压套牢 (清仓)"
                elif v >= 0.33 and m >= med_m: return "⭐ 绝对明星 (死保)"
                elif v >= 0.33 and m < med_m: return "🧲 引流款 (走量)"
                elif v < 0.167 and m >= med_m: return "🐢 利润陷阱"
                elif v < 0.167 and m < med_m: return "☠️ 斩仓废柴"
                else: return "🚶 平庸常规款"

            bi['诊断标签'] = bi.apply(gtg, axis=1)
            # 强制转字符串防止合并时发生空值崩溃
            bi['商品规格'] = translate_series(bi['商品名称']).fillna('').astype(str) + " (" + translate_series(bi['颜色']).fillna('').astype(str) + ")"
            bi['气泡'] = bi['压货金额'].apply(lambda x: max(float(x), 10))

            ac = len(bi[bi['ABC等级'].str.contains('A类')])
            dsv = bi[bi['风控灯'].str.contains('严重积压')]['压货金额'].sum()
            
            bc1, bc2 = st.columns(2)
            bc1.metric(f"👑 A类印钞机", f"{ac} 款")
            bc2.metric("🔴 死库套牢资金 (>60天)", f"${dsv:.2f}", delta_color="inverse")
            
            fig = px.scatter(bi, x='日均动销率', y='毛利率(%)', color='诊断标签', size='气泡', hover_name='商品规格', hover_data={'ABC等级':True,'风控灯':True,'日均动销率':':.2f','毛利率(%)':':.1f','总营业额':':.2f','可售天数':True,'总库存':True,'压货金额':':.2f','气泡':False}, size_max=45, height=550, template="plotly_white")
            fig.add_vline(x=0.33, line_dash="dash", line_color="gray", annotation_text=" 及格销量(0.33)")
            fig.add_hline(y=med_m, line_dash="dash", line_color="gray", annotation_text=f" 达标毛利({med_m:.1f}%)")
            st.plotly_chart(fig, use_container_width=True)
            
            st.dataframe(bi[['商品规格', 'ABC等级', '风控灯', '日均动销率', '毛利率(%)', '总营业额', '可售天数', '总库存', '压货金额']].style.format({'总营业额': '${:.2f}', '压货金额': '${:.2f}', '日均动销率': '{:.2f}', '毛利率(%)': '{:.1f}%'}), use_container_width=True, hide_index=True)

# ================= 🚀 Tab 3-4: 厂商专属层 (Supplier) =================
elif is_supplier:
    with t3:
        st.subheader(t("📦 进货与入库对账单 (ERP 底单)", "📦 Inbound Records"))
        dr = df_restock.copy(); dr['dt'] = pd.to_datetime(dr['记录日期'], errors='coerce')
        dr = dr.dropna(subset=['dt'])
        if not dr.empty:
            s_dr = st.date_input(t("📅 选择日期", "📅 Date Range"), value=[st.session_state.camp_start, st.session_state.camp_end], key="sup_rs")
            r_s, r_e = (s_dr[0], s_dr[1]) if len(s_dr) == 2 else (s_dr[0], s_dr[0])
            fr = dr[(dr['dt'].dt.date >= r_s) & (dr['dt'].dt.date <= r_e)]
            fr = get_f(fr, q)
            if not fr.empty:
                fr['操作类型'] = translate_series(fr['操作类型'])
                a_ops = [str(x) for x in fr['操作类型'].fillna('').unique() if str(x).strip()]
                s_defs = list(set([op for op in [t_val("入库", "en"), t_val("初始建档", "en"), "入库", "初始建档"] if op in a_ops]))
                tf = st.multiselect(t("筛选操作", "Filter Ops"), options=a_ops, default=s_defs)
                if tf:
                    fr = fr[fr['操作类型'].isin(tf)]
                    fr['商品名称'] = translate_series(fr['商品名称']); fr['颜色'] = translate_series(fr['颜色'])
                    tot_i = fr['变动数量'].apply(lambda x: pd.to_numeric(x, errors='coerce')).fillna(0).sum()
                    st.metric(t("🚛 变动总数", "🚛 Total Qty"), f"{int(tot_i)}")
                    dd = fr[['记录日期', '操作类型', '商品名称', '颜色', '变动数量', '库位详情', '备注']].copy()
                    if st.session_state.lang == 'en': dd.rename(columns=col_map, inplace=True)
                    st.dataframe(dd, use_container_width=True, hide_index=True)

    with t4:
        st.subheader(t("🤝 B2B 订单对账单", "🤝 B2B Orders"))
        if not df_b2b.empty:
            db = df_b2b.copy(); db['dt'] = pd.to_datetime(db['创建日期'], errors='coerce'); db = db.dropna(subset=['dt'])
            if not db.empty:
                s_dr = st.date_input(t("📅 选择建单日期", "📅 Select Date"), value=[st.session_state.camp_start, st.session_state.camp_end], key="sup_b2b")
                b_s, b_e = (s_dr[0], s_dr[1]) if len(s_dr) == 2 else (s_dr[0], s_dr[0])
                fb = db[(db['dt'].dt.date >= b_s) & (db['dt'].dt.date <= b_e)]
                fb = get_f(fb, q)
                if not fb.empty:
                    for c in ['采购数量', 'B2B单价', '总计应收', '已收定金']:
                        if c in fb.columns: fb[c] = pd.to_numeric(fb[c], errors='coerce').fillna(0.0)
                    fb['待收尾款'] = fb['总计应收'] - fb['已收定金']
                    c1, c2 = st.columns(2)
                    c1.metric(t("📦 B2B 总采购件数", "📦 Total B2B Qty"), f"{int(fb['采购数量'].sum())}")
                    c2.metric(t("💰 B2B 总计应收", "💰 Total B2B Value"), f"${fb['总计应收'].sum():.2f}")
                    
                    fb['商品名称'] = translate_series(fb['商品名称']); fb['颜色'] = translate_series(fb['颜色']); fb['订单状态'] = translate_series(fb['订单状态'])
                    df_disp = fb[['创建日期', '客户名称', '商品名称', '颜色', '采购数量', 'B2B单价', '总计应收', '已收定金', '待收尾款', '约定交期', '订单状态', '备注']].copy()
                    if st.session_state.lang == 'en': df_disp.rename(columns=col_map, inplace=True)
                    uc, tc, d_c, bc = ('B2B Price', 'Total Recv.', 'Deposit', 'Balance') if st.session_state.lang == 'en' else ('B2B单价', '总计应收', '已收定金', '待收尾款')
                    st.dataframe(df_disp.style.format({uc: '${:.2f}', tc: '${:.2f}', d_c: '${:.2f}', bc: '${:.2f}'}), use_container_width=True, hide_index=True)

# ================= 🚀 Tab 3: 员工打卡层 (Employee) =================
elif is_employee:
    with t3:
        st.subheader(t("⏰ 员工考勤打卡", "⏰ Staff Timeclock"))
        st.info(t("💡 请如实填报您的上下班时间，系统将自动核算工资。", "💡 Please log your daily working hours below. System will auto-calculate wage."))
        
        with st.form("emp_attendance_form"):
            emp_name = st.session_state.current_user
            st.markdown(f"**{t('当前打卡人', 'Current Staff')}:** `{emp_name}`")
            att_date = st.date_input(t("工作日期", "Work Date"), value=datetime.now())
            c1, c2 = st.columns(2)
            att_start = c1.time_input(t("上班时间", "Clock In Time"), value=time(10, 0))
            att_end = c2.time_input(t("下班时间", "Clock Out Time"), value=time(18, 0))
            
            if st.form_submit_button(t("✅ 确认打卡", "✅ Submit Time"), type="primary", use_container_width=True):
                fresh_att = JIT_fetch([ATT_SHEET])[ATT_SHEET]
                fresh_emp = JIT_fetch([EMP_SHEET])[EMP_SHEET]
                
                dt_start = datetime.combine(att_date, att_start)
                dt_end = datetime.combine(att_date, att_end)
                if dt_end < dt_start: dt_end += timedelta(days=1)
                duration_hours = (dt_end - dt_start).total_seconds() / 3600.0
                
                emp_rows = fresh_emp[fresh_emp['员工姓名'].astype(str).str.strip() == str(emp_name).strip()]
                if not emp_rows.empty: hourly_wage = float(pd.to_numeric(emp_rows.iloc[0]['时薪'], errors='coerce') or 0.0)
                else: hourly_wage = 0.0
                total_wage = duration_hours * hourly_wage
                
                new_att = pd.DataFrame([[
                    emp_name, att_date.strftime("%Y/%m/%d"), 
                    att_start.strftime("%H:%M"), att_end.strftime("%H:%M"), 
                    round(duration_hours, 2), round(total_wage, 2)
                ]], columns=ATT_COLS)
                
                fresh_att = pd.concat([new_att, fresh_att], ignore_index=True)
                save_data(fresh_att, ATT_SHEET) 
                st.success(t(f"打卡成功！共计 {round(duration_hours, 1)} 小时。", f"Success! Total {round(duration_hours, 1)} hrs."))
                st.rerun()

        st.divider()
        st.markdown(t("### 📝 我的历史记录 (只读)", "### 📝 My Time Logs (Read-only)"))
        f_att = get_f(df_attendance, q)
        my_att = f_att[f_att['员工姓名'].astype(str).str.strip() == str(st.session_state.current_user).strip()].copy() if not f_att.empty else pd.DataFrame()
        if not my_att.empty:
            my_att['核算薪资'] = pd.to_numeric(my_att['核算薪资'], errors='coerce').fillna(0.0)
            my_disp = my_att.copy()
            if st.session_state.lang == 'en': my_disp.rename(columns=col_map, inplace=True)
            w_col = 'Est. Wage' if st.session_state.lang == 'en' else '核算薪资'
            st.dataframe(my_disp.style.format({w_col: '${:.2f}'}), use_container_width=True, hide_index=True)
            
            tot_h = pd.to_numeric(my_att['工作时长'], errors='coerce').fillna(0).sum()
            tot_w = my_att['核算薪资'].sum()
            c3, c4 = st.columns(2)
            c3.metric(t("累积总工时", "Total Hours"), f"{tot_h:.1f}")
            c4.metric(t("预估总薪资", "Total Est. Wage"), f"${tot_w:.2f}")
        else:
            st.info(t("暂无打卡记录。", "No time logs found."))
