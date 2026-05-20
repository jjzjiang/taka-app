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
    st.error(f"🔴 数据库连接失败 Database connection failed! Error: {e}")
    st.stop()

# ================= 🚀 国际化 (i18n) 双语翻译引擎 =================
if "lang" not in st.session_state:
    st.session_state.lang = "cn"

def t(cn_text, en_text):
    return cn_text if st.session_state.lang == "cn" else en_text

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
    val_str = str(val).strip()
    if to_lang == 'en': return val_map_cn_to_en.get(val_str, val_str)
    else: return val_map_en_to_cn.get(val_str, val_str)

def translate_series(series):
    if st.session_state.lang == 'en': return series.fillna('').astype(str).map(lambda x: val_map_cn_to_en.get(x.strip(), x.strip()))
    return series.fillna('').astype(str)

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

all_sheets = [STOCK_SHEET, SALES_SHEET, EMP_SHEET, ATT_SHEET, B2B_SHEET, FEEDBACK_SHEET, RESTOCK_SHEET, TRAFFIC_SHEET, CAMP_SHEET]

if "sheet_versions" not in st.session_state: st.session_state.sheet_versions = {s: 0 for s in all_sheets}
if "pos_cart" not in st.session_state: st.session_state.pos_cart = []

@st.cache_data(ttl=300, show_spinner=False)
def load_raw_data(sheet_name, version):
    try:
        records = sh.worksheet(sheet_name).get_all_records()
        return pd.DataFrame(records) if records else pd.DataFrame()
    except Exception: return pd.DataFrame()

def load_data(sheet_name, columns):
    df = load_raw_data(sheet_name, st.session_state.sheet_versions.get(sheet_name, 0))
    if df.empty: df = pd.DataFrame(columns=columns)
    for col in columns:
        if col not in df.columns: df[col] = "" 
    return df[columns]

def save_data(df, sheet_name):
    try: worksheet = sh.worksheet(sheet_name)
    except WorksheetNotFound: worksheet = sh.add_worksheet(title=sheet_name, rows="1000", cols="20")
    worksheet.clear() 
    df_safe = df.fillna("").astype(str)
    worksheet.update(values=[df_safe.columns.values.tolist()] + df_safe.values.tolist(), range_name='A1')
    st.session_state.sheet_versions[sheet_name] = st.session_state.sheet_versions.get(sheet_name, 0) + 1

def clean_date_col(df, col_name):
    if not df.empty and col_name in df.columns: df[col_name] = pd.to_datetime(df[col_name], errors='coerce').dt.strftime('%Y/%m/%d').fillna('')
    return df

def load_safe_sales():
    df = clean_date_col(load_data(SALES_SHEET, SALES_COLS), '日期')
    if not df.empty:
        df['订单号'] = df['订单号'].fillna('').astype(str).replace('0', '历史单').replace('', '历史单').replace('nan', '历史单')
        if '收银员' not in df.columns: df['收银员'] = '店长/历史'
        else: df['收银员'] = df['收银员'].fillna('').astype(str).replace('0', '店长/历史').replace('', '店长/历史').replace('nan', '店长/历史')
    return df

def load_safe_emp():
    df = clean_date_col(load_data(EMP_SHEET, EMP_COLS), '入职日期') 
    if not df.empty:
        df['状态'] = df['状态'].fillna('').astype(str).replace('0', '在职').replace('', '在职').replace('nan', '在职')
        df['登录密码'] = df['登录密码'].fillna('').astype(str).replace('0', '').replace('nan', '')
    return df

def JIT_fetch(sheets_to_fetch):
    st.cache_data.clear() 
    res = {}
    if STOCK_SHEET in sheets_to_fetch: res[STOCK_SHEET] = load_data(STOCK_SHEET, STOCK_COLS)
    if SALES_SHEET in sheets_to_fetch: res[SALES_SHEET] = load_safe_sales()
    if RESTOCK_SHEET in sheets_to_fetch: res[RESTOCK_SHEET] = clean_date_col(load_data(RESTOCK_SHEET, RESTOCK_COLS), '记录日期')
    if B2B_SHEET in sheets_to_fetch: res[B2B_SHEET] = clean_date_col(clean_date_col(load_data(B2B_SHEET, B2B_COLS), '创建日期'), '约定交期')
    if FEEDBACK_SHEET in sheets_to_fetch: res[FEEDBACK_SHEET] = clean_date_col(load_data(FEEDBACK_SHEET, FEEDBACK_COLS), '反馈日期')
    if EMP_SHEET in sheets_to_fetch: res[EMP_SHEET] = load_safe_emp()
    if ATT_SHEET in sheets_to_fetch: res[ATT_SHEET] = clean_date_col(load_data(ATT_SHEET, ATT_COLS), '日期')
    if TRAFFIC_SHEET in sheets_to_fetch: res[TRAFFIC_SHEET] = clean_date_col(load_data(TRAFFIC_SHEET, TRAFFIC_COLS), '日期')
    return res

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

# ================= 🚀 门禁系统 =================
if "role" not in st.session_state:
    query_role = st.query_params.get("role")
    query_user = st.query_params.get("user")
    if query_role == "admin": st.session_state.role, st.session_state.current_user = "admin", "店长"
    elif query_role in ["employee", "supplier"] and query_user: st.session_state.role, st.session_state.current_user = query_role, query_user
    else: st.session_state.role = st.session_state.current_user = None

if "camp_start" not in st.session_state: st.session_state.camp_start = datetime(2026, 3, 26).date()
if "camp_end" not in st.session_state: st.session_state.camp_end = datetime.now().date()
if "camp_name" not in st.session_state: st.session_state.camp_name = "默认全局"

with st.sidebar:
    st.header(t("🔐 系统门禁", "🔐 System Access"))
    if st.session_state.role is not None:
        user_emoji = "👑" if st.session_state.role == "admin" else ("🏭" if st.session_state.role == "supplier" else "🧑‍💼")
        st.success(t(f"{user_emoji} 欢迎回来：{st.session_state.current_user}", f"{user_emoji} Welcome: {st.session_state.current_user}"))
        
        if st.button(t("🚪 退出系统 (交接班)", "🚪 Logout"), use_container_width=True):
            st.session_state.role = st.session_state.current_user = None
            st.query_params.clear(); st.rerun()
            
        if st.session_state.role == "admin":
            st.divider()
            st.header("🎯 全局时间控制器")
            st.info("💡 选择时间并应用，右侧看板将瞬间同步该时段的数据，告别卡顿！")
            
            camp_options = df_camp['档期名称'].dropna().unique().tolist() if not df_camp.empty else []
            sel_camp = st.selectbox("📌 预设档期", ["手动自定义区间"] + camp_options, index=0)
            
            c_start_col, c_end_col = st.columns(2)
            man_start = c_start_col.date_input("开始日期", value=st.session_state.camp_start)
            man_end = c_end_col.date_input("结束日期", value=st.session_state.camp_end)
            
            if st.button("🚀 应用此全局时间", type="primary", use_container_width=True):
                if sel_camp != "手动自定义区间" and not df_camp.empty:
                    row = df_camp[df_camp['档期名称'] == sel_camp].iloc[0]
                    try:
                        st.session_state.camp_start = pd.to_datetime(row['开始日期']).date()
                        st.session_state.camp_end = pd.to_datetime(row['结束日期']).date()
                        st.session_state.camp_name = sel_camp
                    except: pass
                else:
                    st.session_state.camp_start, st.session_state.camp_end, st.session_state.camp_name = man_start, man_end, "手动自定义区间"
                st.rerun()
                
            st.success(f"**当前全局时间锁定为:**\n\n`{st.session_state.camp_start}` 至 `{st.session_state.camp_end}`")
                
            with st.expander("⚙️ 管理/自建预设档期", expanded=False):
                v_camp = df_camp.copy() if not df_camp.empty else pd.DataFrame(columns=CAMP_COLS)
                edited_camp = st.data_editor(v_camp, num_rows="dynamic", use_container_width=True)
                if st.button("💾 保存档期名录", type="primary", use_container_width=True):
                    edited_camp['开始日期'] = pd.to_datetime(edited_camp['开始日期'], errors='coerce').dt.strftime('%Y/%m/%d').fillna('')
                    edited_camp['结束日期'] = pd.to_datetime(edited_camp['结束日期'], errors='coerce').dt.strftime('%Y/%m/%d').fillna('')
                    save_data(edited_camp[edited_camp['档期名称'].fillna('').astype(str).str.strip() != ''], CAMP_SHEET)
                    st.success("✅ 档期已更新！"); st.rerun()
            
            st.divider()
            st.header("🛠️ 核心管理")
            with st.expander("➕ 新增产品建档 (Add SKU)"):
                with st.form("new_sku"):
                    n_name, n_color = st.text_input("产品名称"), st.text_input("颜色")
                    c1, c2, c3 = st.columns(3)
                    n_cost, n_price, n_expect = c1.number_input("进价", format="%.2f"), c2.number_input("售价", format="%.2f"), c3.number_input("应收")
                    i1, i2, i3, i4 = st.columns(4)
                    n_disp, n_shelf, n_stor, n_dmg = i1.number_input("展示"), i2.number_input("货柜"), i3.number_input("储物"), i4.number_input("坏货")
                    if st.form_submit_button("确认建档"):
                        if n_name and n_color:
                            fresh = JIT_fetch([STOCK_SHEET, RESTOCK_SHEET])
                            latest_stock, latest_restock = fresh[STOCK_SHEET], fresh[RESTOCK_SHEET]
                            total = n_disp + n_shelf + n_stor 
                            new_r = pd.DataFrame([[n_name, n_color, n_cost, n_price, n_expect, n_disp, n_shelf, n_stor, n_dmg, 0, total]], columns=STOCK_COLS)
                            latest_stock = pd.concat([latest_stock, new_r], ignore_index=True)
                            if total > 0 or n_dmg > 0:
                                log_date = datetime.now().strftime("%Y/%m/%d")
                                init_log = pd.DataFrame([[log_date, "初始建档", n_name, n_color, total+n_dmg, "多库位", n_cost, "系统建档"]], columns=RESTOCK_COLS)
                                latest_restock = pd.concat([init_log, latest_restock], ignore_index=True); save_data(latest_restock, RESTOCK_SHEET)
                            save_data(latest_stock, STOCK_SHEET); st.success("✅ 云端建档成功！"); st.rerun()
    else:
        login_type = st.radio(t("请选择您的身份", "Select Role"), [t("🧑‍💼 门店店员 / 🏭 合作厂商", "🧑‍💼 Staff / 🏭 Supplier"), t("👑 店长/管理员", "👑 Admin")], horizontal=True)
        if login_type == t("👑 店长/管理员", "👑 Admin"):
            pwd_input = st.text_input(t("输入授权密码", "Enter Admin Password"), type="password")
            if st.button(t("🔓 登录后台", "🔓 Login"), use_container_width=True):
                if pwd_input == manager_password: st.session_state.role, st.session_state.current_user = "admin", "店长"; st.query_params["role"] = "admin"; st.rerun()
                else: st.error(t("❌ 密码错误！", "❌ Incorrect Password!"))
        else:
            if df_employee.empty: st.warning(t("⚠️ 暂无人员档案。", "⚠️ No staff records."))
            else:
                active_emps = df_employee[df_employee['状态'] != '离职']['员工姓名'].tolist()
                if not active_emps: st.warning(t("⚠️ 无在职人员。", "⚠️ No active staff."))
                else:
                    emp_sel = st.selectbox(t("选择您的名字", "Select your name"), active_emps)
                    emp_row = df_employee[df_employee['员工姓名'] == emp_sel].iloc[0]
                    emp_pwd = str(emp_row['登录密码']).strip()
                    assigned_role = "supplier" if str(emp_row.get('职位', '')).strip() == '合作厂商' else "employee"
                    
                    if emp_pwd == "":
                        st.info(t("🌟 首次登录请设置 PIN 码。", "🌟 Set your PIN."))
                        new_pwd = st.text_input(t("设置我的登录密码", "Set PIN"), type="password")
                        if st.button(t("💾 保存并进入系统", "💾 Save & Login"), use_container_width=True):
                            if new_pwd.strip() == "": st.warning(t("密码不能为空！", "PIN cannot be empty!"))
                            else:
                                fresh_emp = JIT_fetch([EMP_SHEET])[EMP_SHEET]
                                e_idx = fresh_emp[fresh_emp['员工姓名'].astype(str).str.strip() == str(emp_sel).strip()].index
                                if not e_idx.empty:
                                    fresh_emp.at[e_idx[0], '登录密码'] = new_pwd
                                    save_data(fresh_emp, EMP_SHEET)
                                    st.session_state.role, st.session_state.current_user = assigned_role, emp_sel
                                    st.query_params["role"], st.query_params["user"] = assigned_role, emp_sel
                                    st.success("✅ 密码设置成功！"); st.rerun()
                    else:
                        emp_pwd_input = st.text_input(t("输入您的 PIN 码", "Enter PIN"), type="password")
                        if st.button(t("🔑 打卡/登录", "🔑 Login"), use_container_width=True):
                            if emp_pwd_input == emp_pwd:
                                st.session_state.role, st.session_state.current_user = assigned_role, emp_sel
                                st.query_params["role"], st.query_params["user"] = assigned_role, emp_sel
                                st.rerun()
                            else: st.error(t("❌ 密码不匹配！", "❌ Incorrect PIN!"))

if st.session_state.role is None:
    col_t, col_l = st.columns([8, 2])
    with col_t: st.title(t("🏙️ Takashimaya 零售管理系统", "🏙️ Takashimaya Retail System"))
    with col_l:
        lang_choice = st.radio("🌐 Language", ["中文", "English"], index=0 if st.session_state.lang == 'cn' else 1, horizontal=True)
        if (lang_choice == "中文" and st.session_state.lang != "cn") or (lang_choice == "English" and st.session_state.lang != "en"):
            st.session_state.lang = 'cn' if lang_choice == "中文" else 'en'; st.rerun()
    st.info(t("👈 请在左侧选择您的身份并完成登录。", "👈 Please select your role on the left menu to login."))
    st.stop()  

# ================= 🚀 主界面布局 =================
col_title, col_lang = st.columns([8, 2])
with col_title: st.title(t("🏙️ Takashimaya 零售管理系统 (云端同步版)", "🏙️ Takashimaya Retail System (Cloud Sync)"))
with col_lang:
    lang_choice = st.radio("🌐 Language", ["中文", "English"], index=0 if st.session_state.lang == 'cn' else 1, horizontal=True)
    if (lang_choice == "中文" and st.session_state.lang != "cn") or (lang_choice == "English" and st.session_state.lang != "en"):
        st.session_state.lang = 'cn' if lang_choice == "中文" else 'en'; st.rerun()

q = st.text_input(t("🔍 全局筛查 (输入单号/客户/商品，过滤所有看板)...", "🔍 Quick Search..."), placeholder=t("搜商品/单号/客户...", "Search items/orders/customers..."))

def get_f(df, q):
    if q and not df.empty:
        mask = pd.Series(False, index=df.index); q_cn = t_val(q, 'cn')
        for col in df.columns:
            mask = mask | df[col].fillna('').astype(str).str.contains(q, case=False, regex=False) | df[col].fillna('').astype(str).str.contains(q_cn, case=False, regex=False)
        return df[mask]
    return df

is_admin = st.session_state.role == "admin"
is_supplier = st.session_state.role == "supplier"
is_employee = st.session_state.role == "employee"

if is_admin: t1, t2, t3, t4, t5, t6, t7 = st.tabs([t("📊 库存", "📊 Inventory"), t("💰 销售", "💰 Sales"), t("📈 毛利", "📈 Gross Margin"), t("👥 考勤", "👥 Staff"), t("💎 净利润", "💎 Net Profit"), t("🤝 B2B订单", "🤝 B2B"), t("🗣️ 客户反馈", "🗣️ Feedback")]) # 去掉战略罗盘
elif is_supplier: t1, t2, t3, t4 = st.tabs([t("📊 实时库存快照", "📊 Inventory Snapshot"), t("💰 销售报表对账", "💰 Sales Report"), t("📦 进货对账 (ERP流水)", "📦 Inbound Records"), t("🤝 B2B订单对账", "🤝 B2B Orders")])
else: t1, t2, t3 = st.tabs([t("📊 实时库存查询", "📊 Inventory Snapshot"), t("🛒 智能POS收银台", "🛒 Smart POS"), t("⏰ 考勤打卡", "⏰ Timeclock")])

# ================= 🚀 公共 POS 系统核心引擎 (防丢大招) =================
def render_pos_engine(is_admin_view):
    st.subheader(t("🛒 智能 POS 收银台 (多件合并结账)", "🛒 Smart POS Cashier"))
    
    pos_col1, pos_col2 = st.columns([1.2, 1.5])
    f_opts = get_f(df_stock, "").copy() 
    if not f_opts.empty:
        f_opts['disp_name'] = translate_series(f_opts['商品名称']).fillna('').astype(str)
        f_opts['disp_color'] = translate_series(f_opts['颜色']).fillna('').astype(str)
        f_opts['label'] = f_opts['disp_name'] + " (" + f_opts['disp_color'] + ")" 
        
        with pos_col1:
            with st.container(border=True):
                st.markdown(t("#### 1️⃣ 扫码/点单区", "#### 1️⃣ Scan / Order"))
                
                # 🔥 强力秒搜功能
                search_kw = st.text_input(t("🔍 键盘输入搜商品 (自动过滤下拉菜单)", "🔍 Type to search item"), key=f"pos_search_{is_admin_view}")
                filtered_opts = f_opts[f_opts['label'].str.contains(search_kw, case=False, na=False)] if search_kw else f_opts
                
                if not filtered_opts.empty:
                    s_l = st.selectbox(t("选择商品", "Select Item"), filtered_opts['label'], key=f"pos_item_{is_admin_view}")
                    selected_row = filtered_opts[filtered_opts['label'] == s_l].iloc[0]
                    base_price = float(pd.to_numeric(selected_row['售卖价格'], errors='coerce') or 0)
                    
                    c_q, c_d = st.columns(2)
                    s_q = c_q.number_input(t("数量", "Qty"), min_value=1, value=1, step=1, key=f"pos_qty_{is_admin_view}")
                    d_opts = {"无折扣 (原价)": 1.0, "95折": 0.95, "9折": 0.90, "85折": 0.85, "8折": 0.80, "75折": 0.75, "7折": 0.70, "5折 (半价)": 0.50} if st.session_state.lang == 'cn' else {"No Discount": 1.0, "5% Off": 0.95, "10% Off": 0.90, "15% Off": 0.85, "20% Off": 0.80, "25% Off": 0.75, "30% Off": 0.70, "50% Off": 0.50}
                    s_discount = c_d.selectbox(t("折扣", "Discount"), list(d_opts.keys()), key=f"pos_disc_{is_admin_view}")
                    auto_calc_price = base_price * d_opts[s_discount]
                    
                    s_p = st.number_input(t("最终单价 ($)", "Final Price ($)"), value=float(auto_calc_price), format="%.2f", key=f"pos_final_p_{is_admin_view}")
                    
                    if st.button(t("➕ 加入购物车", "➕ Add to Cart"), use_container_width=True, key=f"btn_add_{is_admin_view}"):
                        item_dict = {
                            "real_name": str(selected_row['商品名称']),
                            "real_color": str(selected_row['颜色']),
                            "disp_name": str(selected_row['disp_name']),
                            "disp_color": str(selected_row['disp_color']),
                            "数量": s_q,
                            "单价": s_p,
                            "小计": s_q * s_p
                        }
                        st.session_state.pos_cart.append(item_dict)
                        st.rerun()
                else:
                    st.warning(t("未找到符合条件的商品。", "No item found."))

        with pos_col2:
            with st.container(border=True):
                st.markdown(t("#### 2️⃣ 当前购物车", "#### 2️⃣ Current Cart"))
                if not st.session_state.pos_cart:
                    st.info(t("🛒 购物车空空如也。", "🛒 Cart is empty."))
                else:
                    cart_df = pd.DataFrame(st.session_state.pos_cart)
                    df_disp = cart_df[['disp_name', 'disp_color', '数量', '单价', '小计']].copy()
                    df_disp.columns = ['Product', 'Variant', 'Qty', 'Price', 'Subtotal'] if st.session_state.lang == 'en' else ['商品名称', '颜色', '数量', '单价', '小计']
                    uc, sc = ('Price', 'Subtotal') if st.session_state.lang == 'en' else ('单价', '小计')
                    st.dataframe(df_disp.style.format({uc: '${:.2f}', sc: '${:.2f}'}), use_container_width=True, hide_index=True)
                    
                    cart_total_qty = cart_df['数量'].sum()
                    cart_total_amt = cart_df['小计'].sum()
                    
                    st.markdown(f"**{t('🛍️ 共计:', '🛍️ Total Qty:')}** `{cart_total_qty}` &nbsp;&nbsp;|&nbsp;&nbsp; **{t('💰 应收:', '💰 Total Pay:')}** ` ${cart_total_amt:.2f}`")
                    
                    co_col1, co_col2 = st.columns([2, 1])
                    s_d = co_col1.date_input(t("交易日期", "Date"), value=datetime.now(), key=f"pos_dt_{is_admin_view}")
                    
                    if co_col2.button(t("🗑️ 清空", "🗑️ Clear"), use_container_width=True, key=f"pos_clear_{is_admin_view}"):
                        st.session_state.pos_cart = []
                        st.rerun()
                        
                    if st.button(t("💳 确认结账 (生成流水)", "💳 Checkout"), type="primary", use_container_width=True, key=f"pos_co_{is_admin_view}"):
                        fresh = JIT_fetch([STOCK_SHEET, SALES_SHEET])
                        latest_stock = fresh[STOCK_SHEET]
                        latest_sales = fresh[SALES_SHEET]
                        
                        order_id = "ORD-" + datetime.now().strftime("%Y%m%d-%H%M%S")
                        order_date = s_d.strftime("%Y/%m/%d")
                        curr_user = st.session_state.get("current_user", "Unknown")
                        
                        new_rows = []
                        for item in st.session_state.pos_cart:
                            real_n = item['real_name']
                            real_c = item['real_color']
                            new_rows.append([order_id, order_date, curr_user, real_n, real_c, item['数量'], item['单价'], item['小计']])
                            idx_p = latest_stock[(latest_stock['商品名称'].astype(str).str.strip() == str(real_n).strip()) & (latest_stock['颜色'].astype(str).str.strip() == str(real_c).strip())].index
                            if not idx_p.empty:
                                i_p = idx_p[0]
                                latest_stock.at[i_p, '货柜数量'] = int(pd.to_numeric(latest_stock.at[i_p, '货柜数量'], errors='coerce') or 0) - item['数量']
                                latest_stock.at[i_p, '已售出数量'] = int(pd.to_numeric(latest_stock.at[i_p, '已售出数量'], errors='coerce') or 0) + item['数量']
                                latest_stock.at[i_p, '总库存'] = sum([int(pd.to_numeric(latest_stock.at[i_p, col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                        
                        new_sales_df = pd.DataFrame(new_rows, columns=SALES_COLS)
                        latest_sales = pd.concat([new_sales_df, latest_sales], ignore_index=True)
                        
                        save_data(latest_sales, SALES_SHEET) 
                        save_data(latest_stock, STOCK_SHEET) 
                        
                        st.session_state.pos_cart = []
                        st.success(t(f"🎉 结账成功！单号 {order_id}", f"🎉 Checkout Success! ID: {order_id}"))
                        st.rerun()
                        
    else:
        st.info(t("请先在库存中添加商品。", "Please add items to stock first."))

    st.divider()
    
    with st.expander(t("🚶‍♂️ 录入/修正每日有效客流", "🚶‍♂️ Daily Traffic Log"), expanded=False):
        with st.form(f"traffic_form_{is_admin_view}"):
            tc1, tc2 = st.columns(2)
            tr_date = tc1.date_input(t("📅 客流日期", "📅 Date"), value=datetime.now())
            tr_num = tc2.number_input(t("👁️ 有效咨询/看货人数", "👁️ Traffic Count"), min_value=0, step=1, value=0)
            
            if st.form_submit_button(t("💾 保存今日客流数据", "💾 Save Traffic Data"), type="primary", use_container_width=True):
                fresh_traffic = JIT_fetch([TRAFFIC_SHEET])[TRAFFIC_SHEET]
                tr_date_str = tr_date.strftime("%Y/%m/%d")
                
                idx = fresh_traffic[fresh_traffic['日期'].astype(str).str.strip() == tr_date_str].index
                if not idx.empty:
                    fresh_traffic.at[idx[0], '有效客流'] = tr_num
                else:
                    new_row = pd.DataFrame([[tr_date_str, tr_num]], columns=TRAFFIC_COLS)
                    fresh_traffic = pd.concat([new_row, fresh_traffic], ignore_index=True)
                
                save_data(fresh_traffic, TRAFFIC_SHEET)
                st.success("✅ Saved!")
                st.rerun()

    with st.expander(t("🔄 客户换货处理 (Exchange)", "🔄 Item Exchange"), expanded=False):
        if not f_opts.empty:
            xc1, xc2 = st.columns(2)
            with xc1:
                st.markdown(t("### 🔙 退回的商品 (入库)", "### 🔙 Return Item"))
                ex_ret_l = st.selectbox("1. Return Item", f_opts['label'], key=f"ex_ret_sku_{is_admin_view}")
                ret_row = f_opts[f_opts['label'] == ex_ret_l].iloc[0]
                ret_base_p = float(pd.to_numeric(ret_row['售卖价格'], errors='coerce') or 0)
                ret_p = st.number_input("2. Return Value ($)", value=ret_base_p, format="%.2f", key=f"ret_val_{is_admin_view}")
                ret_dmg = st.checkbox(t("⚠️ 退回商品有瑕疵 (记入坏货)", "⚠️ Item Damaged"), value=False, key=f"dmg_{is_admin_view}")

            with xc2:
                st.markdown(t("### 🆕 换购的商品 (出库)", "### 🆕 New Item"))
                ex_new_l = st.selectbox("1. New Item", f_opts['label'], key=f"ex_new_sku_{is_admin_view}")
                new_row = f_opts[f_opts['label'] == ex_new_l].iloc[0]
                new_base_p = float(pd.to_numeric(new_row['售卖价格'], errors='coerce') or 0)
                new_p = st.number_input("2. New Item Price ($)", value=new_base_p, format="%.2f", key=f"new_val_{is_admin_view}")

            st.markdown("---")
            
            c_date, c_diff = st.columns(2)
            with c_date:
                ex_date_input = st.date_input("📅 Date", value=datetime.now(), key=f"ex_date_input_{is_admin_view}")
            
            with c_diff:
                diff = new_p - ret_p
                if diff > 0:
                    st.warning(t(f"💰 需补差价：${diff:.2f}", f"💰 Customer Pays: ${diff:.2f}"))
                elif diff < 0:
                    st.success(t(f"💸 需退差价：${abs(diff):.2f}", f"💸 Refund Customer: ${abs(diff):.2f}"))
                else:
                    st.info(t("🤝 等价交换", "🤝 Even Exchange"))

            if st.button(t("🔄 确认执行换货", "🔄 Confirm Exchange"), type="primary", use_container_width=True, key=f"btn_exchange_{is_admin_view}"):
                fresh = JIT_fetch([STOCK_SHEET, SALES_SHEET])
                latest_stock = fresh[STOCK_SHEET]
                latest_sales = fresh[SALES_SHEET]
                
                ex_date = ex_date_input.strftime("%Y/%m/%d")
                ex_order_id = "EXC-" + datetime.now().strftime("%Y%m%d-%H%M%S") 
                curr_user = st.session_state.get("current_user", "Unknown")
                
                r_name = t_val(ret_row['disp_name'], 'cn')
                r_col = t_val(ret_row['disp_color'], 'cn')
                n_name = t_val(new_row['disp_name'], 'cn')
                n_col = t_val(new_row['disp_color'], 'cn')
                
                idx_ret = latest_stock[(latest_stock['商品名称'].astype(str).str.strip() == str(r_name).strip()) & (latest_stock['颜色'].astype(str).str.strip() == str(r_col).strip())].index[0]
                s_ret = pd.DataFrame([[ex_order_id, ex_date, curr_user, latest_stock.at[idx_ret,'商品名称'], latest_stock.at[idx_ret,'颜色'], -1, ret_p, -1 * ret_p]], columns=SALES_COLS)
                
                idx_new = latest_stock[(latest_stock['商品名称'].astype(str).str.strip() == str(n_name).strip()) & (latest_stock['颜色'].astype(str).str.strip() == str(n_col).strip())].index[0]
                s_new = pd.DataFrame([[ex_order_id, ex_date, curr_user, latest_stock.at[idx_new,'商品名称'], latest_stock.at[idx_new,'颜色'], 1, new_p, 1 * new_p]], columns=SALES_COLS)
                
                latest_sales = pd.concat([s_new, s_ret, latest_sales], ignore_index=True)
                
                if ret_dmg:
                    latest_stock.at[idx_ret, '坏货数量'] = int(pd.to_numeric(latest_stock.at[idx_ret, '坏货数量'], errors='coerce') or 0) + 1
                else:
                    latest_stock.at[idx_ret, '货柜数量'] = int(pd.to_numeric(latest_stock.at[idx_ret, '货柜数量'], errors='coerce') or 0) + 1
                    latest_stock.at[idx_ret, '总库存'] = sum([int(pd.to_numeric(latest_stock.at[idx_ret, col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                latest_stock.at[idx_ret, '已售出数量'] = int(pd.to_numeric(latest_stock.at[idx_ret, '已售出数量'], errors='coerce') or 0) - 1
                
                latest_stock.at[idx_new, '货柜数量'] = int(pd.to_numeric(latest_stock.at[idx_new, '货柜数量'], errors='coerce') or 0) - 1
                latest_stock.at[idx_new, '已售出数量'] = int(pd.to_numeric(latest_stock.at[idx_new, '已售出数量'], errors='coerce') or 0) + 1
                latest_stock.at[idx_new, '总库存'] = sum([int(pd.to_numeric(latest_stock.at[idx_new, col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                
                save_data(latest_sales, SALES_SHEET) 
                save_data(latest_stock, STOCK_SHEET) 
                st.success("✅ Exchange Success!")
                st.rerun()

    st.divider()
    
    # 🔥 角色隔离：如果是店长，显示修改功能；如果是店员，只读今天流水
    if is_admin_view:
        st.markdown("### 📝 销售流水编辑与防飞单机制")
        f_sl = get_f(df_sales, q)
        if not f_sl.empty:
            f_sl_sel = f_sl.copy()
            f_sl_sel.insert(0, "选择", False)
            f_sl_sel['成交单价'] = pd.to_numeric(f_sl_sel['成交单价'], errors='coerce').fillna(0.0)
            f_sl_sel['总营业额'] = pd.to_numeric(f_sl_sel['总营业额'], errors='coerce').fillna(0.0)
            
            f_sl_sel['商品名称'] = translate_series(f_sl_sel['商品名称'])
            f_sl_sel['颜色'] = translate_series(f_sl_sel['颜色'])
            
            sel_col_name = "Sel" if st.session_state.lang == 'en' else "选择"
            if st.session_state.lang == 'en': f_sl_sel.rename(columns=col_map, inplace=True); f_sl_sel.rename(columns={"选择": sel_col_name}, inplace=True)
            
            u_col = 'Unit Price' if st.session_state.lang == 'en' else '成交单价'
            t_col = 'Total Amount' if st.session_state.lang == 'en' else '总营业额'
            
            styled_sl = f_sl_sel.style.format({u_col: '${:.2f}', t_col: '${:.2f}'})
            d_disable = [c for c in f_sl_sel.columns if c not in ["选择", "Sel"]]
            
            edt = st.data_editor(
                styled_sl, 
                column_config={sel_col_name: st.column_config.CheckboxColumn(sel_col_name, default=False)}, 
                disabled=d_disable, 
                use_container_width=True, hide_index=True, 
                key=f"sales_editor_{st.session_state.sales_reset_key}"
            )
            
            sel = edt[edt[sel_col_name] == True] if sel_col_name in edt.columns else pd.DataFrame()
            
            if not sel.empty:
                sc1, sc2, _ = st.columns([1.5, 1.5, 4])
                with sc1:
                    if st.button("🔴 批量撤销流水", type="primary"):
                        fresh = JIT_fetch([STOCK_SHEET, SALES_SHEET])
                        latest_stock = fresh[STOCK_SHEET]
                        latest_sales = fresh[SALES_SHEET]
                        
                        for _, r in sel.iterrows():
                            real_n = t_val(r['Product' if st.session_state.lang == 'en' else '商品名称'], 'cn')
                            real_c = t_val(r['Variant' if st.session_state.lang == 'en' else '颜色'], 'cn')
                            q_val = int(pd.to_numeric(r['Qty' if st.session_state.lang == 'en' else '销售数量'], errors='coerce') or 0)
                            
                            m = latest_stock[(latest_stock['商品名称'].astype(str).str.strip() == str(real_n).strip()) & (latest_stock['颜色'].astype(str).str.strip() == str(real_c).strip())].index
                            if not m.empty:
                                latest_stock.at[m[0], '货柜数量'] = int(pd.to_numeric(latest_stock.at[m[0], '货柜数量'], errors='coerce') or 0) + q_val
                                latest_stock.at[m[0], '已售出数量'] = int(pd.to_numeric(latest_stock.at[m[0], '已售出数量'], errors='coerce') or 0) - q_val
                                latest_stock.at[m[0], '总库存'] = sum([int(pd.to_numeric(latest_stock.at[m[0], col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                            
                            o_id = str(r['Order ID' if st.session_state.lang == 'en' else '订单号']).strip()
                            o_dt = str(r['Date' if st.session_state.lang == 'en' else '日期']).strip()
                            
                            cond = (latest_sales['订单号'].astype(str).str.strip() == o_id) & \
                                   (latest_sales['商品名称'].astype(str).str.strip() == str(real_n).strip()) & \
                                   (latest_sales['颜色'].astype(str).str.strip() == str(real_c).strip()) & \
                                   (pd.to_numeric(latest_sales['销售数量'], errors='coerce').fillna(0).astype(int) == q_val)
                            latest_sales = latest_sales[~cond]
                        
                        save_data(latest_stock, STOCK_SHEET)
                        save_data(latest_sales, SALES_SHEET)
                        st.session_state.sales_reset_key += 1
                        st.rerun()
                with sc2: 
                    st.button("🔄 取消所有选中", key="btn_cancel_sales", on_click=clear_sales)

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
                            latest_stock = fresh[STOCK_SHEET]
                            latest_sales = fresh[SALES_SHEET]
                            
                            cond = (latest_sales['订单号'].astype(str).str.strip() == o_id) & \
                                   (latest_sales['商品名称'].astype(str).str.strip() == str(real_n).strip()) & \
                                   (latest_sales['颜色'].astype(str).str.strip() == str(real_c).strip()) & \
                                   (pd.to_numeric(latest_sales['销售数量'], errors='coerce').fillna(0).astype(int) == o_qty)
                            
                            true_idx = latest_sales[cond].index
                            if not true_idx.empty:
                                t_idx = true_idx[0]
                                m_old = latest_stock[(latest_stock['商品名称'].astype(str).str.strip() == str(real_n).strip()) & (latest_stock['颜色'].astype(str).str.strip() == str(real_c).strip())].index
                                if not m_old.empty:
                                    latest_stock.at[m_old[0], '货柜数量'] = int(pd.to_numeric(latest_stock.at[m_old[0], '货柜数量'], errors='coerce') or 0) + o_qty
                                    latest_stock.at[m_old[0], '已售出数量'] = int(pd.to_numeric(latest_stock.at[m_old[0], '已售出数量'], errors='coerce') or 0) - o_qty
                                    latest_stock.at[m_old[0], '总库存'] = sum([int(pd.to_numeric(latest_stock.at[m_old[0], col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                                    
                                new_n = t_val(e_prod.rsplit(" (", 1)[0], 'cn')
                                new_c = t_val(e_prod.rsplit(" (", 1)[1].replace(")", ""), 'cn')
                                
                                m_new = latest_stock[(latest_stock['商品名称'].astype(str).str.strip() == str(new_n).strip()) & (latest_stock['颜色'].astype(str).str.strip() == str(new_c).strip())].index
                                if not m_new.empty:
                                    latest_stock.at[m_new[0], '货柜数量'] = int(pd.to_numeric(latest_stock.at[m_new[0], '货柜数量'], errors='coerce') or 0) - e_qty
                                    latest_stock.at[m_new[0], '已售出数量'] = int(pd.to_numeric(latest_stock.at[m_new[0], '已售出数量'], errors='coerce') or 0) + e_qty
                                    latest_stock.at[m_new[0], '总库存'] = sum([int(pd.to_numeric(latest_stock.at[m_new[0], col], errors='coerce') or 0) for col in ['展示数量', '货柜数量', '储物间数量']])
                                    
                                latest_sales.at[t_idx, '日期'] = e_date.strftime("%Y/%m/%d")
                                latest_sales.at[t_idx, '商品名称'] = new_n
                                latest_sales.at[t_idx, '颜色'] = new_c
                                latest_sales.at[t_idx, '销售数量'] = e_qty
                                latest_sales.at[t_idx, '成交单价'] = e_price
                                latest_sales.at[t_idx, '总营业额'] = e_qty * e_price
                                
                                save_data(latest_stock, STOCK_SHEET)
                                save_data(latest_sales, SALES_SHEET)
                                st.session_state.sales_reset_key += 1
                                st.success("✅ 修改成功！"); st.rerun()
                            else:
                                st.error("⚠️ 未在云端找到该流水！可能是已被删除或数量有偏差。")
        else:
            st.info("No logs.")
    else:
        st.markdown(t("### 📝 今日流水 (只读)", "### 📝 Today's Logs (Read-only)"))
        f_sl = get_f(df_sales, q)
        if not f_sl.empty:
            today_str = datetime.now().strftime("%Y/%m/%d")
            today_sales = f_sl[f_sl['日期'] == today_str].copy()
            if not today_sales.empty:
                today_sales['成交单价'] = pd.to_numeric(today_sales['成交单价'], errors='coerce').fillna(0.0)
                today_sales['总营业额'] = pd.to_numeric(today_sales['总营业额'], errors='coerce').fillna(0.0)
                
                today_sales['商品名称'] = translate_series(today_sales['商品名称'])
                today_sales['颜色'] = translate_series(today_sales['颜色'])
                if st.session_state.lang == 'en': today_sales.rename(columns=col_map, inplace=True)
                
                u_col = 'Unit Price' if st.session_state.lang == 'en' else '成交单价'
                t_col = 'Total Amount' if st.session_state.lang == 'en' else '总营业额'
                st.dataframe(today_sales.style.format({u_col: '${:.2f}', t_col: '${:.2f}'}), use_container_width=True, hide_index=True)
            else:
                st.write(t("今日尚未产生流水。", "No records for today."))

if is_admin:
    with t2:
        # 已通过 render_pos_engine 完成
        render_pos_engine(is_admin_view=True)

    with t3:
        st.subheader("📊 财务与客流报表")
        
        t3_start = st.session_state.camp_start
        t3_end = st.session_state.camp_end
        st.info(f"📅 此看板的财务数据已随左侧全局控制器锁定在：**{t3_start}** 至 **{t3_end}**")

        if not df_sales.empty:
            df_sales['日期_dt'] = pd.to_datetime(df_sales['日期'], errors='coerce')
            df_sales_clean = df_sales.dropna(subset=['日期_dt']).copy()
            
            if not df_sales_clean.empty:
                f_sales_range = df_sales_clean[(df_sales_clean['日期_dt'] >= pd.Timestamp(t3_start)) & (df_sales_clean['日期_dt'] <= pd.Timestamp(t3_end))].copy()
                
                f_sales_range['销售数量'] = pd.to_numeric(f_sales_range['销售数量'], errors='coerce').fillna(0)
                f_sales_range['总营业额'] = pd.to_numeric(f_sales_range['总营业额'], errors='coerce').fillna(0.0)
                
                df_stock_calc = df_stock[['商品名称', '颜色', '进价成本']].copy()
                df_stock_calc['进价成本'] = pd.to_numeric(df_stock_calc['进价成本'], errors='coerce').fillna(0.0)
                f_sales_range = f_sales_range.merge(df_stock_calc, on=['商品名称', '颜色'], how='left')
                f_sales_range['具体毛利'] = f_sales_range['总营业额'] - (f_sales_range['销售数量'] * f_sales_range['进价成本'])
                
                f_sales_range = get_f(f_sales_range, q)
                
                if not f_sales_range.empty:
                    tot_rev = f_sales_range['总营业额'].sum()
                    tot_items = f_sales_range['销售数量'].sum()
                    tot_margin = f_sales_range['具体毛利'].sum()
                    
                    valid_orders = f_sales_range[
                        (~f_sales_range['订单号'].str.contains('历史单', na=False)) & 
                        (~f_sales_range['订单号'].str.contains('EXC-', na=False))
                    ]
                    order_count = valid_orders['订单号'].nunique()
                    
                    legacy_orders = f_sales_range[f_sales_range['订单号'].str.contains('历史单', na=False)]
                    total_order_count = order_count + len(legacy_orders)
                    
                    df_traffic_clean = df_traffic.copy()
                    if not df_traffic_clean.empty:
                        df_traffic_clean['日期_dt'] = pd.to_datetime(df_traffic_clean['日期'], errors='coerce')
                        f_traffic_range = df_traffic_clean[(df_traffic_clean['日期_dt'] >= pd.Timestamp(t3_start)) & (df_traffic_clean['日期_dt'] <= pd.Timestamp(t3_end))]
                        total_traffic = pd.to_numeric(f_traffic_range['有效客流'], errors='coerce').fillna(0).sum()
                    else:
                        total_traffic = 0
                        
                    conv_rate = (total_order_count / total_traffic * 100) if total_traffic > 0 else 0.0
                    acv = tot_rev / total_order_count if total_order_count > 0 else 0
                    upt = tot_items / total_order_count if total_order_count > 0 else 0
                    
                    period = st.radio("维度", ["Daily", "Weekly", "Monthly"], horizontal=True)
                    if "Daily" in period: f_sales_range['周期'] = f_sales_range['日期_dt'].dt.strftime('%Y/%m/%d')
                    elif "Weekly" in period: f_sales_range['周期'] = (f_sales_range['日期_dt'] - pd.to_timedelta(f_sales_range['日期_dt'].dt.dayofweek, unit='D')).dt.strftime('Week of %b %d')
                    else: f_sales_range['周期'] = f_sales_range['日期_dt'].dt.strftime('%Y/%m')
                    
                    summ = f_sales_range.groupby(['周期', '商品名称', '颜色']).agg({'销售数量':'sum', '总营业额':'sum', '具体毛利':'sum'}).reset_index()
                    
                    delta_days = (t3_end - t3_start).days + 1
                    
                    st.markdown(f"### 🏬 核心客流漏斗矩阵 {f'(已过滤: {q})' if q else ''}")
                    m1, m2, m3 = st.columns(3)
                    m1.metric("👁️ 有效总客流", f"{int(total_traffic)} 人")
                    m2.metric("💳 交易单数", f"{total_order_count} 单")
                    m3.metric("🔄 购买转化率", f"{conv_rate:.1f}%")
                    
                    st.divider()
                    
                    m4, m5, m6 = st.columns(3)
                    m4.metric("💰 总营业额", f"${tot_rev:.2f}")
                    m5.metric("🛒 平均客单价 (ACV)", f"${acv:.2f}")
                    m6.metric("🛍️ 连带率 (UPT)", f"{upt:.2f} 件/单")
                    
                    st.divider()
                    
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("具体毛利", f"${tot_margin:.2f}")
                    c2.metric("总售出件数", f"{int(tot_items)} 件")
                    
                    avg_m = tot_margin / tot_rev * 100 if tot_rev > 0 else 0
                    c3.metric("平均毛利率", f"{avg_m:.1f}%")
                    
                    avg_daily = tot_rev / delta_days if delta_days > 0 else 0
                    c4.metric("日均坪效 (每日营收)", f"${avg_daily:.2f}")
                    
                    st.divider()
                    st.markdown("### 📈 营收与毛利走势")
                    chart_data_t3 = summ.groupby('周期')[['总营业额', '具体毛利']].sum().sort_index(ascending=True)
                    st.bar_chart(chart_data_t3, use_container_width=True)

                    dl_c1, dl_c2 = st.columns([1, 4])
                    with dl_c1:
                        csv_t3 = convert_df_to_csv(summ)
                        st.download_button(
                            label="⬇️ 一键导出毛利报表 (CSV)",
                            data=csv_t3,
                            file_name=f"Takashimaya_毛利报表_{datetime.now().strftime('%Y%m%d')}.csv",
                            mime="text/csv",
                            type="primary"
                        )
                    
                    st.dataframe(summ.sort_values('周期', ascending=False).style.format({'总营业额':"${:.2f}", '具体毛利':"${:.2f}", '销售数量':"{:d}"}), use_container_width=True)
                else:
                    st.info("💡 在选定时间段内没有找到符合条件的记录。")
            else:
                st.info("流水表中无有效数据。")

    with t4:
        st.subheader("👥 员工档案与门禁管理")
        with st.expander("➕ 新增人员档案 (含合作厂商)", expanded=False):
            with st.form("add_employee"):
                c1, c2 = st.columns(2)
                e_name = c1.text_input("人员姓名")
                e_role = c2.selectbox("身份职位", ["店长", "全职店员", "兼职店员", "实习生", "合作厂商", "其他"])
                c3, c4, c5 = st.columns(3)
                e_wage = c3.number_input("时薪 ($/小时, 厂商填0)", min_value=0.0, step=0.5, value=12.0, format="%.2f")
                e_phone = c4.text_input("联系方式 (选填)")
                e_date = c5.date_input("入职/开通日期", value=datetime.now())
                if st.form_submit_button("保存人员信息"):
                    if e_name.strip() == "": st.warning("⚠️ 姓名不能为空！")
                    elif e_name in df_employee['员工姓名'].values: st.warning(f"⚠️ 人员 {e_name} 已经存在！")
                    else:
                        fresh_emp = JIT_fetch([EMP_SHEET])[EMP_SHEET]
                        new_emp = pd.DataFrame([[e_name, e_role, e_wage, e_phone, e_date.strftime("%Y/%m/%d"), "", "在职"]], columns=EMP_COLS)
                        fresh_emp = pd.concat([fresh_emp, new_emp], ignore_index=True)
                        save_data(fresh_emp, EMP_SHEET) 
                        st.session_state.emp_reset_key += 1
                        st.rerun()

        f_employee = get_f(df_employee, q) 
        if not f_employee.empty:
            v_emp = f_employee.copy()
            v_emp.insert(0, "选择", False)
            
            v_emp['时薪'] = pd.to_numeric(v_emp['时薪'], errors='coerce').fillna(0.0)
            styled_emp = v_emp.style.format({'时薪': '${:.2f}'})
            
            editor_key = f"emp_editor_{st.session_state.emp_reset_key}"
            edited_emp = st.data_editor(
                styled_emp, 
                column_config={
                    "选择": st.column_config.CheckboxColumn("选择", default=False),
                    "状态": st.column_config.SelectboxColumn("在离职状态", options=["在职", "离职"]),
                    "登录密码": st.column_config.TextColumn("登录密码 (店长清空后，人员可重新设置)")
                }, 
                disabled=['员工姓名', '入职日期'], 
                use_container_width=True, hide_index=True, key=editor_key
            )
            
            editor_state = st.session_state.get(editor_key, {})
            if editor_state.get("edited_rows"):
                has_real_edits = False
                fresh_emp = JIT_fetch([EMP_SHEET])[EMP_SHEET]
                for idx, row in edited_emp.iterrows():
                    is_changed = False
                    for c in EMP_COLS:
                        if str(row[c]) != str(v_emp.loc[idx, c]):
                            is_changed = True
                            break
                    if is_changed:
                        has_real_edits = True
                        for col in EMP_COLS:
                            fresh_emp.at[idx, col] = row[col]
                if has_real_edits:
                    save_data(fresh_emp, EMP_SHEET)
                    st.success("✅ 人员档案修改已保存！")
                    st.session_state.emp_reset_key += 1
                    st.rerun()
            
            selected_emp = edited_emp[edited_emp["选择"] == True]
            if not selected_emp.empty:
                col_btn1, col_btn2, _ = st.columns([1.5, 1.5, 4])
                with col_btn1:
                    if st.button("🗑️ 彻底删除人员 (不建议)", type="primary", key="del_emp"):
                        fresh_emp = JIT_fetch([EMP_SHEET])[EMP_SHEET]
                        for _, row in selected_emp.iterrows():
                            fresh_emp = fresh_emp[fresh_emp['员工姓名'].astype(str).str.strip() != str(row['员工姓名']).strip()]
                        save_data(fresh_emp, EMP_SHEET)
                        st.session_state.emp_reset_key += 1; st.rerun()
                with col_btn2: st.button("🔄 取消所有选中", key="btn_cancel_emp", on_click=clear_emp)

        st.divider()
        st.subheader("⏰ 排班与打卡记录")
        
        if df_employee.empty:
            st.info("💡 请先在上方添加人员。")
        else:
            with st.expander("➕ 帮员工补录打卡", expanded=True):
                with st.form("add_attendance_admin"):
                    c1, c2 = st.columns(2)
                    att_name = c1.selectbox("选择员工", df_employee['员工姓名'].astype(str).tolist())
                    att_date = c2.date_input("工作日期", value=datetime.now())
                    
                    c3, c4 = st.columns(2)
                    att_start = c3.time_input("上班时间", value=time(10, 0))
                    att_end = c4.time_input("下班时间", value=time(18, 0))
                    
                    if st.form_submit_button("确认记录考勤"):
                        fresh_att = JIT_fetch([ATT_SHEET])[ATT_SHEET]
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
                        
                        fresh_att = pd.concat([new_att, fresh_att], ignore_index=True)
                        save_data(fresh_att, ATT_SHEET) 
                        
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
                            fresh_att = JIT_fetch([ATT_SHEET])[ATT_SHEET]
                            for _, row in selected_att.iterrows():
                                fresh_att = fresh_att[~((fresh_att['员工姓名'].astype(str).str.strip() == str(row['员工姓名']).strip()) & (fresh_att['日期'].astype(str).str.strip() == str(row['日期']).strip()) & (fresh_att['开始时间'].astype(str).str.strip() == str(row['开始时间']).strip()))]
                            save_data(fresh_att, ATT_SHEET)
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
        st.subheader(f"💎 真实净利润核算 (9% GST 剥离版)")
        
        t5_start = st.session_state.camp_start
        t5_end = st.session_state.camp_end
        st.info(f"📅 此看板的净利数据已随左侧全局控制器锁定在：**{t5_start}** 至 **{t5_end}**")

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
                fs = df_s_np[(df_s_np['日期_dt'] >= pd.Timestamp(t5_start)) & (df_s_np['日期_dt'] <= pd.Timestamp(t5_end))].copy()
                fa = df_a_np[(df_a_np['日期_dt'] >= pd.Timestamp(t5_start)) & (df_a_np['日期_dt'] <= pd.Timestamp(t5_end))].copy()

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

                daily_np['免税净营业额'] = daily_np['总营业额'] / 1.09
                daily_np['代扣GST(9%)'] = daily_np['总营业额'] - daily_np['免税净营业额']
                daily_np['商场抽成(36%)'] = daily_np['免税净营业额'] * 0.36
                daily_np['商场实际回款'] = daily_np['免税净营业额'] - daily_np['商场抽成(36%)']
                daily_np['毛利润'] = daily_np['商场实际回款'] - daily_np['总进价成本']
                daily_np['真实净利润'] = daily_np['毛利润'] - daily_np['人工成本']

                tot_gross = daily_np['总营业额'].sum()
                tot_net_rev = daily_np['免税净营业额'].sum()
                tot_gst = daily_np['代扣GST(9%)'].sum()
                tot_comm = daily_np['商场抽成(36%)'].sum()
                tot_settlement = daily_np['商场实际回款'].sum()
                tot_cogs = daily_np['总进价成本'].sum()
                tot_wage = daily_np['人工成本'].sum()
                tot_net = daily_np['真实净利润'].sum()

                pct_gst = (tot_gst / tot_gross * 100) if tot_gross > 0 else 0
                pct_comm = (tot_comm / tot_gross * 100) if tot_gross > 0 else 0
                pct_cogs = (tot_cogs / tot_gross * 100) if tot_gross > 0 else 0
                pct_wage = (tot_wage / tot_gross * 100) if tot_gross > 0 else 0
                pct_net = (tot_net / tot_gross * 100) if tot_gross > 0 else 0

                st.info("💡 财务脱水逻辑：顾客支付的含税总额中，9% 为政府消费税 (GST)。高岛屋的 36% 抽成基于**免税净额**计算。实际回款 = 免税净额 - 抽成。")
                
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("💰 选中期间总营业额", f"${tot_gross:.2f}", delta="100.0% (营收基准)", delta_color="off")
                m2.metric("🏛️ 剥离 GST (9%)", f"${tot_gst:.2f}", delta=f"占比: {pct_gst:.1f}%", delta_color="off")
                m3.metric("📉 商场抽成 (36%)", f"${tot_comm:.2f}", delta=f"占比: {pct_comm:.1f}%", delta_color="off")
                m4.metric("💵 商场实际回款", f"${tot_settlement:.2f}", help="免税额减去抽成后，高岛屋真正打给你的钱")
                
                st.divider()
                
                m5, m6, m7, m8 = st.columns(4)
                m5.metric("📦 商品进价成本", f"${tot_cogs:.2f}", delta=f"占比: {pct_cogs:.1f}%", delta_color="off")
                m6.metric("👥 打卡人工成本", f"${tot_wage:.2f}", delta=f"占比: {pct_wage:.1f}%", delta_color="off")
                m7.metric("💎 选中期间纯利润", f"${tot_net:.2f}", delta=f"含税净利率: {pct_net:.1f}%", delta_color="normal")
                m8.empty()

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
                
                format_dict = {
                    '总营业额': '${:.2f}', '免税净营业额': '${:.2f}', '代扣GST(9%)': '${:.2f}',
                    '商场抽成(36%)': '${:.2f}', '商场实际回款': '${:.2f}',
                    '总进价成本': '${:.2f}', '人工成本': '${:.2f}',
                    '毛利润': '${:.2f}', '真实净利润': '${:.2f}'
                }
                
                try:
                    styled_np = show_np.style.format(format_dict).map(color_net_profit, subset=['真实净利润'])
                except AttributeError:
                    styled_np = show_np.style.format(format_dict).applymap(color_net_profit, subset=['真实净利润'])

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
                    f_opts_b2b['dn'] = translate_series(f_opts_b2b['商品名称']).fillna('').astype(str)
                    f_opts_b2b['dc'] = translate_series(f_opts_b2b['颜色']).fillna('').astype(str)
                    f_opts_b2b['label'] = f_opts_b2b['dn'] + " (" + f_opts_b2b['dc'] + ")" 
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
                        sel_disp_name = b2b_prod.rsplit(" (", 1)[0]
                        sel_disp_color = b2b_prod.rsplit(" (", 1)[1].replace(")", "")
                        final_name = t_val(sel_disp_name, 'cn')
                        final_color = t_val(sel_disp_color, 'cn')
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
                    fresh_b2b = JIT_fetch([B2B_SHEET])[B2B_SHEET]
                    
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

                    fresh_b2b = pd.concat([new_b2b, fresh_b2b], ignore_index=True)
                    save_data(fresh_b2b, B2B_SHEET)
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
                fresh_b2b = JIT_fetch([B2B_SHEET])[B2B_SHEET]
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
                                fresh_b2b.at[idx, col] = row[col]
                        
                        total_receivable = float(row['总计应收'] or 0)
                        deposit = float(row['已收定金'] or 0)
                        fresh_b2b.at[idx, '待收尾款'] = total_receivable - deposit
                        
                if has_real_edits:
                    save_data(fresh_b2b[B2B_COLS], B2B_SHEET) 
                    st.success("✅ B2B 订单修改已全量精准保存！")
                    st.session_state.b2b_reset_key += 1
                    st.rerun()

            selected_b2b = edited_b2b[edited_b2b["选择"] == True]
            if not selected_b2b.empty:
                bc1, bc2, _ = st.columns([1.5, 1.5, 4])
                with bc1:
                    if st.button("🗑️ 删除选中订单", type="primary", key="del_b2b"):
                        fresh_b2b = JIT_fetch([B2B_SHEET])[B2B_SHEET]
                        for _, row in selected_b2b.iterrows():
                            fresh_b2b = fresh_b2b[~((fresh_b2b['客户名称'].astype(str).str.strip() == str(row['客户名称']).strip()) & (fresh_b2b['商品名称'].astype(str).str.strip() == str(row['商品名称']).strip()) & (fresh_b2b['创建日期'].astype(str).str.strip() == str(row['创建日期']).strip()))]
                        save_data(fresh_b2b[B2B_COLS], B2B_SHEET)
                        st.session_state.b2b_reset_key += 1 
                        st.rerun()
                with bc2: st.button("🔄 取消选中", key="btn_cancel_b2b", on_click=clear_b2b)
        else:
            st.info("💡 暂无 B2B 订单记录或没有找到符合搜索条件的订单。")

    with t7:
        st.subheader("🗣️ 新加坡本地客户产品反馈池")
        
        fb_type_options = ["产品功能性", "产品优化", "保温保冷效能", "外观颜值 / 颜色", "材质手感 / 重量", "清洗 / 异味问题", "杯盖 / 密封性", "价格因素", "🌏 本土化优化 (非产品)", "夸奖 / 好评", "其他建议"]
        fb_customer_options = ["本地散客", "VIP / 老客复购", "送礼需求", "游客", "B2B企业客户"]
        fb_status_options = ["🚨 待处理 / 待评估", "📝 已记录 / 待反馈工厂", "✅ 已解决 / 已采纳"]

        with st.expander("➕ 快速录入新反馈", expanded=True):
            f_opts_fb = get_f(df_stock, "").copy()
            with st.form("add_feedback"):
                c1, c2 = st.columns(2)
                fb_date = c1.date_input("反馈日期", value=datetime.now())
                if not f_opts_fb.empty: fb_prod = c2.selectbox("提及的商品", f_opts_fb['商品名称'].unique().tolist() + ["全系产品 / 通用"])
                else: fb_prod = c2.text_input("提及的商品", "全系产品 / 通用")

                c3, c4 = st.columns(2)
                fb_type = c3.selectbox("反馈痛点 / 类型", fb_type_options)
                fb_customer = c4.selectbox("客户画像", fb_customer_options)
                fb_detail = st.text_area("🗣️ 客户原话或详细描述")
                fb_status = st.selectbox("当前跟进状态", fb_status_options)

                if st.form_submit_button("保存客户反馈", type="primary", use_container_width=True):
                    if fb_detail.strip() == "": st.warning("⚠️ 详细反馈内容不能为空！")
                    else:
                        fresh_fb = JIT_fetch([FEEDBACK_SHEET])[FEEDBACK_SHEET]
                        new_fb = pd.DataFrame([[fb_date.strftime("%Y/%m/%d"), fb_prod, fb_customer, fb_type, fb_detail, fb_status]], columns=FEEDBACK_COLS)
                        fresh_fb = pd.concat([new_fb, fresh_fb], ignore_index=True)
                        save_data(fresh_fb, FEEDBACK_SHEET); st.success("✅ 宝贵的一线反馈已入库！"); st.rerun()

        st.divider()
        f_fb = get_f(df_feedback, q)
        if not f_fb.empty:
            fb_c1, fb_c2 = st.columns(2)
            with fb_c1:
                st.markdown("**📌 哪些痛点被疯狂吐槽？**")
                st.bar_chart(f_fb['反馈类型'].value_counts())
            with fb_c2:
                st.markdown("**📌 哪款产品话题度最高？**")
                st.bar_chart(f_fb['商品名称'].value_counts())

            v_fb = f_fb.copy()
            v_fb.insert(0, "选择", False)
            editor_key = f"fb_editor_{st.session_state.fb_reset_key}"
            edited_fb = st.data_editor(v_fb, column_config={"选择": st.column_config.CheckboxColumn("选择", default=False), "跟进状态": st.column_config.SelectboxColumn("跟进状态", options=fb_status_options), "反馈类型": st.column_config.SelectboxColumn("反馈类型", options=fb_type_options), "客户画像": st.column_config.SelectboxColumn("客户画像", options=fb_customer_options)}, disabled=[], use_container_width=True, hide_index=True, key=editor_key)

            if st.session_state.get(editor_key, {}).get("edited_rows"):
                has_real_edits = False
                fresh_fb = JIT_fetch([FEEDBACK_SHEET])[FEEDBACK_SHEET]
                for idx, row in edited_fb.iterrows():
                    is_changed = False
                    for c in FEEDBACK_COLS:
                        if str(row[c]) != str(v_fb.loc[idx, c]):
                            is_changed = True
                            break
                    if is_changed:
                        has_real_edits = True
                        for col in FEEDBACK_COLS:
                            fresh_fb.at[idx, col] = row[col]
                if has_real_edits:
                    save_data(fresh_fb, FEEDBACK_SHEET)
                    st.success("✅ 客户反馈修改已全量精准保存！")
                    st.session_state.fb_reset_key += 1
                    st.rerun()

            selected_fb = edited_fb[edited_fb["选择"] == True]
            if not selected_fb.empty:
                fbc1, fbc2, _ = st.columns([1.5, 1.5, 4])
                with fbc1:
                    if st.button("🗑️ 删除选中反馈", type="primary", key="del_fb"):
                        fresh_fb = JIT_fetch([FEEDBACK_SHEET])[FEEDBACK_SHEET]
                        for _, row in selected_fb.iterrows():
                            fresh_fb = fresh_fb[~((fresh_fb['详细原话'].astype(str).str.strip() == str(row['详细原话']).strip()) & (fresh_fb['反馈日期'].astype(str).str.strip() == str(row['反馈日期']).strip()) & (fresh_fb['商品名称'].astype(str).str.strip() == str(row['商品名称']).strip()))]
                        save_data(fresh_fb, FEEDBACK_SHEET)
                        st.session_state.fb_reset_key += 1
                        st.rerun()
                with fbc2: st.button("🔄 取消选中", key="btn_cancel_fb", on_click=clear_fb)
        else:
            st.info("💡 暂无客户反馈记录或没有找到符合条件的反馈。")

# ================= 🚀 Tab 3/4: 厂商专属层 (Supplier) =================
elif is_supplier:
    with t3:
        st.subheader(t("📦 进货与入库对账单 (ERP 底单)", "📦 Inbound Records"))
        
        # 🔥 全局接管：隐藏独立的日期选择器，直接显示左侧锁定的档期时间
        r_s = st.session_state.camp_start
        r_e = st.session_state.camp_end
        st.info(f"📅 此对账单已随左侧全局控制器锁定在：**{r_s}** 至 **{r_e}**")
        
        if not df_restock.empty:
            dr = df_restock.copy()
            dr['dt'] = pd.to_datetime(dr['记录日期'], errors='coerce')
            dr = dr.dropna(subset=['dt'])
            if not dr.empty:
                fr = dr[(dr['dt'].dt.date >= r_s) & (dr['dt'].dt.date <= r_e)]
                fr = get_f(fr, q)
                
                if not fr.empty:
                    fr['操作类型'] = translate_series(fr['操作类型'])
                    
                    a_ops = [str(x) for x in fr['操作类型'].fillna('').unique().tolist() if str(x).strip() != '']
                    s_defs = list(set([op for op in [t_val("入库", "en"), t_val("初始建档", "en"), "入库", "初始建档"] if op in a_ops]))
                    
                    tf = st.multiselect(t("筛选操作类型", "Filter Ops"), options=a_ops, default=s_defs)
                    if tf:
                        fr = fr[fr['操作类型'].isin(tf)]
                        fr['商品名称'] = translate_series(fr['商品名称'])
                        fr['颜色'] = translate_series(fr['颜色'])
                        
                        tot_i = fr['变动数量'].apply(lambda x: pd.to_numeric(x, errors='coerce')).fillna(0).sum()
                        st.metric(t("🚛 筛选后累计变动数量", "🚛 Total Qty"), f"{int(tot_i)}")
                        
                        show_cols = ['记录日期', '操作类型', '商品名称', '颜色', '变动数量', '库位详情', '备注']
                        df_disp = fr[show_cols].copy()
                        if st.session_state.lang == 'en': df_disp.rename(columns=col_map, inplace=True)
                        st.dataframe(df_disp, use_container_width=True, hide_index=True)
                    else:
                        st.info(t("无对应类型的记录。", "No records matched."))
                else:
                    st.info(t("该区间无对账记录。", "No records in range."))

    with t4:
        st.subheader(t("🤝 B2B 订单对账单", "🤝 B2B Orders"))
        
        b_s = st.session_state.camp_start
        b_e = st.session_state.camp_end
        st.info(f"📅 此对账单已随左侧全局控制器锁定在：**{b_s}** 至 **{b_e}**")
        
        if not df_b2b.empty:
            db = df_b2b.copy()
            db['dt'] = pd.to_datetime(db['创建日期'], errors='coerce')
            db = db.dropna(subset=['dt'])
            if not db.empty:
                fb = db[(db['dt'].dt.date >= b_s) & (db['dt'].dt.date <= b_e)]
                fb = get_f(fb, q)
                
                if not fb.empty:
                    for c in ['采购数量', 'B2B单价', '总计应收', '已收定金']:
                        if c in fb.columns: fb[c] = pd.to_numeric(fb[c], errors='coerce').fillna(0.0)
                    fb['待收尾款'] = fb['总计应收'] - fb['已收定金']
                    
                    c1, c2 = st.columns(2)
                    c1.metric(t("📦 B2B 总采购件数", "📦 Total B2B Qty"), f"{int(fb['采购数量'].sum())}")
                    c2.metric(t("💰 B2B 总计应收金额", "💰 Total B2B Value"), f"${fb['总计应收'].sum():.2f}")
                    
                    fb['商品名称'] = translate_series(fb['商品名称'])
                    fb['颜色'] = translate_series(fb['颜色'])
                    fb['订单状态'] = translate_series(fb['订单状态'])
                    
                    show_cols = ['创建日期', '客户名称', '商品名称', '颜色', '采购数量', 'B2B单价', '总计应收', '已收定金', '待收尾款', '约定交期', '订单状态', '备注']
                    df_disp = fb[show_cols].copy()
                    if st.session_state.lang == 'en': df_disp.rename(columns=col_map, inplace=True)
                    uc, tc, dc, bc = ('B2B Price', 'Total Recv.', 'Deposit', 'Balance') if st.session_state.lang == 'en' else ('B2B单价', '总计应收', '已收定金', '待收尾款')
                    st.dataframe(df_disp.style.format({uc: '${:.2f}', tc: '${:.2f}', dc: '${:.2f}', bc: '${:.2f}'}), use_container_width=True, hide_index=True)
                else:
                    st.info(t("该区间无数据。", "No records in range."))

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
            
            if st.form_submit_button(t("✅ 确认打卡 (提交本班次)", "✅ Submit Time"), type="primary", use_container_width=True):
                fresh_att = JIT_fetch([ATT_SHEET])[ATT_SHEET]
                fresh_emp = JIT_fetch([EMP_SHEET])[EMP_SHEET]
                
                # 计算时长
                dt_start = datetime.combine(att_date, att_start)
                dt_end = datetime.combine(att_date, att_end)
                if dt_end < dt_start: dt_end += timedelta(days=1)
                duration_hours = (dt_end - dt_start).total_seconds() / 3600.0
                
                # 强转去空格防匹配报错
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
        st.markdown(t("### 📝 我的历史打卡记录 (只读)", "### 📝 My Time Logs (Read-only)"))
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
