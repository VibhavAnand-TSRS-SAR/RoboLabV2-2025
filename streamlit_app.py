import streamlit as st
import pandas as pd
import sqlite3
import time
import json
import uuid
import base64
import io
import altair as alt
from datetime import datetime, timedelta

# --- CONFIGURATION ---
st.set_page_config(page_title="RoboLab Inventory System", page_icon="🤖", layout="wide")

# --- THEME & CSS ---
THEMES = {
    "TSRS (Red/Grey)": {
        "primary": "#A6192E",
        "secondary": "#58595B",
        "bg_sidebar": "#F3F4F6",
        "text_sidebar": "#1F2937",
        "hover": "#E5E7EB",
        "active": "#A6192E",
        "active_text": "#FFFFFF"
    },
    "Night Mode": {
        "primary": "#3B82F6",
        "secondary": "#9CA3AF",
        "bg_sidebar": "#111827",
        "text_sidebar": "#E5E7EB",
        "hover": "#374151",
        "active": "#1D4ED8",
        "active_text": "#FFFFFF"
    }
}

if 'theme' not in st.session_state:
    st.session_state.theme = "TSRS (Red/Grey)"

current_theme = THEMES[st.session_state.theme]

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {{
        font-family: 'Inter', sans-serif;
    }}
    
    /* Sidebar */
    section[data-testid="stSidebar"] {{ background-color: {current_theme['bg_sidebar']}; }}
    
    .nav-btn {{
        width: 100%; text-align: left; padding: 12px 15px; margin: 5px 0;
        border: none; border-radius: 8px; background-color: transparent;
        color: {current_theme['text_sidebar']}; font-size: 16px; cursor: pointer;
        display: flex; align-items: center; gap: 10px; transition: all 0.3s ease;
    }}
    .nav-btn:hover {{ background-color: {current_theme['hover']}; transform: translateX(5px); }}
    
    /* Metrics */
    div[data-testid="stMetric"] {{
        background-color: white; padding: 20px; border-radius: 12px;
        border-left: 5px solid {current_theme['primary']};
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }}
    
    /* Login Page Styling */
    .login-container {{
        display: flex; justify-content: center; align-items: center;
        height: 80vh; background-color: #f3f4f6;
    }}
    .login-card {{
        background: white; padding: 2rem; border-radius: 1.5rem;
        box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
        width: 100%; max-width: 450px; border-top: 8px solid {current_theme['primary']};
    }}
    .login-header {{ text-align: center; margin-bottom: 2rem; }}
    .login-header h1 {{ color: {current_theme['primary']}; font-weight: 800; font-size: 2.5rem; margin: 0; }}
    .login-header p {{ color: #6b7280; font-size: 0.95rem; margin-top: 0.5rem; }}
    
    /* Footer */
    .footer {{
        position: fixed; bottom: 0; left: 0; width: 100%;
        background-color: white; text-align: center; padding: 10px;
        font-size: 12px; color: #9CA3AF; border-top: 1px solid #E5E7EB;
        z-index: 999;
    }}
</style>
""", unsafe_allow_html=True)

# --- DATABASE ENGINE ---

def get_db_connection():
    conn = sqlite3.connect('robolab_v2.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # 1. Users (Added profile_pic)
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 emp_id TEXT UNIQUE NOT NULL,
                 name TEXT NOT NULL,
                 password TEXT NOT NULL,
                 role TEXT NOT NULL,
                 dob TEXT, gender TEXT, address TEXT, phone TEXT,
                 profile_pic TEXT)''')
    
    # Migration for older DBs
    try:
        c.execute("SELECT profile_pic FROM users LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE users ADD COLUMN profile_pic TEXT")
        conn.commit()

    # 2. Roles
    c.execute('''CREATE TABLE IF NOT EXISTS roles (
                 name TEXT PRIMARY KEY,
                 permissions TEXT)''')
    
    # 3. Inventory
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 name TEXT NOT NULL,
                 category TEXT,
                 location TEXT,
                 quantity INTEGER DEFAULT 0,
                 min_stock INTEGER DEFAULT 5,
                 price REAL DEFAULT 0.0)''')
    
    # 4. Transactions
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 item_id INTEGER,
                 item_name TEXT,
                 type TEXT,
                 quantity INTEGER,
                 user TEXT,
                 timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                 notes TEXT)''')
    
    # 5. Sessions
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (
                 token TEXT PRIMARY KEY,
                 user_id INTEGER,
                 expires_at DATETIME)''')
    
    # 6. Activity Logs (New Feature for Admin)
    c.execute('''CREATE TABLE IF NOT EXISTS activity_logs (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 user_name TEXT,
                 action TEXT,
                 details TEXT,
                 timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    # Seed Data
    c.execute("SELECT count(*) FROM roles")
    if c.fetchone()[0] == 0:
        # Admin: All permissions + 'Audit Logs'
        all_perms = json.dumps(["Dashboard", "Inventory", "Stock Operations", "Reports", "Shopping List", "User Management", "Audit Logs", "Settings"])
        c.execute("INSERT INTO roles (name, permissions) VALUES (?, ?)", ('admin', all_perms))
        
        # Assistant: Basic permissions
        asst_perms = json.dumps(["Dashboard", "Inventory", "Stock Operations", "Reports", "Shopping List"])
        c.execute("INSERT INTO roles (name, permissions) VALUES (?, ?)", ('assistant', asst_perms))
        conn.commit()

    c.execute("SELECT count(*) FROM users")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users (emp_id, name, password, role) VALUES (?, ?, ?, ?)", ('admin', 'System Admin', 'admin123', 'admin'))
        c.execute("INSERT INTO users (emp_id, name, password, role) VALUES (?, ?, ?, ?)", ('assistant', 'Lab Assistant', '123', 'assistant'))
        conn.commit()
    
    conn.close()

def run_query(query, params=(), fetch=False):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute(query, params)
        if fetch:
            data = c.fetchall()
            conn.close()
            return [dict(row) for row in data]
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        conn.close()
        return False

# --- LOGGING HELPER ---
def log_activity(action, details):
    if 'user' in st.session_state and st.session_state.user:
        user_name = st.session_state.user['name']
        run_query("INSERT INTO activity_logs (user_name, action, details) VALUES (?, ?, ?)", 
                  (user_name, action, details))

# --- IMAGE UTILS ---
def get_image_base64(image_file):
    if image_file is not None:
        return base64.b64encode(image_file.read()).decode()
    return None

def image_from_base64(base64_str):
    if base64_str:
        return f"data:image/png;base64,{base64_str}"
    return "https://www.w3schools.com/howto/img_avatar.png" # Default avatar

# --- AUTH ---
def create_session(user_id):
    token = str(uuid.uuid4())
    expiry = datetime.now() + timedelta(minutes=5)
    run_query("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (token, user_id, expiry))
    return token

def validate_session(token):
    run_query("DELETE FROM sessions WHERE expires_at < ?", (datetime.now(),))
    data = run_query("SELECT user_id FROM sessions WHERE token = ? AND expires_at > ?", (token, datetime.now()), fetch=True)
    if data:
        new_expiry = datetime.now() + timedelta(minutes=5)
        run_query("UPDATE sessions SET expires_at = ? WHERE token = ?", (new_expiry, token))
        return run_query("SELECT * FROM users WHERE id = ?", (data[0]['user_id'],), fetch=True)[0]
    return None

def logout_user():
    if 'session_token' in st.query_params:
        run_query("DELETE FROM sessions WHERE token = ?", (st.query_params['session_token'],))
    st.query_params.clear()
    st.session_state.user = None
    log_activity("Logout", "User logged out")
    st.rerun()

# --- VIEWS ---

def view_dashboard():
    role = st.session_state.user['role']
    
    # 1. ADMIN DASHBOARD
    if role == 'admin':
        st.title("📊 Master Dashboard")
        df = pd.read_sql_query("SELECT * FROM inventory", get_db_connection())
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Items", int(df['quantity'].sum()) if not df.empty else 0)
        c2.metric("Inventory Value", f"₹{(df['quantity'] * df['price']).sum():,.0f}" if not df.empty else "₹0")
        c3.metric("Alerts", len(df[df['quantity'] <= df['min_stock']]) if not df.empty else 0)
        c4.metric("Categories", df['category'].nunique() if not df.empty else 0)
        
        col_chart, col_recent = st.columns([2, 1])
        with col_chart:
            st.subheader("Category Breakdown")
            if not df.empty:
                chart_data = df.groupby('category')['quantity'].sum().reset_index()
                chart = alt.Chart(chart_data).mark_arc(innerRadius=60).encode(
                    theta='quantity', color='category', tooltip=['category', 'quantity']
                )
                st.altair_chart(chart, use_container_width=True)
            else:
                st.info("No data available")
            
        with col_recent:
            st.subheader("System Logs")
            logs = pd.read_sql_query("SELECT user_name, action, timestamp FROM activity_logs ORDER BY timestamp DESC LIMIT 5", get_db_connection())
            st.dataframe(logs, use_container_width=True, hide_index=True)

    # 2. USER DASHBOARD (Personalized)
    else:
        st.title(f"👋 Welcome, {st.session_state.user['name']}")
        
        # User Specific Stats
        conn = get_db_connection()
        my_trans = pd.read_sql_query("SELECT * FROM transactions WHERE user = ? ORDER BY timestamp DESC", conn, params=(st.session_state.user['name'],))
        conn.close()
        
        c1, c2 = st.columns(2)
        c1.metric("My Transactions", len(my_trans))
        
        last_active = my_trans.iloc[0]['timestamp'] if not my_trans.empty else "N/A"
        c2.metric("Last Active", str(last_active)[:10])
        
        st.subheader("My Recent Activity")
        if not my_trans.empty:
            st.dataframe(my_trans[['timestamp', 'type', 'item_name', 'quantity', 'notes']].head(10), use_container_width=True)
        else:
            st.info("You haven't performed any stock operations yet.")

def view_audit_logs():
    st.title("🛡️ Audit Logs (Admin Only)")
    st.info("Tracking all system changes: Logins, Inventory updates, User changes.")
    
    df = pd.read_sql_query("SELECT timestamp, user_name, action, details FROM activity_logs ORDER BY timestamp DESC", get_db_connection())
    st.dataframe(df, use_container_width=True)

def view_reports():
    st.title("📑 Financial Reports")
    
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM transactions", conn)
    conn.close()
    
    if df.empty:
        st.warning("No data available for reports.")
        return

    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['year'] = df['timestamp'].dt.year
    df['month'] = df['timestamp'].dt.month_name()
    df['month_num'] = df['timestamp'].dt.month
    
    # Get available years in reverse order
    years = sorted(df['year'].unique(), reverse=True)
    
    for year in years:
        with st.expander(f"📂 Year: {year}", expanded=(year==max(years))):
            year_data = df[df['year'] == year]
            
            # Annual Download
            buffer_annual = io.BytesIO()
            with pd.ExcelWriter(buffer_annual, engine='xlsxwriter') as writer:
                year_data.to_excel(writer, sheet_name='Annual', index=False)
            
            col_main, col_months = st.columns([1, 3])
            with col_main:
                st.download_button(f"📥 Download Annual Report {year}", buffer_annual, f"Annual_Report_{year}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                
            with col_months:
                st.write("**Monthly Breakdown (Reverse Order)**")
                # Months reversed (Dec -> Jan)
                months_in_year = sorted(year_data['month_num'].unique(), reverse=True)
                
                cols = st.columns(4)
                for i, m_num in enumerate(months_in_year):
                    month_name = datetime(2000, m_num, 1).strftime('%B')
                    month_data = year_data[year_data['month_num'] == m_num]
                    
                    buff = io.BytesIO()
                    with pd.ExcelWriter(buff, engine='xlsxwriter') as w:
                        month_data.to_excel(w, sheet_name=month_name, index=False)
                        
                    cols[i%4].download_button(f"📄 {month_name}", buff, f"{year}_{month_name}.xlsx")

def view_profile():
    st.title("👤 My Profile")
    user = st.session_state.user
    
    col_img, col_form = st.columns([1, 2])
    
    with col_img:
        # Display Profile Pic
        img_src = image_from_base64(user['profile_pic'])
        st.markdown(f"""
            <div style="text-align:center;">
                <img src="{img_src}" style="width:150px; height:150px; object-fit:cover; border-radius:50%; border: 4px solid {current_theme['primary']};">
            </div>
        """, unsafe_allow_html=True)
        
        # Upload New Pic
        new_pic = st.file_uploader("Change Photo", type=['png', 'jpg', 'jpeg'])
        if new_pic:
            b64_pic = get_image_base64(new_pic)
            run_query("UPDATE users SET profile_pic = ? WHERE id = ?", (b64_pic, user['id']))
            st.session_state.user['profile_pic'] = b64_pic
            log_activity("Profile Update", "Changed profile picture")
            st.rerun()

    with col_form:
        with st.form("profile_edit"):
            st.subheader("Basic Details")
            c1, c2 = st.columns(2)
            
            # Fetch fresh
            curr = run_query("SELECT * FROM users WHERE id=?", (user['id'],), fetch=True)[0]
            
            name = c1.text_input("Full Name", value=curr['name'])
            password = c2.text_input("New Password (Optional)", type="password")
            dob = c1.date_input("Date of Birth", value=datetime.strptime(curr['dob'], '%Y-%m-%d') if curr['dob'] else None)
            gender = c2.selectbox("Gender", ["Male", "Female", "Other"], index=["Male", "Female", "Other"].index(curr['gender']) if curr['gender'] in ["Male", "Female", "Other"] else 0)
            phone = c1.text_input("Phone", value=curr['phone'] if curr['phone'] else "")
            address = c2.text_area("Address", value=curr['address'] if curr['address'] else "")
            
            if st.form_submit_button("Save Changes"):
                q = "UPDATE users SET name=?, dob=?, gender=?, phone=?, address=?"
                p = [name, str(dob), gender, phone, address]
                if password:
                    q += ", password=?"
                    p.append(password)
                q += " WHERE id=?"
                p.append(user['id'])
                
                run_query(q, tuple(p))
                
                # Update Session
                st.session_state.user['name'] = name
                log_activity("Profile Update", "Updated personal details")
                st.success("Profile Updated")
                time.sleep(1)
                st.rerun()

# --- LANDING PAGE ---
def landing_page():
    # Modern Login Interface
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown(f"""
            <div class="login-card">
                <div class="login-header">
                    <h1>TSRS</h1>
                    <p>Robotics Lab Inventory System</p>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        with st.form("login_form"):
            st.markdown("### Secure Sign In")
            u = st.text_input("Employee ID", placeholder="e.g. admin")
            p = st.text_input("Password", type="password", placeholder="•••••••")
            
            if st.form_submit_button("Login", type="primary", use_container_width=True):
                user = run_query("SELECT * FROM users WHERE emp_id = ? AND password = ?", (u, p), fetch=True)
                if user:
                    user_data = user[0]
                    st.session_state.user = dict(user_data)
                    token = create_session(user_data['id'])
                    st.query_params['session_token'] = token
                    log_activity("Login", "User logged in")
                    st.rerun()
                else:
                    st.error("Invalid Credentials")

    st.markdown("""
        <div class="footer">
            Created by <b>Blackquest</b>
        </div>
    """, unsafe_allow_html=True)

# --- INVENTORY VIEW WITH BULK UPLOAD (EXCEL) ---
def view_inventory():
    st.title("📦 Inventory Management")
    
    tab1, tab2, tab3 = st.tabs(["🔎 View Inventory", "➕ Add Single Item", "📂 Bulk Upload (Excel)"])
    
    # 1. VIEW TAB
    with tab1:
        df = pd.read_sql_query("SELECT * FROM inventory", get_db_connection())
        st.dataframe(df, use_container_width=True)
        
        if st.session_state.user['role'] == 'admin':
            with st.expander("🗑️ Delete Item"):
                if not df.empty:
                    del_name = st.selectbox("Select Item", df['name'].tolist())
                    if st.button("Delete Item"):
                        run_query("DELETE FROM inventory WHERE name = ?", (del_name,))
                        log_activity("Delete Item", f"Deleted {del_name}")
                        st.rerun()

    # 2. ADD TAB
    with tab2:
        with st.form("add_i"):
            n = st.text_input("Name")
            c = st.selectbox("Category", ["Sensors", "Motors", "Microcontrollers", "Power", "Tools", "Others"])
            q = st.number_input("Quantity", 0)
            ms = st.number_input("Min Stock", 5)
            p = st.number_input("Price", 0.0)
            l = st.text_input("Location", "Bin A")
            
            if st.form_submit_button("Add Item"):
                run_query("INSERT INTO inventory (name, category, quantity, min_stock, price, location) VALUES (?,?,?,?,?,?)", (n,c,q,ms,p,l))
                log_activity("Inventory", f"Added item {n}")
                st.success("Item Added")
                time.sleep(1)
                st.rerun()

    # 3. UPLOAD TAB (EXCEL)
    with tab3:
        st.subheader("Import Data via Excel")
        st.markdown("""
        **Instructions:**
        1. Upload a `.xlsx` file.
        2. Required Columns: `name`, `category`, `quantity`, `price`
        3. Optional Columns: `min_stock`, `location`
        """)
        
        uploaded_file = st.file_uploader("Choose Excel File", type=['xlsx'])
        
        if uploaded_file:
            try:
                # Read Excel
                df_upload = pd.read_excel(uploaded_file)
                st.write("Preview:")
                st.dataframe(df_upload.head())
                
                # Check column headers (case insensitive handling)
                cols = [c.lower() for c in df_upload.columns]
                
                if st.button("Confirm Import"):
                    count = 0
                    for index, row in df_upload.iterrows():
                        # Normalize row keys to lowercase for matching
                        row_lower = {k.lower(): v for k, v in row.items()}
                        
                        if 'name' in row_lower and pd.notna(row_lower['name']):
                            name = row_lower['name']
                            cat = row_lower.get('category', 'Others')
                            qty = row_lower.get('quantity', 0)
                            price = row_lower.get('price', 0.0)
                            ms = row_lower.get('min_stock', 5)
                            loc = row_lower.get('location', 'Unknown')
                            
                            # Insert into DB
                            run_query("INSERT INTO inventory (name, category, quantity, min_stock, price, location) VALUES (?,?,?,?,?,?)", 
                                      (name, cat, qty, ms, price, loc))
                            count += 1
                    
                    log_activity("Bulk Upload", f"Imported {count} items via Excel")
                    st.success(f"Successfully added {count} items to the database.")
                    time.sleep(2)
                    st.rerun()
            except Exception as e:
                st.error(f"Error reading Excel file: {e}")

def view_stock_ops():
    st.title("🔄 Stock Operations")
    df = pd.read_sql_query("SELECT * FROM inventory", get_db_connection())
    if df.empty: return
    
    c1, c2 = st.columns(2)
    with c1:
        with st.form("in"):
            i = st.selectbox("Item", df['name'])
            q = st.number_input("Qty", 1)
            if st.form_submit_button("Stock In"):
                run_query("UPDATE inventory SET quantity = quantity + ? WHERE name = ?", (q, i))
                run_query("INSERT INTO transactions (item_name, type, quantity, user) VALUES (?,?,?,?)", (i,'in',q,st.session_state.user['name']))
                log_activity("Stock In", f"Added {q} to {i}")
                st.success("Updated"); st.rerun()
    with c2:
        with st.form("out"):
            i = st.selectbox("Item", df['name'], key='o')
            q = st.number_input("Qty", 1)
            if st.form_submit_button("Stock Out"):
                run_query("UPDATE inventory SET quantity = quantity - ? WHERE name = ?", (q, i))
                run_query("INSERT INTO transactions (item_name, type, quantity, user) VALUES (?,?,?,?)", (i,'out',q,st.session_state.user['name']))
                log_activity("Stock Out", f"Removed {q} from {i}")
                st.success("Updated"); st.rerun()

def view_shopping():
    st.title("🛒 Shopping List")
    df = pd.read_sql_query("SELECT * FROM inventory WHERE quantity < min_stock", get_db_connection())
    st.dataframe(df)

def view_users():
    st.title("👥 User Management")
    df = pd.read_sql_query("SELECT emp_id, name, role FROM users", get_db_connection())
    st.dataframe(df)

def view_settings():
    st.title("⚙️ Settings")
    t = st.selectbox("Theme", list(THEMES.keys()))
    if t != st.session_state.theme:
        st.session_state.theme = t; st.rerun()

# --- MAIN ---
def main():
    init_db()
    
    # Session Restore
    if 'user' not in st.session_state: st.session_state.user = None
    if st.session_state.user is None and 'session_token' in st.query_params:
        user = validate_session(st.query_params['session_token'])
        if user: st.session_state.user = dict(user)

    if st.session_state.user is None:
        landing_page()
    else:
        # Permission Handling
        perms_json = run_query("SELECT permissions FROM roles WHERE name = ?", (st.session_state.user['role'],), fetch=True)[0]['permissions']
        perms = json.loads(perms_json)
        
        # Sidebar
        with st.sidebar:
            # Profile Pic Mini
            img_src = image_from_base64(st.session_state.user['profile_pic'])
            st.markdown(f"<div style='text-align:center; margin-bottom:10px;'><img src='{img_src}' style='width:80px; height:80px; border-radius:50%; object-fit:cover; border:2px solid {current_theme['primary']};'></div>", unsafe_allow_html=True)
            st.markdown(f"<div style='text-align:center'><b>{st.session_state.user['name']}</b><br><small>{st.session_state.user['role'].upper()}</small></div>", unsafe_allow_html=True)
            st.markdown("---")
            
            # Nav
            nav_map = {
                "Dashboard": "📊", "Inventory": "📦", "Stock Operations": "🔄", 
                "Reports": "📑", "Audit Logs": "🛡️", "Shopping List": "🛒", 
                "User Management": "👥", "Settings": "⚙️"
            }
            
            # Everyone sees Profile
            if st.button("👤 My Profile", use_container_width=True):
                st.session_state.current_view = "My Profile"
                st.rerun()
                
            for p, icon in nav_map.items():
                if p in perms:
                    if st.button(f"{icon} {p}", use_container_width=True):
                        st.session_state.current_view = p
                        st.rerun()
                        
            st.markdown("---")
            if st.button("🚪 Logout"): logout_user()

        # Route
        if 'current_view' not in st.session_state: st.session_state.current_view = "Dashboard"
        v = st.session_state.current_view
        
        if v == "My Profile": view_profile()
        elif v == "Dashboard": view_dashboard()
        elif v == "Inventory" and v in perms: view_inventory()
        elif v == "Stock Operations" and v in perms: view_stock_ops()
        elif v == "Reports" and v in perms: view_reports()
        elif v == "Audit Logs" and v in perms: view_audit_logs()
        elif v == "Shopping List" and v in perms: view_shopping()
        elif v == "User Management" and v in perms: view_users()
        elif v == "Settings" and v in perms: view_settings()
        elif v not in perms: st.error("⛔ Access Denied")

if __name__ == '__main__':
    main()
