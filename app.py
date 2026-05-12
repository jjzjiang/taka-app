import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
import gspread 
from gspread.exceptions import WorksheetNotFound
import json
import plotly.express as px

# --- 1. 系统核心配置 ---
st.set_page_config(page_title="Taka Retail Management System", layout="wide")

try:
    key_dict = json.loads(st.secrets["google_key"])
    gc = gspread.service_account_from_dict(key_dict)
    sh = gc.open_by_url(st.secrets["sheet_url"]) 
except Exception as e:
    st.error(f"🔴 Connection Failed! Check your secrets. Error: {e}")
    st.stop()

# ================= 🚀 国际化 (i18n) 增强型翻译引擎 =================
if "lang" not in st.session_state:
    st.session_state.lang = "cn"

def t(cn_text, en_text):
    return cn_text if st.session_state.lang == "cn" else en_text

col_map = {
    '商品名称': 'Product', '颜色': 'Variant', '进价成本': 'Cost', '售卖价格': 'Price',
    '应收到数量': 'Expected', '展示数量': 'Display', '货柜数量': 'Cabinet', '储物间数量': 'Storage', 
    '坏货数量': 'Damaged', '已售出数量': 'Total Sold', '总库存': 'Total Stock', '期间售出': 'Period Sales',
    '订单号': 'Order ID', '日期': 'Date', '收银员': 'Cashier', '销售数量': 'Qty', '成交单价': 'Unit Price', 
    '总营业额': 'Total Revenue', '小计': 'Subtotal', '有效客流': 'Traffic',
    '员工姓名': 'Staff Name', '职位': 'Role', '时薪': 'Hourly Wage', '状态': 'Status',
    '创建日期': 'Create Date', '客户名称': 'Client', '采购数量': 'Purchase Qty', 'B2B单价': 'B2B Price',
    '总计应收': 'Total Recv.', '已收定金': 'Deposit', '待收尾款': 'Balance', '约定交期': 'Deadline', '订单状态': 'Order Status', '备注': 'Notes',
    '记录日期': 'Log Date', '操作类型': 'Operation', '变动数量': 'Change Qty', '库位详情': 'Location Det.'
}

val_map_cn_to_en = {
    "黑": "Black", "金缮": "Kintsugi", "墨金": "Ink Gold", "银霜": "Silver Frost", "黑玉": "Black Jade",
    "陨星黑": "Meteorite Black", "陨星": "Meteorite", "天蓝": "Sky Blue", "金色": "Gold", "蓝色": "Blue", 
    "灰色": "Grey", "银色": "Silver", "黑色": "Black", "默认": "Default", "多件混装": "Mixed Combo",
    "粉色": "Pink", "绿色": "Green", "紫色": "Purple", "枫叶红": "Maple Red",
    "焖茶杯": "Brew Bottle", "纯钛酒壶": "Pure Ti Wine Flask", "直滤杯": "Flat Bottom", "冲锋壶": "Canteen",
    "咖啡杯": "Coffee Cup With Straw", "口袋杯": "Pocket Cup", "筷子": "Chopstick", "保温壶": "Thermal Flask",
    "托盘": "Tray", "盘子": "Plate", "叶碟": "Leaf Plate", "随心杯": "Easy Cup", "主人杯": "Host Cup",
    "迷你杯": "Mini Cup", "钛艺T杯": "Ti Artisan Bottle", "圆融杯": "Round Cup",
    "钛杯": "Titanium Cup", "常规水杯": "Standard Cup", "低价配件": "Accessories", "T杯": "T-Cup", "钛碗": "Titanium Bowl",
    "在职": "Active", "离职": "Resigned", "店长": "Manager", "全职店员": "Full-time", "兼职店员": "Part-time",
    "合作厂商": "Supplier", "入库": "Inbound", "调拨": "Transfer", "盘盈": "Surplus (+)", "盘亏": "Shortage (-)",
    "意向/沟通中": "Communication", "已付定金/备货中": "Prep", "已发货/待结尾款": "Shipped", "✅ 订单已完成": "✅ Completed",
    "初始建档": "Initial Setup"
}
val_map_en_to_cn = {v: k for k, v in val_map_cn_to_en.items()}

def t_val(val, to_lang):
    if pd.isna(val): return ""
    v_s = str(val).strip()
    if to_lang == 'en': return val_map_cn_to_en.get(v_s, v_s)
    return val_map_en_to_cn.get(v_s, v_s)

def translate_series(series):
    if st.session_state.lang == 'en':
        return series.map(lambda x: val_map_cn_to_en.get(str(x).strip(), str(x).strip())).fillna('')
    return series.fillna('')

# --- 2. 数据库配置 ---
STOCK_SHEET, SALES_SHEET, EMP_SHEET = "Stock", "Sales", "Employee"
ATT_SHEET, B2B_SHEET, RESTOCK_SHEET = "Attendance", "B2B_Orders", "Restock_Log"
TRAFFIC_SHEET, CAMP_SHEET, FEEDBACK_SHEET = "Traffic_Log", "Campaigns", "Feedback"

STOCK_COLS = ['商品名称', '颜色', '进价成本', '售卖价格', '应收到数量', '展示数量', '货柜数量', '储物间数量', '坏货数量', '已售出数量', '总库存']
SALES_COLS = ['订单号', '日期', '收银员', '商品名称', '颜色', '销售数量', '成交单价', '总营业额']
EMP_COLS = ['员工姓名', '职位', '时薪', '联系方式', '入职日期', '登录密码', '状态']
ATT_COLS = ['员工姓名', '日期', '开始时间', '结束时间', '工作时长', '核算薪资']
B2B_COLS = ['创建日期', '客户名称', '商品名称', '颜色', '采购数量', 'B2B单价', '总计应收', '货物成本', '物流成本', '关税', '已收定金', '待收尾款', '约定交期', '订单状态', '备注']
RESTOCK_COLS = ['记录日期', '操作类型', '商品名称', '颜色', '变动数量', '库位详情', '单件成本', '备注']
TRAFFIC_COLS = ['日期', '有效客流']
CAMP_COLS = ['档期名称', '开始日期', '结束日期']
FEEDBACK_COLS = ['反馈日期', '商品名称', '客户画像', '反馈类型', '详细原话', '跟进状态']

all_sheets = [STOCK_SHEET, SALES_SHEET, EMP_SHEET, ATT_SHEET, B2B_SHEET, RESTOCK_SHEET, TRAFFIC_SHEET, CAMP_SHEET, FEEDBACK_SHEET]
if "sheet_versions" not in st.session_state:
    st.session_state.sheet_versions = {s: 0 for s in all_sheets}

@st.cache_data(ttl=300, show_spinner=False)
def load_raw_data(sheet_name, version):
    try:
        worksheet = sh.worksheet(sheet_name)
        records = worksheet.get_all_records()
        return pd.DataFrame(records) if records else pd.DataFrame()
    except: return pd.DataFrame()

def load_data(sheet_name, columns):
    ver = st.session_state.sheet_versions.get(sheet_name, 0)
    df = load_raw_data(sheet_name, ver)
    if df.empty: df = pd.DataFrame(columns=columns)
    for col in columns:
        if col not in df.columns: df[col] = "" 
    return df[columns]

def save_data(df, sheet_name):
    try: worksheet = sh.worksheet(sheet_name)
    except WorksheetNotFound: worksheet = sh.add_worksheet(title=sheet_name, rows="1000", cols="20")
    worksheet.clear() 
    df_safe = df.fillna("").astype(str)
    data_to_upload = [df_safe.columns.values.tolist()] + df_safe.values.tolist()
    worksheet.update(values=data_to_upload, range_name='A1')
    st.session_state.sheet_versions[sheet_name] += 1

def clean_date_col(df, col_name):
    if not df.empty and col_name in df.columns:
        df[col_name] = pd.to_datetime(df[col_name], errors='coerce').dt.strftime('%Y/%m/%d').fillna('')
    return df

def load_safe_sales():
    df = clean_date_col(load_data(SALES_SHEET, SALES_COLS), '日期')
    if not df.empty:
        df['订单号'] = df['订单号'].astype(str).replace(['0', '', 'nan'], 'Historical')
        if '收银员' not in df.columns: df['收银员'] = 'Manager'
        else: df['收银员'] = df['收银员'].astype(str).replace(['0', '', 'nan'], 'Manager')
    return df

def load_safe_emp():
    df = clean_date_col(load_data(EMP_SHEET, EMP_COLS), '入职日期') 
    if not df.empty:
        df['状态'] = df['状态'].astype(str).replace(['0', '', 'nan'], '在职')
        df['登录密码'] = df['登录密码'].astype(str).replace(['0', 'nan'], '')
    return df

def JIT_fetch(sheets):
    st.cache_data.clear()
    res = {}
    for s in sheets:
        if s == FEEDBACK_SHEET: res[s] = clean_date_col(load_data(s, FEEDBACK_COLS), '反馈日期')
        elif s == STOCK_SHEET: res[s] = load_data(s, STOCK_COLS)
        elif s == SALES_SHEET: res[s] = load_safe_sales()
        elif s == RESTOCK_SHEET: res[s] = clean_date_col(load_data(s, RESTOCK_COLS), '记录日期')
        elif s == B2B_SHEET: res[s] = clean_date_col(clean_date_col(load_data(s, B2B_COLS), '创建日期'), '约定交期')
        elif s == EMP_SHEET: res[s] = load_safe_emp()
        elif s == ATT_SHEET: res[s] = clean_date_col(load_data(s, ATT_COLS), '日期')
        elif s == TRAFFIC_SHEET: res[s] = clean_date_col(load_data(s, TRAFFIC_COLS), '日期')
    return res

@st.cache_data(show_spinner=False)
def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8-sig')

df_stock = load_data(STOCK_SHEET, STOCK_COLS)
df_sales = load_safe_sales()
df_employee = load_safe_emp()
df_camp = clean_date_col(clean_date_col(load_data(CAMP_SHEET, CAMP_COLS), '开始日期'), '结束日期')
df_restock = clean_date_col(load_data(RESTOCK_SHEET, RESTOCK_COLS), '记录日期')
df_traffic = clean_date_col(load_data(TRAFFIC_SHEET, TRAFFIC_COLS), '日期')
df_attendance = clean_date_col(load_data(ATT_SHEET, ATT_COLS), '日期') 
df_b2b = clean_date_col(clean_date_col(load_data(B2B_SHEET, B2B_COLS), '创建日期'), '约定交期')
df_feedback = clean_date_col(load_data(FEEDBACK_SHEET, FEEDBACK_COLS), '反馈日期')

if "stock_reset_key" not in st.session_state: st.session_state.stock_reset_key = 0
if "sales_reset_key" not in st.session_state: st.session_state.sales_reset_key = 0
if "pos_cart" not in st.session_state: st.session_state.pos_cart = []

manager_password = "taka888"

# --- 4. 权限与角色判定 ---
if "role" not in st.session_state:
    query_role, query_user = st.query_params.get("role"), st.query_params.get("user")
    if query_role == "admin": st.session_state.role, st.session_state.current_user = "admin", "Manager"
    elif query_role in ["employee", "supplier"] and query_user: st.session_state.role, st.session_state.current_user = query_role, query_user
    else: st.session_state.role, st.session_state.current_user = None, None

if "camp_start" not in st.session_state: st.session_state.camp_start = datetime(2026, 3, 26).date()
if "camp_end" not in st.session_state: st.session_state.camp_end = datetime.now().date()
if "camp_name" not in st.session_state: st.session_state.camp_name = "Default"

# --- 5. 侧边栏 ---
with st.sidebar:
    st.header(t("🔐 系统门禁", "🔐 System Access"))
    if st.session_state.role:
        emoji = "👑" if st.session_state.role == "admin" else ("🏭" if st.session_state.role == "supplier" else "🧑‍💼")
        st.success(t(f"{emoji} 欢迎回来：{st.session_state.current_user}", f"{emoji} Welcome: {st.session_state.current_user}"))
        if st.button(t("🚪 退出系统", "🚪 Logout"), use_container_width=True):
            st.session_state.role = None
            st.query_params.clear()
            st.rerun()
            
        if st.session_state.role == "admin":
            st.divider()
            st.header("🎯 全局档期基准台")
            c_opts = df_camp['档期名称'].dropna().unique().tolist() if not df_camp.empty else []
            def on_c():
                sel = st.session_state.camp_selector
                if sel != "Manual" and not df_camp.empty:
                    r = df_camp[df_camp['档期名称'] == sel].iloc[0]
                    try:
                        st.session_state.camp_start = pd.to_datetime(r['开始日期']).date()
                        st.session_state.camp_end = pd.to_datetime(r['结束日期']).date()
                        st.session_state.camp_name = sel
                    except: pass
            st.selectbox("📌 选择基准档期", ["Manual"] + c_opts, key="camp_selector", on_change=on_c)
            st.write(f"**Current:** `{st.session_state.camp_start}` to `{st.session_state.camp_end}`")
            with st.expander("⚙️ 管理档期名录", expanded=False):
                v_camp = df_camp.copy()
                # 修复1：使用防呆的日期转换
                if not v_camp.empty:
                    v_camp['开始日期'] = pd.to_datetime(v_camp['开始日期'], errors='coerce')
                    v_camp['结束日期'] = pd.to_datetime(v_camp['结束日期'], errors='coerce')
                else: v_camp = pd.DataFrame(columns=CAMP_COLS)
                ed_camp = st.data_editor(v_camp, num_rows="dynamic", use_container_width=True)
                if st.button("💾 保存档期", type="primary", use_container_width=True):
                    ed_camp['开始日期'] = pd.to_datetime(ed_camp['开始日期'], errors='coerce').dt.strftime('%Y/%m/%d').fillna('')
                    ed_camp['结束日期'] = pd.to_datetime(ed_camp['结束日期'], errors='coerce').dt.strftime('%Y/%m/%d').fillna('')
                    save_data(ed_camp[ed_camp['档期名称'].str.strip() != ''], CAMP_SHEET); st.rerun()
    else:
        log_type = st.radio(t("身份", "Role"), [t("店员/厂商", "Staff/Supplier"), t("店长", "Admin")])
        if log_type == t("店长", "Admin"):
            pwd = st.text_input("Password", type="password")
            if st.button("Login") and pwd == manager_password:
                st.session_state.role, st.session_state.current_user = "admin", "Manager"; st.rerun()
        else:
            if not df_employee.empty:
                names = df_employee[df_employee['状态'] != '离职']['员工姓名'].tolist()
                sel = st.selectbox("Name", names)
                row = df_employee[df_employee['员工姓名'] == sel].iloc[0]
                role_assigned = "supplier" if str(row.get('职位',''))=='合作厂商' else "employee"
                pin = st.text_input("PIN", type="password")
                if st.button("Login") and pin == str(row['登录密码']).strip():
                    st.session_state.role = role_assigned; st.session_state.current_user = sel; st.rerun()

if not st.session_state.role:
    c_t, c_l = st.columns([8, 2]); c_t.title(t("🏙️ Taka 零售管理系统", "🏙️ Taka Retail System"))
    with c_l:
        lc = st.radio("🌐", ["中文", "English"], index=0 if st.session_state.lang=='cn' else 1, horizontal=True)
        if (lc=="中文" and st.session_state.lang!='cn') or (lc=="English" and st.session_state.lang!='en'):
            st.session_state.lang = 'cn' if lc=="中文" else 'en'; st.rerun()
    st.stop()

# ================= 🚀 主界面 =================
col_t, col_l = st.columns([8, 2]); col_t.title(t("🏙️ Taka 零售管理系统", "🏙️ Taka Retail System"))
with col_l:
    lc = st.radio("🌐", ["中文", "English"], index=0 if st.session_state.lang=='cn' else 1, horizontal=True)
    if (lc=="中文" and st.session_state.lang!='cn') or (lc=="English" and st.session_state.lang!='en'):
        st.session_state.lang = 'cn' if lc=="中文" else 'en'; st.rerun()

q = st.text_input(t("🔍 全局筛选搜索...", "🔍 Quick Search..."))

def get_f(df, q):
    if q and not df.empty:
        mask = pd.Series(False, index=df.index)
        q_cn = t_val(q, 'cn')
        for col in df.columns:
            mask = mask | df[col].fillna('').astype(str).str.contains(q, case=False, regex=False) | df[col].fillna('').astype(str).str.contains(q_cn, case=False, regex=False)
        return df[mask]
    return df

is_admin, is_sup = st.session_state.role == "admin", st.session_state.role == "supplier"
if is_admin: tabs = st.tabs([t("📊 库存", "📊 Inventory"), t("💰 销售", "💰 Sales"), t("📈 毛利", "📈 Margin"), t("👥 考勤", "👥 Staff"), t("💎 净利润", "💎 Net Profit"), t("🤝 B2B", "🤝 B2B"), t("🗣️ 反馈", "🗣️ Feedback"), t("🧠 BI", "🧠 BI")])
elif is_sup: tabs = st.tabs([t("📊 库存快照", "📊 Inventory"), t("💰 销售对账", "💰 Sales"), t("📦 进货对账", "📦 Inbound"), t("🤝 B2B对账", "🤝 B2B")])
else: tabs = st.tabs([t("📊 库存查询", "📊 Inventory"), t("🛒 收银台", "🛒 POS")])

# ================= Tab 1: 库存 (防 ArrowTypeError 版) =================
with tabs[0]:
    f_opts_stk = df_stock.copy()
    stock_list_labels = []
    if not f_opts_stk.empty:
        # 修复3: 强制转换为字符串，防止 PyArrow 因空值连接报错
        f_opts_stk['disp_n'] = translate_series(f_opts_stk['商品名称']).astype(str)
        f_opts_stk['disp_c'] = translate_series(f_opts_stk['颜色']).astype(str)
        f_opts_stk['label'] = f_opts_stk['disp_n'] + " (" + f_opts_stk['disp_c'] + ")"
        stock_list_labels = f_opts_stk['label'].tolist()
        
    if is_admin:
        st.subheader("📦 ERP 库存管理")
        ti1, ti2, ti3 = st.tabs(["📥 入库", "🔄 调拨", "⚖️ 盘点"])
        with ti1:
            with st.form("in"):
                sku = st.selectbox("SKU", stock_list_labels) if stock_list_labels else st.selectbox("SKU", ["Empty"])
                qty = st.number_input("Qty", min_value=1, value=10)
                loc = st.selectbox("Location", ["货柜数量", "展示数量", "储物间数量"])
                r_cst = st.number_input("Cost", value=0.0)
                if st.form_submit_button("Submit") and stock_list_labels:
                    f = JIT_fetch([STOCK_SHEET, RESTOCK_SHEET]); ls, lr = f[STOCK_SHEET], f[RESTOCK_SHEET]
                    dn, dc = sku.rsplit(" (", 1); rn, rc = t_val(dn, 'cn'), t_val(dc.replace(")", ""), 'cn')
                    idx = ls[(ls['商品名称']==rn) & (ls['颜色']==rc)].index[0]
                    ls.at[idx, loc] = int(pd.to_numeric(ls.at[idx, loc], errors='coerce') or 0) + qty
                    ls.at[idx, '总库存'] = sum([int(pd.to_numeric(ls.at[idx, c], errors='coerce') or 0) for c in ['展示数量','货柜数量','储物间数量']])
                    if r_cst > 0: ls.at[idx, '进价成本'] = r_cst
                    nl = pd.DataFrame([[datetime.now().strftime("%Y/%m/%d"), "入库", rn, rc, qty, f"In: {loc}", r_cst, "Admin"]], columns=RESTOCK_COLS)
                    save_data(ls, STOCK_SHEET); save_data(pd.concat([nl, lr], ignore_index=True), RESTOCK_SHEET); st.rerun()
        with ti2:
            with st.form("trans"):
                sku = st.selectbox("SKU", stock_list_labels) if stock_list_labels else st.selectbox("SKU", ["Empty"])
                frm = st.selectbox("From", ["储物间数量", "货柜数量", "展示数量"])
                to_loc = st.selectbox("To", ["货柜数量", "展示数量", "储物间数量"])
                qty = st.number_input("Qty", min_value=1, value=10)
                if st.form_submit_button("Transfer") and stock_list_labels and frm != to_loc:
                    f = JIT_fetch([STOCK_SHEET, RESTOCK_SHEET]); ls, lr = f[STOCK_SHEET], f[RESTOCK_SHEET]
                    dn, dc = sku.rsplit(" (", 1); rn, rc = t_val(dn, 'cn'), t_val(dc.replace(")", ""), 'cn')
                    idx = ls[(ls['商品名称']==rn) & (ls['颜色']==rc)].index[0]
                    curr_q = int(pd.to_numeric(ls.at[idx, frm], errors='coerce') or 0)
                    if curr_q < qty: st.error(f"⚠️ Not enough stock in {frm}!")
                    else:
                        ls.at[idx, frm] = curr_q - qty
                        ls.at[idx, to_loc] = int(pd.to_numeric(ls.at[idx, to_loc], errors='coerce') or 0) + qty
                        nl = pd.DataFrame([[datetime.now().strftime("%Y/%m/%d"), "调拨", rn, rc, qty, f"{frm} -> {to_loc}", 0, "Transfer"]], columns=RESTOCK_COLS)
                        save_data(ls, STOCK_SHEET); save_data(pd.concat([nl, lr], ignore_index=True), RESTOCK_SHEET); st.success("OK!"); st.rerun()
        with ti3:
            with st.form("adj"):
                sku = st.selectbox("SKU", stock_list_labels) if stock_list_labels else st.selectbox("SKU", ["Empty"])
                loc = st.selectbox("Location", ["货柜数量", "展示数量", "储物间数量", "坏货数量"])
                diff = st.number_input("Difference (+ Surplus, - Shortage)", value=-1, step=1)
                note = st.text_input("Reason", placeholder="Must fill")
                if st.form_submit_button("Adjust") and note.strip() != "" and diff != 0:
                    f = JIT_fetch([STOCK_SHEET, RESTOCK_SHEET]); ls, lr = f[STOCK_SHEET], f[RESTOCK_SHEET]
                    dn, dc = sku.rsplit(" (", 1); rn, rc = t_val(dn, 'cn'), t_val(dc.replace(")", ""), 'cn')
                    idx = ls[(ls['商品名称']==rn) & (ls['颜色']==rc)].index[0]
                    ls.at[idx, loc] = int(pd.to_numeric(ls.at[idx, loc], errors='coerce') or 0) + diff
                    if loc != '坏货数量': ls.at[idx, '总库存'] = sum([int(pd.to_numeric(ls.at[idx, c], errors='coerce') or 0) for c in ['展示数量','货柜数量','储物间数量']])
                    atype = "盘盈" if diff > 0 else "盘亏"
                    nl = pd.DataFrame([[datetime.now().strftime("%Y/%m/%d"), atype, rn, rc, diff, loc, 0, note]], columns=RESTOCK_COLS)
                    save_data(ls, STOCK_SHEET); save_data(pd.concat([nl, lr], ignore_index=True), RESTOCK_SHEET); st.success("OK!"); st.rerun()

    st.subheader(t("📊 实时快照", "📊 Inventory Snapshot"))
    dr = st.date_input(t("期间动销统计区间", "Analysis Period:"), value=[st.session_state.camp_start, st.session_state.camp_end], key="t1_dr")
    t1s, t1e = (dr[0], dr[1]) if len(dr)==2 else (dr[0], dr[0])
    
    fs = get_f(df_stock, q).copy()
    if not fs.empty:
        ds1 = df_sales.copy(); ds1['dt'] = pd.to_datetime(ds1['日期'], errors='coerce')
        fs1 = ds1[(ds1['dt']>=pd.Timestamp(t1s)) & (ds1['dt']<=pd.Timestamp(t1e))]
        ps = fs1.groupby(['商品名称','颜色'])['销售数量'].sum().reset_index().rename(columns={'销售数量':'期间售出'}) if not fs1.empty else pd.DataFrame(columns=['商品名称','颜色','期间售出'])
        fs = fs.merge(ps, on=['商品名称','颜色'], how='left').fillna(0)
        
        fs['商品名称'] = translate_series(fs['商品名称'])
        fs['颜色'] = translate_series(fs['颜色'])
        
        int_c = ['总库存','展示数量','货柜数量','储物间数量','坏货数量','期间售出','已售出数量']
        for c in int_c: fs[c] = pd.to_numeric(fs[c], errors='coerce').fillna(0).astype(int)
        fs['售卖价格'] = pd.to_numeric(fs['售卖价格'], errors='coerce').fillna(0.0)
        fs['进价成本'] = pd.to_numeric(fs['进价成本'], errors='coerce').fillna(0.0)
        fs['单品毛利率'] = fs.apply(lambda r: f"{((r['售卖价格']-r['进价成本'])/r['售卖价格']*100):.1f}%" if r['售卖价格']>0 else "0.0%", axis=1)
        
        if is_sup:
            d_cols = ['商品名称','颜色','期间售出','总库存','展示数量','货柜数量','储物间数量','坏货数量','售卖价格']
            df_v = fs[d_cols].copy()
            if st.session_state.lang == 'en': df_v.rename(columns=col_map, inplace=True)
            p_c = 'Price' if st.session_state.lang=='en' else '售卖价格'
            st.dataframe(df_v.style.format({p_c: '${:.2f}'}), use_container_width=True, hide_index=True)
        elif is_admin:
            fs.insert(0, "选择", False)
            d_cols = ['选择','商品名称','颜色','期间售出','已售出数量','总库存','展示数量','货柜数量','储物间数量','坏货数量','售卖价格','进价成本','单品毛利率']
            df_v = fs[d_cols].copy()
            if st.session_state.lang == 'en': df_v.rename(columns=col_map, inplace=True)
            p_c, c_c, stk_c = ('Price', 'Cost', 'Total Stock') if st.session_state.lang=='en' else ('售卖价格', '进价成本', '总库存')
            def hl(row):
                try:
                    if int(row[stk_c]) <= 2: return ['background-color: #ffe6e6; color: #cc0000; font-weight: bold;'] * len(row)
                except: pass
                return [''] * len(row)
            styled_df = df_v.style.format({c_c: '${:.2f}', p_c: '${:.2f}'}).apply(hl, axis=1)
            ed = st.data_editor(styled_df, column_config={"选择": st.column_config.CheckboxColumn("Sel", default=False)}, disabled=[c for c in df_v.columns if c!="选择"], use_container_width=True, hide_index=True, key=f"se_{st.session_state.stock_reset_key}")
            sel = ed[ed["选择"] == True]
            if len(sel) == 1:
                st.write("### ⚙️ SKU Edit")
                o_n = str(sel.iloc[0]['Product' if st.session_state.lang=='en' else '商品名称'])
                o_c = str(sel.iloc[0]['Variant' if st.session_state.lang=='en' else '颜色'])
                r_o_n, r_o_c = t_val(o_n, 'cn'), t_val(o_c, 'cn')
                rcst = str(sel.iloc[0][c_c]).replace('$','').replace(',','')
                rprc = str(sel.iloc[0][p_c]).replace('$','').replace(',','')
                with st.form("edit_sku"):
                    cc1, cc2 = st.columns(2)
                    nn = cc1.text_input("Name (CN)", value=r_o_n)
                    nc = cc2.text_input("Color (CN)", value=r_o_c)
                    ncst = st.number_input("Cost", value=float(rcst) if rcst else 0.0)
                    nprc = st.number_input("Price", value=float(rprc) if rprc else 0.0)
                    if st.form_submit_button("Save"):
                        f = JIT_fetch([STOCK_SHEET, SALES_SHEET, B2B_SHEET, RESTOCK_SHEET])
                        ls, lsal, lb, lr = f[STOCK_SHEET], f[SALES_SHEET], f[B2B_SHEET], f[RESTOCK_SHEET]
                        idx = ls[(ls['商品名称']==r_o_n) & (ls['颜色']==r_o_c)].index[0]
                        ls.loc[idx, ['商品名称','颜色','进价成本','售卖价格']] = [nn, nc, ncst, nprc]
                        if nn!=r_o_n or nc!=r_o_c:
                            if not lsal.empty: lsal.loc[(lsal['商品名称']==r_o_n) & (lsal['颜色']==r_o_c), ['商品名称','颜色']] = [nn, nc]
                            if not lr.empty: lr.loc[(lr['商品名称']==r_o_n) & (lr['颜色']==r_o_c), ['商品名称','颜色']] = [nn, nc]
                            if not lb.empty: lb.loc[(lb['商品名称']==r_o_n) & (lb['颜色']==r_o_c), ['商品名称','颜色']] = [nn, nc]
                            save_data(lsal, SALES_SHEET); save_data(lr, RESTOCK_SHEET); save_data(lb, B2B_SHEET)
                        save_data(ls, STOCK_SHEET); st.session_state.stock_reset_key += 1; st.rerun()
            if not sel.empty and st.button("🗑️ Delete"):
                fs_s = JIT_fetch([STOCK_SHEET])[STOCK_SHEET]
                for _, row in sel.iterrows():
                    rn, rc = t_val(row['Product' if st.session_state.lang=='en' else '商品名称'], 'cn'), t_val(row['Variant' if st.session_state.lang=='en' else '颜色'], 'cn')
                    fs_s = fs_s[~((fs_s['商品名称']==rn) & (fs_s['颜色']==rc))]
                save_data(fs_s, STOCK_SHEET); st.session_state.stock_reset_key += 1; st.rerun()
            with st.expander("📜 Logs", expanded=False):
                dl = get_f(df_restock, q).copy()
                dl['操作类型'] = translate_series(dl['操作类型']); dl['商品名称'] = translate_series(dl['商品名称']); dl['颜色'] = translate_series(dl['颜色'])
                if st.session_state.lang == 'en': dl.rename(columns=col_map, inplace=True)
                st.dataframe(dl, use_container_width=True)
        else: # 店员
            d_cols = ['商品名称','颜色','期间售出','总库存','展示数量','货柜数量','储物间数量','售卖价格']
            df_v = fs[d_cols].copy()
            if st.session_state.lang == 'en': df_v.rename(columns=col_map, inplace=True)
            p_c = 'Price' if st.session_state.lang=='en' else '售卖价格'
            st.dataframe(df_v.style.format({p_c: '${:.2f}'}), use_container_width=True, hide_index=True)

# ================= Tab 2: 销售/POS (防 ArrowTypeError 版) =================
with tabs[1]:
    if is_sup:
        st.subheader(t("💰 销售报表对账查询", "💰 Sales Report Reconciliation"))
        ds = df_sales.copy(); ds['dt'] = pd.to_datetime(ds['日期'], errors='coerce')
        dr = st.date_input("Range", value=[st.session_state.camp_start, st.session_state.camp_end], key="sup_s")
        if len(dr)==2:
            fs = ds[(ds['dt'].dt.date>=pd.Timestamp(dr[0])) & (ds['dt'].dt.date<=pd.Timestamp(dr[1]))]
            fs = get_f(fs, q)
            fs['商品名称'] = translate_series(fs['商品名称']); fs['颜色'] = translate_series(fs['颜色'])
            fs['销售数量'] = pd.to_numeric(fs['销售数量'], errors='coerce').fillna(0)
            fs['总营业额'] = pd.to_numeric(fs['总营业额'], errors='coerce').fillna(0.0)
            st.metric("Total Qty", f"{int(fs['销售数量'].sum())}")
            dv = fs[['日期','商品名称','颜色','销售数量','成交单价','总营业额']].copy()
            if st.session_state.lang=='en': dv.rename(columns=col_map, inplace=True)
            st.dataframe(dv, use_container_width=True, hide_index=True)
    else:
        st.subheader(t("🛒 智能收银台", "🛒 Smart POS"))
        c1, c2 = st.columns([1.2, 1.5])
        with c1:
            with st.container(border=True):
                fo = df_stock.copy()
                # 修复3: 强制字符化，防止拼接报错
                fo['dn'] = translate_series(fo['商品名称']).astype(str)
                fo['dc'] = translate_series(fo['颜色']).astype(str)
                fo['label'] = fo['dn'] + " (" + fo['dc'] + ")"
                if not fo.empty:
                    sku = st.selectbox("Product", fo['label'], key="pos_sku")
                    row = fo[fo['label']==sku].iloc[0]
                    qty = st.number_input("Qty", min_value=1, value=1)
                    prc = float(pd.to_numeric(row['售卖价格'], errors='coerce') or 0)
                    disc = st.selectbox("Discount", list({"No Discount":1.0, "5% Off":0.95, "10% Off":0.9, "20% Off":0.8, "50% Off":0.5}.items()), format_func=lambda x: x[0])
                    final_p = st.number_input("Final Price", value=prc*disc[1], format="%.2f")
                    if st.button("➕ Add to Cart", use_container_width=True):
                        st.session_state.pos_cart.append({"rn":row['商品名称'], "rc":row['颜色'], "dn":row['dn'], "dc":row['dc'], "q":qty, "p":final_p})
                        st.rerun()
        with c2:
            with st.container(border=True):
                if st.session_state.pos_cart:
                    cdf = pd.DataFrame(st.session_state.pos_cart)
                    dv = cdf[['dn','dc','q','p']].copy()
                    dv.columns = ['Product', 'Variant', 'Qty', 'Price']
                    st.dataframe(dv.style.format({'Price': '${:.2f}'}), use_container_width=True, hide_index=True)
                    st.markdown(f"**Total Qty:** {cdf['q'].sum()} | **Total Amount: ${cdf['q'].dot(cdf['p']):.2f}**")
                    sd = st.date_input("Date", value=datetime.now())
                    cc1, cc2 = st.columns(2)
                    if cc1.button("🗑️ Clear", use_container_width=True): st.session_state.pos_cart = []; st.rerun()
                    if cc2.button("💳 Checkout", type="primary", use_container_width=True):
                        f = JIT_fetch([STOCK_SHEET, SALES_SHEET]); ls, lsal = f[STOCK_SHEET], f[SALES_SHEET]
                        oid, odt, usr = "ORD-"+datetime.now().strftime("%y%m%d%H%M"), sd.strftime("%Y/%m/%d"), st.session_state.current_user
                        new = []
                        for i in st.session_state.pos_cart:
                            new.append([oid, odt, usr, i['rn'], i['rc'], i['q'], i['p'], i['q']*i['p']])
                            idx = ls[(ls['商品名称']==i['rn']) & (ls['颜色']==i['rc'])].index
                            if not idx.empty:
                                ls.at[idx[0],'货柜数量'] = int(pd.to_numeric(ls.at[idx[0],'货柜数量'], errors='coerce') or 0) - i['q']
                                ls.at[idx[0],'已售出数量'] = int(pd.to_numeric(ls.at[idx[0],'已售出数量'], errors='coerce') or 0) + i['q']
                                ls.at[idx[0],'总库存'] = sum([int(pd.to_numeric(ls.at[idx[0],c], errors='coerce') or 0) for c in ['展示数量','货柜数量','储物间数量']])
                        save_data(ls, STOCK_SHEET); save_data(pd.concat([pd.DataFrame(new, columns=SALES_COLS), lsal], ignore_index=True), SALES_SHEET)
                        st.session_state.pos_cart = []; st.success("Success!"); st.rerun()
                else: st.info("Cart is empty.")
        
        st.divider()
        with st.expander(t("🔄 换货处理 (Exchange)", "🔄 Item Exchange")):
            if not fo.empty:
                xc1, xc2 = st.columns(2)
                with xc1:
                    rl = st.selectbox("Return Item", fo['label'], key="r_sku")
                    rr = fo[fo['label']==rl].iloc[0]
                    rp = st.number_input("Return Value ($)", value=float(pd.to_numeric(rr['售卖价格'], errors='coerce') or 0))
                    rd = st.checkbox("Damaged", value=False)
                with xc2:
                    nl = st.selectbox("New Item", fo['label'], key="n_sku")
                    nr = fo[fo['label']==nl].iloc[0]
                    np = st.number_input("New Item Price ($)", value=float(pd.to_numeric(nr['售卖价格'], errors='coerce') or 0))
                diff = np - rp
                st.write(f"**Difference:** ${diff:.2f}")
                if st.button("Confirm Exchange"):
                    f = JIT_fetch([STOCK_SHEET, SALES_SHEET]); ls, lsal = f[STOCK_SHEET], f[SALES_SHEET]
                    oid, odt, usr = "EXC-"+datetime.now().strftime("%y%m%d%H%M"), datetime.now().strftime("%Y/%m/%d"), st.session_state.current_user
                    idx_r = ls[(ls['商品名称']==rr['商品名称']) & (ls['颜色']==rr['颜色'])].index[0]
                    idx_n = ls[(ls['商品名称']==nr['商品名称']) & (ls['颜色']==nr['颜色'])].index[0]
                    sr = pd.DataFrame([[oid, odt, usr, rr['商品名称'], rr['颜色'], -1, rp, -rp]], columns=SALES_COLS)
                    sn = pd.DataFrame([[oid, odt, usr, nr['商品名称'], nr['颜色'], 1, np, np]], columns=SALES_COLS)
                    lsal = pd.concat([sn, sr, lsal], ignore_index=True)
                    if rd: ls.at[idx_r,'坏货数量'] = int(pd.to_numeric(ls.at[idx_r,'坏货数量'], errors='coerce') or 0) + 1
                    else: 
                        ls.at[idx_r,'货柜数量'] = int(pd.to_numeric(ls.at[idx_r,'货柜数量'], errors='coerce') or 0) + 1
                        ls.at[idx_r,'总库存'] = sum([int(pd.to_numeric(ls.at[idx_r,c], errors='coerce') or 0) for c in ['展示数量','货柜数量','储物间数量']])
                    ls.at[idx_r,'已售出数量'] = int(pd.to_numeric(ls.at[idx_r,'已售出数量'], errors='coerce') or 0) - 1
                    ls.at[idx_n,'货柜数量'] = int(pd.to_numeric(ls.at[idx_n,'货柜数量'], errors='coerce') or 0) - 1
                    ls.at[idx_n,'已售出数量'] = int(pd.to_numeric(ls.at[idx_n,'已售出数量'], errors='coerce') or 0) + 1
                    ls.at[idx_n,'总库存'] = sum([int(pd.to_numeric(ls.at[idx_n,c], errors='coerce') or 0) for c in ['展示数量','货柜数量','储物间数量']])
                    save_data(ls, STOCK_SHEET); save_data(lsal, SALES_SHEET); st.rerun()

        st.markdown(t("### 📝 今日流水 (Today's Logs)", "### 📝 Today's Logs"))
        td = datetime.now().strftime("%Y/%m/%d")
        fsl = df_sales[df_sales['日期']==td].copy()
        if not fsl.empty:
            if is_admin:
                fsl.insert(0, "Sel", False)
                ed = st.data_editor(fsl, hide_index=True)
                if st.button("🔴 Revert Selected"):
                    sel = ed[ed["Sel"]==True]
                    f = JIT_fetch([STOCK_SHEET, SALES_SHEET]); ls, lsal = f[STOCK_SHEET], f[SALES_SHEET]
                    for _, r in sel.iterrows():
                        idx = ls[(ls['商品名称']==r['商品名称']) & (ls['颜色']==r['颜色'])].index[0]
                        ls.at[idx,'货柜数量'] = int(pd.to_numeric(ls.at[idx,'货柜数量'], errors='coerce') or 0) + int(r['销售数量'])
                        ls.at[idx,'已售出数量'] = int(pd.to_numeric(ls.at[idx,'已售出数量'], errors='coerce') or 0) - int(r['销售数量'])
                        ls.at[idx,'总库存'] = sum([int(pd.to_numeric(ls.at[idx,c], errors='coerce') or 0) for c in ['展示数量','货柜数量','储物间数量']])
                        lsal = lsal[~((lsal['订单号']==r['订单号']) & (lsal['商品名称']==r['商品名称']) & (lsal['颜色']==r['颜色']))]
                    save_data(ls, STOCK_SHEET); save_data(lsal, SALES_SHEET); st.rerun()
            else:
                fsl['商品名称'] = translate_series(fsl['商品名称']); fsl['颜色'] = translate_series(fsl['颜色'])
                if st.session_state.lang=='en': fsl.rename(columns=col_map, inplace=True)
                st.dataframe(fsl, hide_index=True)

# ================= 🚀 Tab 3-8: 后台管理 (Admin) =================
if is_admin:
    with tabs[2]:
        st.subheader("📊 Profit & Traffic Funnel")
        dr = st.date_input("Period:", value=[st.session_state.camp_start, st.session_state.camp_end], key="t3_dr")
        t3s, t3e = (dr[0], dr[1]) if len(dr)==2 else (dr[0], dr[0])
        ds = df_sales.copy(); ds['dt'] = pd.to_datetime(ds['日期'], errors='coerce')
        fs = ds[(ds['dt'].dt.date>=t3s) & (ds['dt'].dt.date<=t3e)].copy()
        if not fs.empty:
            fs['销售数量'] = pd.to_numeric(fs['销售数量'], errors='coerce').fillna(0)
            fs['总营业额'] = pd.to_numeric(fs['总营业额'], errors='coerce').fillna(0.0)
            dc = df_stock[['商品名称','颜色','进价成本']].copy()
            dc['进价成本'] = pd.to_numeric(dc['进价成本'], errors='coerce').fillna(0.0)
            fs = fs.merge(dc, on=['商品名称','颜色'], how='left')
            fs['具体毛利'] = fs['总营业额'] - (fs['销售数量'] * fs['进价成本'])
            
            tot_rev = fs['总营业额'].sum()
            tot_items = fs['销售数量'].sum()
            tot_margin = fs['具体毛利'].sum()
            valid_o = fs[~fs['订单号'].str.contains('EXC-|Historical')]['订单号'].nunique() + len(fs[fs['订单号'].str.contains('Historical')])
            
            dft = df_traffic.copy(); dft['dt'] = pd.to_datetime(dft['日期'], errors='coerce')
            ft = dft[(dft['dt'].dt.date>=t3s) & (dft['dt'].dt.date<=t3e)]
            tot_tf = pd.to_numeric(ft['有效客流'], errors='coerce').fillna(0).sum() if not ft.empty else 0
            
            c1, c2, c3 = st.columns(3)
            c1.metric("👁️ Traffic", f"{int(tot_tf)}")
            c2.metric("💳 Orders", f"{valid_o}")
            c3.metric("🔄 Conv. Rate", f"{(valid_o/tot_tf*100) if tot_tf>0 else 0:.1f}%")
            
            c4, c5, c6 = st.columns(3)
            c4.metric("💰 Rev", f"${tot_rev:.2f}")
            c5.metric("🛒 ACV", f"${(tot_rev/valid_o) if valid_o>0 else 0:.2f}")
            c6.metric("💎 Margin", f"${tot_margin:.2f} ({(tot_margin/tot_rev*100) if tot_rev>0 else 0:.1f}%)")
            
            fs['dt_str'] = fs['dt'].dt.strftime('%Y/%m/%d')
            grp = fs.groupby('dt_str')[['总营业额','具体毛利']].sum().sort_index()
            st.bar_chart(grp)

    with tabs[3]:
        st.subheader("👥 Staff & Attendance")
        with st.form("new_emp"):
            c1, c2 = st.columns(2)
            nm = c1.text_input("Name")
            rl = c2.selectbox("Role", ["全职店员", "兼职店员", "合作厂商", "店长"])
            if st.form_submit_button("Add") and nm:
                f = JIT_fetch([EMP_SHEET])[EMP_SHEET]
                nl = pd.DataFrame([[nm, rl, 0, "", datetime.now().strftime("%Y/%m/%d"), "", "在职"]], columns=EMP_COLS)
                save_data(pd.concat([f, nl], ignore_index=True), EMP_SHEET); st.rerun()
        ed_emp = st.data_editor(df_employee, hide_index=True, use_container_width=True)
        if st.button("💾 Save Employee Changes"): save_data(ed_emp, EMP_SHEET); st.rerun()

    with tabs[4]:
        st.subheader("💎 Net Profit P&L (9% GST Stripped)")
        st.info(f"Period Locked: {st.session_state.camp_start} to {st.session_state.camp_end}")
        ds = df_sales.copy(); ds['dt'] = pd.to_datetime(ds['日期'], errors='coerce')
        da = df_attendance.copy(); da['dt'] = pd.to_datetime(da['日期'], errors='coerce')
        fs = ds[(ds['dt'].dt.date>=st.session_state.camp_start) & (ds['dt'].dt.date<=st.session_state.camp_end)].copy()
        fa = da[(da['dt'].dt.date>=st.session_state.camp_start) & (da['dt'].dt.date<=st.session_state.camp_end)].copy()
        if not fs.empty:
            fs['销售数量'] = pd.to_numeric(fs['销售数量'], errors='coerce').fillna(0)
            fs['总营业额'] = pd.to_numeric(fs['总营业额'], errors='coerce').fillna(0.0)
            dc = df_stock[['商品名称','颜色','进价成本']].copy()
            dc['进价成本'] = pd.to_numeric(dc['进价成本'], errors='coerce').fillna(0.0)
            fs = fs.merge(dc, on=['商品名称','颜色'], how='left')
            fs['Cost'] = fs['销售数量'] * fs['进价成本']
            d_sales = fs.groupby(fs['dt'].dt.strftime('%Y/%m/%d')).agg({'总营业额':'sum', 'Cost':'sum'}).reset_index().rename(columns={'dt':'日期'})
            d_att = fa.groupby(fa['dt'].dt.strftime('%Y/%m/%d'))['核算薪资'].apply(lambda x: pd.to_numeric(x, errors='coerce').sum()).reset_index().rename(columns={'dt':'日期', '核算薪资':'Wage'}) if not fa.empty else pd.DataFrame(columns=['日期','Wage'])
            
            dnp = pd.merge(d_sales, d_att, on='日期', how='outer').fillna(0).sort_values('日期', ascending=False)
            dnp['Net_Rev'] = dnp['总营业额'] / 1.09
            dnp['GST'] = dnp['总营业额'] - dnp['Net_Rev']
            dnp['Comm(36%)'] = dnp['Net_Rev'] * 0.36
            dnp['Actual_Recv'] = dnp['Net_Rev'] - dnp['Comm(36%)']
            dnp['Gross_Profit'] = dnp['Actual_Recv'] - dnp['Cost']
            dnp['Net_Profit'] = dnp['Gross_Profit'] - dnp['Wage']
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Rev (Inc. Tax)", f"${dnp['总营业额'].sum():.2f}")
            c2.metric("GST (9%)", f"${dnp['GST'].sum():.2f}")
            c3.metric("Commission (36%)", f"${dnp['Comm(36%)'].sum():.2f}")
            c4.metric("True Net Profit", f"${dnp['Net_Profit'].sum():.2f}", f"{(dnp['Net_Profit'].sum()/dnp['总营业额'].sum()*100) if dnp['总营业额'].sum()>0 else 0:.1f}%")
            st.dataframe(dnp.style.format({c: '${:.2f}' for c in dnp.columns if c!='日期'}), use_container_width=True, hide_index=True)

    with tabs[5]:
        st.subheader("🤝 B2B Orders")
        ed_b2b = st.data_editor(df_b2b, num_rows="dynamic", use_container_width=True, hide_index=True)
        if st.button("💾 Save B2B"): save_data(ed_b2b, B2B_SHEET); st.rerun()

    with tabs[6]:
        st.subheader("🗣️ Feedback")
        ed_fb = st.data_editor(df_feedback, num_rows="dynamic", use_container_width=True, hide_index=True)
        if st.button("💾 Save Feedback"): save_data(ed_fb, FEEDBACK_SHEET); st.rerun()

    with tabs[7]:
        st.subheader(f"📈 选品战略罗盘 (Locked: {st.session_state.camp_start} to {st.session_state.camp_end})")
        ds = df_sales.copy(); ds['dt'] = pd.to_datetime(ds['日期'], errors='coerce')
        fs = ds[(ds['dt'].dt.date>=st.session_state.camp_start) & (ds['dt'].dt.date<=st.session_state.camp_end)].copy()
        if not fs.empty and not df_stock.empty:
            fs['销售数量'] = pd.to_numeric(fs['销售数量'], errors='coerce').fillna(0)
            fs['总营业额'] = pd.to_numeric(fs['总营业额'], errors='coerce').fillna(0.0)
            bs = fs.groupby(['商品名称','颜色']).agg({'销售数量':'sum', '总营业额':'sum'}).reset_index()
            
            dk = df_stock[['商品名称','颜色','进价成本','总库存']].copy()
            dk['进价成本'] = pd.to_numeric(dk['进价成本'], errors='coerce').fillna(0.0)
            dk['总库存'] = pd.to_numeric(dk['总库存'], errors='coerce').fillna(0)
            
            bi = pd.merge(dk, bs, on=['商品名称','颜色'], how='left').fillna(0)
            days = max((min(datetime.now().date(), st.session_state.camp_end) - st.session_state.camp_start).days + 1, 1)
            
            bi['Velocity'] = bi['销售数量'] / days
            bi['Margin(%)'] = ((bi['总营业额'] - bi['销售数量']*bi['进价成本']) / bi['总营业额'] * 100).fillna(0.0)
            bi['Stock_Val'] = bi['总库存'] * bi['进价成本']
            
            def get_tag(r):
                v, m, s = r['Velocity'], r['Margin(%)'], r['总库存']
                if s<=2 and r['销售数量']>0: return "🚨 Blood/OOS"
                if v<0.167 and s>0: return "📦 Dead Stock"
                if v>=0.33 and m>=50: return "⭐ Star"
                if v>=0.33 and m<50: return "🧲 Traffic Driver"
                return "🚶 Regular"
                
            bi['Tag'] = bi.apply(get_tag, axis=1)
            bi['SKU'] = translate_series(bi['商品名称']).astype(str) + " " + translate_series(bi['颜色']).astype(str)
            bi['Bubble'] = bi['Stock_Val'].apply(lambda x: max(float(x), 10))
            
            fig = px.scatter(bi, x='Velocity', y='Margin(%)', color='Tag', size='Bubble', hover_name='SKU', size_max=45, height=500, template="plotly_white")
            fig.add_vline(x=0.33, line_dash="dash", annotation_text="Target Velocity")
            fig.add_hline(y=50, line_dash="dash", annotation_text="Target Margin")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(bi[['SKU','Tag','Velocity','Margin(%)','总库存','Stock_Val']].sort_values('Velocity', ascending=False), use_container_width=True, hide_index=True)

# ================= 🚀 厂商对账层 (Supplier) 修复2: 防止 multiselect 空集报错 =================
if is_sup:
    with tabs[2]:
        st.subheader("📦 Inbound Records")
        dr = df_restock.copy(); dr['dt'] = pd.to_datetime(dr['记录日期'], errors='coerce')
        fr = dr[(dr['dt'].dt.date>=st.session_state.camp_start) & (dr['dt'].dt.date<=st.session_state.camp_end)].copy()
        if not fr.empty:
            fr['操作类型'] = translate_series(fr['操作类型'])
            # 修复2：动态获取列表里有的操作类型，作为默认值，防止报错
            avail_ops = fr['操作类型'].unique().tolist()
            safe_defs = [op for op in [t_val("入库", "en"), t_val("初始建档", "en"), "入库", "初始建档"] if op in avail_ops]
            
            type_filter = st.multiselect("Filter Operation", options=avail_ops, default=safe_defs)
            if type_filter:
                fr = fr[fr['操作类型'].isin(type_filter)]
                fr['商品名称'] = translate_series(fr['商品名称']); fr['颜色'] = translate_series(fr['颜色'])
                st.dataframe(fr[['记录日期','操作类型','商品名称','颜色','变动数量','备注']], hide_index=True)
            else: st.info("Please select an operation type.")
        else: st.info("No records.")
        
    with tabs[3]:
        st.subheader("🤝 B2B Orders (Profit Masked)")
        db = df_b2b.copy(); db['dt'] = pd.to_datetime(db['创建日期'], errors='coerce')
        fb = db[(db['dt'].dt.date>=st.session_state.camp_start) & (db['dt'].dt.date<=st.session_state.camp_end)].copy()
        if not fb.empty:
            fb['商品名称'] = translate_series(fb['商品名称']); fb['颜色'] = translate_series(fb['颜色']); fb['订单状态'] = translate_series(fb['订单状态'])
            df_disp = fb[['创建日期','客户名称','商品名称','颜色','采购数量','总计应收','已收定金','订单状态']].copy()
            if st.session_state.lang=='en': df_disp.rename(columns=col_map, inplace=True)
            st.dataframe(df_disp, hide_index=True)
