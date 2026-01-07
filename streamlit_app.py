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
    
    section[data-testid="stSidebar"] {{ background-color: {current_theme['bg_sidebar']}; }}
    
    div[data-testid="stMetric"] {{
        background-color: white; padding: 20px; border-radius: 12px;
        border-left: 5px solid {current_theme['primary']};
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }}
    
    .login-card {{
        background: white; padding: 2.5rem; border-radius: 1.5rem;
        box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
        width: 100%; max-width: 450px; border-top: 8px solid {current_theme['primary']};
    }}
    .login-header {{ text-align: center; margin-bottom: 2rem; }}
    .login-header h1 {{ color: {current_theme['primary']}; font-weight: 800; font-size: 2.5rem; margin: 0; }}
    .login-header p {{ color: #6b7280; font-size: 0.95rem; margin-top: 0.5rem; }}
    
    .logo-icon {{
        font-size: 80px;
        color: {current_theme['primary']};
        margin-bottom: 20px;
    }}
    
    .footer {{
        position: fixed; bottom: 0; left: 0; width: 100%;
        background-color: white; text-align: center; padding: 10px;
        font-size: 12px; color: #9CA3AF; border-top: 1px solid #E5E7EB;
        z-index: 999;
    }}
    
    .activity-card {{
        background: #f9fafb; padding: 10px 15px; border-radius: 8px;
        margin-bottom: 8px; border-left: 4px solid {current_theme['primary']};
    }}
    
    .procurement-item {{
        background: white; padding: 15px; border-radius: 10px;
        border: 1px solid #e5e7eb; margin-bottom: 10px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }}
    
    .step-indicator {{
        display: flex; justify-content: center; gap: 10px; margin-bottom: 20px;
    }}
    .step {{
        padding: 10px 20px; border-radius: 20px; font-weight: 600;
        background: #e5e7eb; color: #6b7280;
    }}
    .step.active {{
        background: {current_theme['primary']}; color: white;
    }}
    .step.completed {{
        background: #10b981; color: white;
    }}
    
    .po-card {{
        background: white; padding: 15px; border-radius: 10px;
        border: 1px solid #e5e7eb; margin-bottom: 10px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }}
    
    .category-tag {{
        display: inline-block;
        padding: 5px 12px;
        margin: 3px;
        border-radius: 15px;
        background: #e5e7eb;
        font-size: 14px;
    }}
</style>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
""", unsafe_allow_html=True)

# --- DATABASE ENGINE ---

def get_db_connection():
    conn = sqlite3.connect('robolab_v2.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 emp_id TEXT UNIQUE NOT NULL,
                 name TEXT NOT NULL,
                 password TEXT NOT NULL,
                 role TEXT NOT NULL,
                 dob TEXT, gender TEXT, address TEXT, phone TEXT,
                 profile_pic TEXT)''')
    
    try:
        c.execute("SELECT profile_pic FROM users LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE users ADD COLUMN profile_pic TEXT")
        conn.commit()

    c.execute('''CREATE TABLE IF NOT EXISTS roles (
                 name TEXT PRIMARY KEY,
                 permissions TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 name TEXT NOT NULL,
                 category TEXT,
                 location TEXT,
                 quantity INTEGER DEFAULT 0,
                 min_stock INTEGER DEFAULT 5,
                 price REAL DEFAULT 0.0)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 item_id INTEGER,
                 item_name TEXT,
                 type TEXT,
                 quantity INTEGER,
                 user TEXT,
                 timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                 notes TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (
                 token TEXT PRIMARY KEY,
                 user_id INTEGER,
                 expires_at DATETIME)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS activity_logs (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 user_name TEXT,
                 action TEXT,
                 details TEXT,
                 timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS purchase_orders (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 po_number TEXT UNIQUE NOT NULL,
                 created_by TEXT,
                 created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                 required_by DATE,
                 status TEXT DEFAULT 'Draft',
                 items_json TEXT,
                 total_items INTEGER,
                 mode TEXT,
                 justification TEXT)''')
    
    # NEW: Categories Table
    c.execute('''CREATE TABLE IF NOT EXISTS categories (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 name TEXT UNIQUE NOT NULL,
                 created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    # Seed default categories if empty
    c.execute("SELECT count(*) FROM categories")
    if c.fetchone()[0] == 0:
        default_categories = ["Sensors", "Motors", "Microcontrollers", "Power", "Tools", "Passive", "Others"]
        for cat in default_categories:
            c.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat,))
        conn.commit()
    
    # Migrate: Add categories from existing inventory items
    c.execute("SELECT DISTINCT category FROM inventory WHERE category IS NOT NULL AND category != ''")
    existing_cats = c.fetchall()
    for cat_row in existing_cats:
        cat_name = cat_row[0]
        if cat_name:
            c.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat_name,))
    conn.commit()

    # Seed Roles
    c.execute("SELECT count(*) FROM roles")
    if c.fetchone()[0] == 0:
        all_perms = json.dumps(["Dashboard", "Inventory", "Stock Operations", "Reports", "Procurement List", "User Management", "Audit Logs", "Settings"])
        c.execute("INSERT INTO roles (name, permissions) VALUES (?, ?)", ('admin', all_perms))
        
        asst_perms = json.dumps(["Dashboard", "Inventory", "Stock Operations", "Reports", "Procurement List"])
        c.execute("INSERT INTO roles (name, permissions) VALUES (?, ?)", ('assistant', asst_perms))
        conn.commit()
    else:
        c.execute("SELECT name, permissions FROM roles")
        roles = c.fetchall()
        for role in roles:
            perms = json.loads(role[1])
            if "Procurement List" not in perms:
                if "Shopping List" in perms:
                    perms.remove("Shopping List")
                perms.append("Procurement List")
                c.execute("UPDATE roles SET permissions = ? WHERE name = ?", (json.dumps(perms), role[0]))
        conn.commit()

    # Seed Users
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
        st.error(f"DB Error: {e}")
        return False

def log_activity(action, details):
    if 'user' in st.session_state and st.session_state.user:
        run_query("INSERT INTO activity_logs (user_name, action, details) VALUES (?, ?, ?)", 
                  (st.session_state.user['name'], action, details))

def get_image_base64(image_file):
    if image_file is not None:
        return base64.b64encode(image_file.read()).decode()
    return None

def image_from_base64(base64_str):
    if base64_str:
        return f"data:image/png;base64,{base64_str}"
    return "https://www.w3schools.com/howto/img_avatar.png"

def create_session(user_id):
    token = str(uuid.uuid4())
    expiry = datetime.now() + timedelta(minutes=5)
    run_query("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (token, user_id, expiry))
    return token

def validate_session(token):
    run_query("DELETE FROM sessions WHERE expires_at < ?", (datetime.now(),))
    data = run_query("SELECT user_id FROM sessions WHERE token = ? AND expires_at > ?", (token, datetime.now()), fetch=True)
    if data:
        run_query("UPDATE sessions SET expires_at = ? WHERE token = ?", (datetime.now() + timedelta(minutes=5), token))
        return run_query("SELECT * FROM users WHERE id = ?", (data[0]['user_id'],), fetch=True)[0]
    return None

def logout_user():
    if 'session_token' in st.query_params:
        run_query("DELETE FROM sessions WHERE token = ?", (st.query_params['session_token'],))
    st.query_params.clear()
    st.session_state.user = None
    st.rerun()

def generate_po_number():
    now = datetime.now()
    if now.month >= 4:
        academic_year = f"{now.year}-{str(now.year + 1)[2:]}"
    else:
        academic_year = f"{now.year - 1}-{str(now.year)[2:]}"
    
    if now.month >= 4:
        start_date = datetime(now.year, 4, 1)
    else:
        start_date = datetime(now.year - 1, 4, 1)
    
    existing = run_query("SELECT COUNT(*) as cnt FROM purchase_orders WHERE created_at >= ?", (start_date,), fetch=True)
    count = existing[0]['cnt'] + 1 if existing else 1
    
    po_number = f"TSRS/RoboLab/PO/{academic_year}/PO{count:04d}"
    return po_number

# --- CATEGORY HELPER ---
def get_categories():
    """Get all categories from database"""
    cats = run_query("SELECT name FROM categories ORDER BY name", fetch=True)
    return [c['name'] for c in cats] if cats else ["Others"]

def add_category(name):
    """Add a new category if it doesn't exist"""
    if name and name.strip():
        name = name.strip()
        run_query("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
        return True
    return False

def add_categories_from_list(category_list):
    """Add multiple categories from a list (used in bulk upload)"""
    added = 0
    for cat in category_list:
        if cat and str(cat).strip() and str(cat).lower() != 'nan':
            cat_name = str(cat).strip()
            result = run_query("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat_name,))
            if result:
                added += 1
    return added

# --- VIEWS ---

def view_dashboard():
    role = st.session_state.user['role']
    
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
    else:
        st.title(f"👋 Welcome, {st.session_state.user['name']}")
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
            st.info("No activity yet.")

def view_audit_logs():
    st.title("🛡️ Audit Logs")
    df = pd.read_sql_query("SELECT timestamp, user_name, action, details FROM activity_logs ORDER BY timestamp DESC", get_db_connection())
    st.dataframe(df, use_container_width=True)

def view_reports():
    st.title("📑 Reports")
    
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM transactions", conn)
    conn.close()
    
    if df.empty:
        st.warning("No transaction data available.")
        return

    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['year'] = df['timestamp'].dt.year
    df['month_num'] = df['timestamp'].dt.month
    
    years = sorted(df['year'].unique(), reverse=True)
    
    for year in years:
        with st.expander(f"📂 Year: {year}", expanded=(year==max(years))):
            year_data = df[df['year'] == year]
            
            buffer_annual = io.BytesIO()
            year_data.to_excel(buffer_annual, index=False, engine='openpyxl')
            buffer_annual.seek(0)
            
            col_main, col_months = st.columns([1, 3])
            with col_main:
                st.download_button(f"📥 Annual {year}", buffer_annual, f"Annual_{year}.xlsx")
                
            with col_months:
                st.write("**Monthly Reports:**")
                months_in_year = sorted(year_data['month_num'].unique(), reverse=True)
                cols = st.columns(4)
                for i, m_num in enumerate(months_in_year):
                    month_name = datetime(2000, m_num, 1).strftime('%B')
                    month_data = year_data[year_data['month_num'] == m_num]
                    
                    buff = io.BytesIO()
                    month_data.to_excel(buff, index=False, engine='openpyxl')
                    buff.seek(0)
                    cols[i%4].download_button(f"📄 {month_name}", buff, f"{year}_{month_name}.xlsx")

def view_profile():
    st.title("👤 My Profile")
    user = st.session_state.user
    
    col_img, col_form = st.columns([1, 2])
    
    with col_img:
        img_src = image_from_base64(user.get('profile_pic'))
        st.markdown(f"<div style='text-align:center;'><img src='{img_src}' style='width:150px; height:150px; object-fit:cover; border-radius:50%; border: 4px solid {current_theme['primary']};'></div>", unsafe_allow_html=True)
        
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
            
            curr = run_query("SELECT * FROM users WHERE id=?", (user['id'],), fetch=True)[0]
            
            name = c1.text_input("Full Name", value=curr['name'])
            password = c2.text_input("New Password (Optional)", type="password")
            
            dob_val = None
            if curr.get('dob'):
                try:
                    dob_val = datetime.strptime(curr['dob'], '%Y-%m-%d')
                except:
                    dob_val = None

            dob = c1.date_input("Date of Birth", value=dob_val)
            gender_options = ["Male", "Female", "Other"]
            gender_idx = gender_options.index(curr['gender']) if curr.get('gender') in gender_options else 0
            gender = c2.selectbox("Gender", gender_options, index=gender_idx)
            phone = c1.text_input("Phone", value=curr.get('phone') or "")
            address = c2.text_area("Address", value=curr.get('address') or "")
            
            if st.form_submit_button("Save Changes"):
                q = "UPDATE users SET name=?, dob=?, gender=?, phone=?, address=?"
                p = [name, str(dob), gender, phone, address]
                if password:
                    q += ", password=?"
                    p.append(password)
                q += " WHERE id=?"
                p.append(user['id'])
                
                run_query(q, tuple(p))
                st.session_state.user['name'] = name
                log_activity("Profile Update", "Updated personal details")
                st.success("Profile Updated")
                time.sleep(1)
                st.rerun()

def landing_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown(f"""
            <div class="login-card">
                <div class="login-header">
                    <i class="fa-solid fa-robot logo-icon"></i>
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

    st.markdown("<div class='footer'>Created by <b>Blackquest</b></div>", unsafe_allow_html=True)

# --- INVENTORY VIEW WITH DYNAMIC CATEGORIES ---
def view_inventory():
    st.title("📦 Inventory Management")
    
    tab1, tab2, tab3, tab4 = st.tabs(["🔎 View", "➕ Add Item", "📂 Bulk Upload", "🏷️ Manage Categories"])
    
    # Get current categories
    categories = get_categories()
    
    with tab1:
        df = pd.read_sql_query("SELECT * FROM inventory", get_db_connection())
        
        # Filter by category
        col_filter, col_search = st.columns([1, 2])
        with col_filter:
            filter_cat = st.selectbox("Filter by Category", ["All"] + categories, key="filter_cat")
        with col_search:
            search_term = st.text_input("Search Items", placeholder="Type to search...")
        
        # Apply filters
        if not df.empty:
            if filter_cat != "All":
                df = df[df['category'] == filter_cat]
            if search_term:
                df = df[df['name'].str.contains(search_term, case=False, na=False)]
        
        st.dataframe(df, use_container_width=True)
        
        if st.session_state.user['role'] == 'admin' and not df.empty:
            with st.expander("🗑️ Delete Item"):
                del_name = st.selectbox("Select Item", df['name'].tolist())
                if st.button("Delete"):
                    run_query("DELETE FROM inventory WHERE name = ?", (del_name,))
                    log_activity("Delete", f"Deleted {del_name}")
                    st.rerun()

    with tab2:
        with st.form("add_i"):
            n = st.text_input("Name")
            c = st.selectbox("Category", categories)
            q = st.number_input("Quantity", 0)
            ms = st.number_input("Min Stock", 5)
            p = st.number_input("Price", 0.0)
            l = st.text_input("Location", "Bin A")
            
            if st.form_submit_button("Add Item"):
                run_query("INSERT INTO inventory (name, category, quantity, min_stock, price, location) VALUES (?,?,?,?,?,?)", (n,c,q,ms,p,l))
                log_activity("Inventory", f"Added item {n}")
                st.success("Added!")
                st.rerun()

    with tab3:
        st.markdown("**Upload Excel (.xlsx)** with columns: `name`, `category`, `quantity`, `price`, `min_stock`, `location`")
        st.info("💡 New categories in the Excel file will be automatically added to the system.")
        
        uploaded_file = st.file_uploader("Choose File", type=['xlsx'])
        
        if uploaded_file:
            df_upload = pd.read_excel(uploaded_file)
            st.dataframe(df_upload.head())
            
            # Show new categories that will be added
            if 'category' in [col.lower() for col in df_upload.columns]:
                cat_col = [col for col in df_upload.columns if col.lower() == 'category'][0]
                new_cats = df_upload[cat_col].dropna().unique().tolist()
                existing_cats = get_categories()
                truly_new = [c for c in new_cats if c not in existing_cats]
                
                if truly_new:
                    st.warning(f"🆕 New categories will be added: {', '.join(truly_new)}")
            
            if st.button("Confirm Import"):
                count = 0
                new_categories = set()
                
                for _, row in df_upload.iterrows():
                    row_lower = {k.lower(): v for k, v in row.items()}
                    if 'name' in row_lower and pd.notna(row_lower['name']):
                        cat = row_lower.get('category', 'Others')
                        if pd.isna(cat) or not cat:
                            cat = 'Others'
                        
                        # Track new categories
                        new_categories.add(str(cat))
                        
                        run_query("INSERT INTO inventory (name, category, quantity, min_stock, price, location) VALUES (?,?,?,?,?,?)", 
                                  (row_lower['name'], cat, row_lower.get('quantity', 0), row_lower.get('min_stock', 5), row_lower.get('price', 0.0), row_lower.get('location', 'Unknown')))
                        count += 1
                
                # Add new categories to database
                added_cats = add_categories_from_list(new_categories)
                
                log_activity("Bulk Upload", f"Imported {count} items, {added_cats} new categories")
                st.success(f"Imported {count} items!")
                if added_cats > 0:
                    st.info(f"Added {added_cats} new categories to the system.")
                st.rerun()

    # NEW: Manage Categories Tab
    with tab4:
        st.subheader("🏷️ Category Management")
        
        # Display current categories
        st.markdown("**Current Categories:**")
        current_cats = get_categories()
        
        # Show as tags
        tags_html = "".join([f"<span class='category-tag'>{cat}</span>" for cat in current_cats])
        st.markdown(f"<div>{tags_html}</div>", unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Add new category
        col1, col2 = st.columns([3, 1])
        with col1:
            new_cat = st.text_input("New Category Name", placeholder="e.g., Displays, Cables, etc.")
        with col2:
            st.write("")
            st.write("")
            if st.button("➕ Add Category", use_container_width=True):
                if new_cat and new_cat.strip():
                    if new_cat.strip() in current_cats:
                        st.error("Category already exists!")
                    else:
                        add_category(new_cat.strip())
                        log_activity("Category", f"Added category: {new_cat.strip()}")
                        st.success(f"Added category: {new_cat.strip()}")
                        st.rerun()
                else:
                    st.error("Please enter a category name.")
        
        st.markdown("---")
        
        # Delete category (Admin only)
        if st.session_state.user['role'] == 'admin':
            with st.expander("🗑️ Delete Category", expanded=False):
                st.warning("⚠️ Deleting a category will NOT delete items in that category. They will retain their category label.")
                
                del_cat = st.selectbox("Select Category to Delete", current_cats)
                
                # Check if category is in use
                items_in_cat = run_query("SELECT COUNT(*) as cnt FROM inventory WHERE category = ?", (del_cat,), fetch=True)
                item_count = items_in_cat[0]['cnt'] if items_in_cat else 0
                
                if item_count > 0:
                    st.info(f"ℹ️ This category has {item_count} items.")
                
                if st.button("Delete Category", type="secondary"):
                    run_query("DELETE FROM categories WHERE name = ?", (del_cat,))
                    log_activity("Category", f"Deleted category: {del_cat}")
                    st.success(f"Deleted category: {del_cat}")
                    st.rerun()

def view_stock_ops():
    st.title("🔄 Stock Operations")
    
    df = pd.read_sql_query("SELECT * FROM inventory", get_db_connection())
    if df.empty:
        st.warning("No items in inventory. Add items first.")
        return
    
    col_in, col_out = st.columns(2)
    
    with col_in:
        st.markdown(f"<div style='background:#ecfdf5; padding:20px; border-radius:12px; border:2px solid #10b981;'>", unsafe_allow_html=True)
        st.subheader("📥 Stock In")
        with st.form("stock_in_form"):
            item_in = st.selectbox("Select Item", df['name'].tolist(), key="in_item")
            qty_in = st.number_input("Quantity to Add", min_value=1, value=1, key="in_qty")
            notes_in = st.text_input("Notes (e.g., Purchase Order #)", key="in_notes")
            
            if st.form_submit_button("➕ Add Stock", use_container_width=True):
                run_query("UPDATE inventory SET quantity = quantity + ? WHERE name = ?", (qty_in, item_in))
                run_query("INSERT INTO transactions (item_name, type, quantity, user, notes) VALUES (?,?,?,?,?)", 
                          (item_in, 'in', qty_in, st.session_state.user['name'], notes_in))
                log_activity("Stock In", f"Added {qty_in} to {item_in}")
                st.success(f"Added {qty_in} units to {item_in}")
                time.sleep(1)
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with col_out:
        st.markdown(f"<div style='background:#fef2f2; padding:20px; border-radius:12px; border:2px solid #ef4444;'>", unsafe_allow_html=True)
        st.subheader("📤 Stock Out")
        with st.form("stock_out_form"):
            item_out = st.selectbox("Select Item", df['name'].tolist(), key="out_item")
            qty_out = st.number_input("Quantity to Remove", min_value=1, value=1, key="out_qty")
            notes_out = st.text_input("Notes (e.g., Project Name)", key="out_notes")
            
            if st.form_submit_button("➖ Remove Stock", use_container_width=True):
                current_qty = df[df['name'] == item_out]['quantity'].values[0]
                if qty_out > current_qty:
                    st.error(f"Insufficient stock! Available: {current_qty}")
                else:
                    run_query("UPDATE inventory SET quantity = quantity - ? WHERE name = ?", (qty_out, item_out))
                    run_query("INSERT INTO transactions (item_name, type, quantity, user, notes) VALUES (?,?,?,?,?)", 
                              (item_out, 'out', qty_out, st.session_state.user['name'], notes_out))
                    log_activity("Stock Out", f"Removed {qty_out} from {item_out}")
                    st.success(f"Removed {qty_out} units from {item_out}")
                    time.sleep(1)
                    st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("📋 Recent Stock Activity")
    
    recent_trans = pd.read_sql_query("SELECT timestamp, item_name, type, quantity, user, notes FROM transactions ORDER BY timestamp DESC LIMIT 10", get_db_connection())
    
    if recent_trans.empty:
        st.info("No transactions recorded yet.")
    else:
        for _, row in recent_trans.iterrows():
            icon = "📥" if row['type'] == 'in' else "📤"
            color = "#10b981" if row['type'] == 'in' else "#ef4444"
            action = "Added" if row['type'] == 'in' else "Removed"
            
            st.markdown(f"""
                <div class="activity-card" style="border-left-color: {color};">
                    <strong>{icon} {action} {row['quantity']} × {row['item_name']}</strong><br>
                    <small style="color:#6b7280;">By {row['user']} | {row['timestamp']}</small>
                    {f"<br><small style='color:#9ca3af;'>Note: {row['notes']}</small>" if row['notes'] else ""}
                </div>
            """, unsafe_allow_html=True)

# --- PROCUREMENT LIST ---
def view_procurement():
    st.title("🛒 Procurement List")
    
    if 'procurement_step' not in st.session_state:
        st.session_state.procurement_step = 1
    if 'selected_items' not in st.session_state:
        st.session_state.selected_items = []
    if 'procurement_details' not in st.session_state:
        st.session_state.procurement_details = {}
    if 'global_justification' not in st.session_state:
        st.session_state.global_justification = ""
    if 'item_justifications' not in st.session_state:
        st.session_state.item_justifications = {}
    
    tab_new, tab_history = st.tabs(["📝 New Request", "📋 Purchase Order History"])
    
    with tab_new:
        step = st.session_state.procurement_step
        st.markdown(f"""
            <div class="step-indicator">
                <div class="step {'completed' if step > 1 else 'active' if step == 1 else ''}">1. Select Items</div>
                <div class="step {'completed' if step > 2 else 'active' if step == 2 else ''}">2. Fill Details</div>
                <div class="step {'completed' if step > 3 else 'active' if step == 3 else ''}">3. Preview</div>
                <div class="step {'active' if step == 4 else ''}">4. Download</div>
            </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        if step == 1:
            st.subheader("Step 1: Select Items for Procurement")
            
            df = pd.read_sql_query("SELECT * FROM inventory WHERE quantity < min_stock", get_db_connection())
            
            if df.empty:
                st.success("✅ All items are well-stocked! No procurement needed.")
                return
            
            st.warning(f"⚠️ {len(df)} items are below minimum stock level.")
            
            select_all = st.checkbox("Select All Items")
            
            selected = []
            for idx, row in df.iterrows():
                shortage = row['min_stock'] - row['quantity']
                
                col1, col2, col3, col4 = st.columns([0.5, 3, 1, 1])
                with col1:
                    checked = st.checkbox("", value=select_all, key=f"check_{idx}")
                with col2:
                    st.write(f"**{row['name']}** ({row['category']})")
                with col3:
                    st.write(f"Stock: {row['quantity']}")
                with col4:
                    st.write(f"🔴 Need: {shortage}")
                
                if checked:
                    selected.append({
                        'id': row['id'],
                        'name': row['name'],
                        'category': row['category'],
                        'current_stock': row['quantity'],
                        'min_stock': row['min_stock'],
                        'shortage': shortage,
                        'price': row['price']
                    })
            
            st.markdown("---")
            
            col1, col2 = st.columns([3, 1])
            with col2:
                if st.button("Proceed to Details ➡️", type="primary", use_container_width=True):
                    if len(selected) > 0:
                        st.session_state.selected_items = selected
                        st.session_state.item_justifications = {item['name']: "" for item in selected}
                        st.session_state.procurement_step = 2
                        st.rerun()
                    else:
                        st.error("Please select at least one item.")
        
        elif step == 2:
            st.subheader("Step 2: Fill Procurement Details")
            
            selected_items = st.session_state.selected_items
            
            st.markdown("### 📋 General Information")
            col1, col2 = st.columns(2)
            with col1:
                requested_by = st.text_input("Requested By", value=st.session_state.user['name'])
            with col2:
                required_by = st.date_input("Required By", value=datetime.now() + timedelta(days=7))
            
            col1, col2 = st.columns(2)
            with col1:
                mode = st.selectbox("Purchase Mode", ["Online", "Offline"])
            with col2:
                if mode == "Online":
                    default_link = st.text_input("Default Purchase Link (Optional)", placeholder="https://...")
                else:
                    default_link = ""
            
            st.markdown("### 📝 Common Justification")
            st.info("💡 Enter a justification below and click 'Apply to All Items' to copy it to all items.")
            
            global_just = st.text_area(
                "Common Justification", 
                value=st.session_state.global_justification,
                placeholder="Required for robotics lab projects and maintenance...", 
                key="global_just_input"
            )
            
            if st.button("✅ Apply to All Items", type="secondary"):
                st.session_state.global_justification = global_just
                for item in selected_items:
                    st.session_state.item_justifications[item['name']] = global_just
                st.success("Justification applied to all items!")
                st.rerun()
            
            st.markdown("---")
            st.markdown("### 📦 Item Details")
            
            item_details = []
            for idx, item in enumerate(selected_items):
                with st.expander(f"📦 {item['name']} (Shortage: {item['shortage']})", expanded=True):
                    col1, col2 = st.columns(2)
                    with col1:
                        qty = st.number_input("Quantity", min_value=1, value=int(item['shortage']), key=f"qty_{idx}")
                    with col2:
                        if mode == "Online":
                            link = st.text_input("Purchase Link", value=default_link, key=f"link_{idx}")
                        else:
                            link = "N/A"
                    
                    current_just = st.session_state.item_justifications.get(item['name'], "")
                    justification = st.text_area(
                        "Justification", 
                        value=current_just,
                        key=f"just_{idx}", 
                        height=80
                    )
                    st.session_state.item_justifications[item['name']] = justification
                    
                    item_details.append({
                        'Item Name': item['name'],
                        'Category': item['category'],
                        'Current Stock': item['current_stock'],
                        'Min Stock': item['min_stock'],
                        'Quantity Requested': qty,
                        'Unit Price': item['price'],
                        'Estimated Cost': qty * item['price'],
                        'Justification': justification,
                        'Mode': mode,
                        'Purchase Link': link
                    })
            
            st.markdown("---")
            
            col1, col2, col3 = st.columns([1, 1, 1])
            with col1:
                if st.button("⬅️ Back", use_container_width=True):
                    st.session_state.procurement_step = 1
                    st.rerun()
            with col3:
                if st.button("Preview ➡️", type="primary", use_container_width=True):
                    st.session_state.procurement_details = {
                        'requested_by': requested_by,
                        'required_by': str(required_by),
                        'mode': mode,
                        'items': item_details
                    }
                    st.session_state.procurement_step = 3
                    st.rerun()
        
        elif step == 3:
            st.subheader("Step 3: Preview Procurement Request")
            
            details = st.session_state.procurement_details
            
            st.markdown(f"""
                <div class="po-card">
                    <h4 style="color:{current_theme['primary']};">📋 Request Summary</h4>
                    <p><strong>Requested By:</strong> {details['requested_by']}</p>
                    <p><strong>Required By:</strong> {details['required_by']}</p>
                    <p><strong>Purchase Mode:</strong> {details['mode']}</p>
                    <p><strong>Total Items:</strong> {len(details['items'])}</p>
                </div>
            """, unsafe_allow_html=True)
            
            preview_df = pd.DataFrame(details['items'])
            st.dataframe(preview_df, use_container_width=True)
            
            total_cost = sum([item['Estimated Cost'] for item in details['items']])
            st.metric("Total Estimated Cost", f"₹{total_cost:,.2f}")
            
            st.markdown("---")
            
            col1, col2, col3 = st.columns([1, 1, 1])
            with col1:
                if st.button("⬅️ Back to Edit", use_container_width=True):
                    st.session_state.procurement_step = 2
                    st.rerun()
            with col3:
                if st.button("Generate PO ➡️", type="primary", use_container_width=True):
                    po_number = generate_po_number()
                    
                    run_query("""
                        INSERT INTO purchase_orders (po_number, created_by, required_by, status, items_json, total_items, mode, justification)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        po_number,
                        details['requested_by'],
                        details['required_by'],
                        'Generated',
                        json.dumps(details['items']),
                        len(details['items']),
                        details['mode'],
                        details['items'][0]['Justification'] if details['items'] else ''
                    ))
                    
                    log_activity("Procurement", f"Generated PO: {po_number}")
                    
                    st.session_state.generated_po = po_number
                    st.session_state.procurement_step = 4
                    st.rerun()
        
        elif step == 4:
            st.subheader("Step 4: Download Procurement Request")
            
            po_number = st.session_state.get('generated_po', 'N/A')
            details = st.session_state.procurement_details
            
            st.success(f"✅ Purchase Order Generated Successfully!")
            
            st.markdown(f"""
                <div class="po-card" style="text-align:center; padding:30px;">
                    <h2 style="color:{current_theme['primary']};">{po_number}</h2>
                    <p style="color:#6b7280;">Your Purchase Order Number</p>
                </div>
            """, unsafe_allow_html=True)
            
            items_df = pd.DataFrame(details['items'])
            items_df.insert(0, 'PO Number', po_number)
            items_df['Requested By'] = details['requested_by']
            items_df['Required By'] = details['required_by']
            
            column_order = [
                'PO Number', 'Item Name', 'Category', 'Current Stock', 'Min Stock',
                'Quantity Requested', 'Unit Price', 'Estimated Cost', 'Justification',
                'Mode', 'Purchase Link', 'Requested By', 'Required By'
            ]
            items_df = items_df[column_order]
            
            buffer = io.BytesIO()
            items_df.to_excel(buffer, index=False, engine='openpyxl')
            buffer.seek(0)
            
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.download_button(
                    label="📥 Download Excel File",
                    data=buffer,
                    file_name=f"{po_number.replace('/', '_')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            
            st.markdown("---")
            
            if st.button("🔄 Create New Request", use_container_width=True):
                st.session_state.procurement_step = 1
                st.session_state.selected_items = []
                st.session_state.procurement_details = {}
                st.session_state.global_justification = ""
                st.session_state.item_justifications = {}
                st.rerun()
    
    with tab_history:
        st.subheader("📋 Purchase Order History")
        
        pos = run_query("SELECT * FROM purchase_orders ORDER BY created_at DESC", fetch=True)
        
        if not pos:
            st.info("No purchase orders created yet.")
        else:
            for po in pos:
                with st.expander(f"📄 {po['po_number']} - {po['status']}", expanded=False):
                    col1, col2, col3 = st.columns(3)
                    col1.write(f"**Created By:** {po['created_by']}")
                    col2.write(f"**Created At:** {po['created_at'][:10]}")
                    col3.write(f"**Required By:** {po['required_by']}")
                    
                    st.write(f"**Total Items:** {po['total_items']}")
                    st.write(f"**Mode:** {po['mode']}")
                    
                    if po['items_json']:
                        items = json.loads(po['items_json'])
                        items_df = pd.DataFrame(items)
                        st.dataframe(items_df, use_container_width=True)
                    
                    col_dl, col_del = st.columns([3, 1])
                    
                    with col_dl:
                        if po['items_json']:
                            items_df = pd.DataFrame(items)
                            items_df.insert(0, 'PO Number', po['po_number'])
                            
                            buff = io.BytesIO()
                            items_df.to_excel(buff, index=False, engine='openpyxl')
                            buff.seek(0)
                            
                            st.download_button(
                                f"📥 Re-download",
                                buff,
                                f"{po['po_number'].replace('/', '_')}.xlsx",
                                key=f"dl_{po['id']}"
                            )
                    
                    with col_del:
                        if st.button(f"🗑️ Delete", key=f"del_{po['id']}", type="secondary"):
                            run_query("DELETE FROM purchase_orders WHERE id = ?", (po['id'],))
                            log_activity("Procurement Deleted", f"Deleted PO: {po['po_number']}")
                            st.success(f"Deleted {po['po_number']}")
                            time.sleep(1)
                            st.rerun()

def view_users():
    st.title("👥 User & Role Management")
    
    tab_users, tab_roles = st.tabs(["👤 Manage Users", "🔐 Manage Roles"])
    
    with tab_users:
        users_df = pd.read_sql_query("SELECT emp_id, name, role FROM users", get_db_connection())
        st.dataframe(users_df, use_container_width=True)
        
        col_add, col_edit = st.columns(2)
        
        with col_add:
            with st.expander("➕ Add New User", expanded=False):
                with st.form("create_user_form"):
                    roles_list = [r['name'] for r in run_query("SELECT name FROM roles", fetch=True)]
                    
                    new_emp = st.text_input("Employee ID")
                    new_name = st.text_input("Full Name")
                    new_pass = st.text_input("Password", type="password")
                    new_role = st.selectbox("Assign Role", roles_list)
                    
                    if st.form_submit_button("Create User"):
                        if run_query("INSERT INTO users (emp_id, name, password, role) VALUES (?, ?, ?, ?)", (new_emp, new_name, new_pass, new_role)):
                            log_activity("User Created", f"Created user {new_emp}")
                            st.success("User created!")
                            st.rerun()
                        else:
                            st.error("Error: Employee ID may already exist.")

        with col_edit:
            with st.expander("✏️ Edit User", expanded=False):
                user_to_edit = st.selectbox("Select User", users_df['emp_id'].tolist())
                
                if user_to_edit:
                    curr_user = run_query("SELECT * FROM users WHERE emp_id = ?", (user_to_edit,), fetch=True)[0]
                    roles_list = [r['name'] for r in run_query("SELECT name FROM roles", fetch=True)]
                    
                    with st.form("edit_user_form"):
                        edit_name = st.text_input("Name", value=curr_user['name'])
                        edit_role = st.selectbox("Role", roles_list, index=roles_list.index(curr_user['role']) if curr_user['role'] in roles_list else 0)
                        edit_pass = st.text_input("Reset Password (leave blank to keep)", type="password")
                        
                        if st.form_submit_button("Update User"):
                            q = "UPDATE users SET name=?, role=?"
                            p = [edit_name, edit_role]
                            if edit_pass:
                                q += ", password=?"
                                p.append(edit_pass)
                            q += " WHERE emp_id=?"
                            p.append(user_to_edit)
                            
                            run_query(q, tuple(p))
                            log_activity("User Updated", f"Updated user {user_to_edit}")
                            st.success("Updated!")
                            st.rerun()

    with tab_roles:
        st.info("Define custom roles and select which pages each role can access.")
        
        ALL_PAGES = ["Dashboard", "Inventory", "Stock Operations", "Reports", "Procurement List", "User Management", "Audit Logs", "Settings"]
        
        roles_data = run_query("SELECT * FROM roles", fetch=True)
        
        for role in roles_data:
            with st.expander(f"🔑 Role: {role['name'].upper()}", expanded=False):
                current_perms = json.loads(role['permissions'])
                
                with st.form(f"edit_role_{role['name']}"):
                    st.write(f"**Permissions for {role['name']}**")
                    
                    new_perms = []
                    cols = st.columns(4)
                    for i, page in enumerate(ALL_PAGES):
                        with cols[i % 4]:
                            if st.checkbox(page, value=(page in current_perms), key=f"perm_{role['name']}_{page}"):
                                new_perms.append(page)
                    
                    if st.form_submit_button("Save Permissions"):
                        run_query("UPDATE roles SET permissions = ? WHERE name = ?", (json.dumps(new_perms), role['name']))
                        log_activity("Role Updated", f"Updated permissions for {role['name']}")
                        st.success("Permissions updated!")
                        st.rerun()

        st.markdown("---")
        with st.form("new_role_form"):
            st.subheader("➕ Create New Role")
            new_role_name = st.text_input("Role Name (e.g., student_leader)").lower().replace(" ", "_")
            
            st.write("**Select Permissions:**")
            nr_perms = []
            cols = st.columns(4)
            for i, page in enumerate(ALL_PAGES):
                with cols[i % 4]:
                    if st.checkbox(page, key=f"new_role_{page}"):
                        nr_perms.append(page)
            
            if st.form_submit_button("Create Role"):
                if new_role_name:
                    run_query("INSERT INTO roles (name, permissions) VALUES (?, ?)", (new_role_name, json.dumps(nr_perms)))
                    log_activity("Role Created", f"Created role {new_role_name}")
                    st.success(f"Role '{new_role_name}' created!")
                    st.rerun()

def view_settings():
    st.title("⚙️ Settings")
    t = st.selectbox("Theme", list(THEMES.keys()))
    if t != st.session_state.theme:
        st.session_state.theme = t
        st.rerun()

# --- MAIN ---
def main():
    init_db()
    
    if 'user' not in st.session_state:
        st.session_state.user = None
    if st.session_state.user is None and 'session_token' in st.query_params:
        user = validate_session(st.query_params['session_token'])
        if user:
            st.session_state.user = dict(user)

    if st.session_state.user is None:
        landing_page()
    else:
        perms_data = run_query("SELECT permissions FROM roles WHERE name = ?", (st.session_state.user['role'],), fetch=True)
        if perms_data:
            perms = json.loads(perms_data[0]['permissions'])
        else:
            perms = []
        
        with st.sidebar:
            img_src = image_from_base64(st.session_state.user.get('profile_pic'))
            st.markdown(f"<div style='text-align:center; margin-bottom:10px;'><img src='{img_src}' style='width:80px; height:80px; border-radius:50%; object-fit:cover; border:2px solid {current_theme['primary']};'></div>", unsafe_allow_html=True)
            st.markdown(f"<div style='text-align:center'><b>{st.session_state.user['name']}</b><br><small>{st.session_state.user['role'].upper()}</small></div>", unsafe_allow_html=True)
            st.markdown("---")
            
            nav_map = {
                "Dashboard": "📊", 
                "Inventory": "📦", 
                "Stock Operations": "🔄", 
                "Reports": "📑", 
                "Audit Logs": "🛡️", 
                "Procurement List": "🛒", 
                "User Management": "👥", 
                "Settings": "⚙️"
            }
            
            if st.button("👤 My Profile", use_container_width=True):
                st.session_state.current_view = "My Profile"
                st.rerun()
                
            for p, icon in nav_map.items():
                if p in perms:
                    if st.button(f"{icon} {p}", use_container_width=True):
                        st.session_state.current_view = p
                        if p == "Procurement List":
                            st.session_state.procurement_step = 1
                            st.session_state.selected_items = []
                            st.session_state.procurement_details = {}
                            st.session_state.global_justification = ""
                            st.session_state.item_justifications = {}
                        st.rerun()
                        
            st.markdown("---")
            if st.button("🚪 Logout"):
                logout_user()

        if 'current_view' not in st.session_state:
            st.session_state.current_view = "Dashboard"
        v = st.session_state.current_view
        
        if v == "My Profile": 
            view_profile()
        elif v == "Dashboard": 
            view_dashboard()
        elif v == "Inventory" and v in perms: 
            view_inventory()
        elif v == "Stock Operations" and v in perms: 
            view_stock_ops()
        elif v == "Reports" and v in perms: 
            view_reports()
        elif v == "Audit Logs" and v in perms: 
            view_audit_logs()
        elif v == "Procurement List" and v in perms: 
            view_procurement()
        elif v == "User Management" and v in perms: 
            view_users()
        elif v == "Settings" and v in perms: 
            view_settings()
        elif v not in perms and v != "My Profile": 
            st.error("⛔ Access Denied")

if __name__ == '__main__':
    main()
