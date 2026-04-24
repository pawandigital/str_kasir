import streamlit as st
import sqlite3
import uuid
import json
from datetime import datetime
import pandas as pd  # <--- Tambahkan import ini untuk mengelola tabel Dataframe
import hashlib       # <--- Tambahkan import ini untuk keamanan password

# 1. SETUP & KONFIGURASI HALAMAN
# set_page_config harus menjadi pemanggilan Streamlit pertama di script
st.set_page_config(
    page_title="SaaS POS System", 
    page_icon="🛒", 
    layout="wide"
)

# 2. INISIALISASI DATABASE
DB_NAME = "database.db"

def init_db():
    """Membuat koneksi ke SQLite dan menyiapkan tabel jika belum ada."""
    # Connect ke database (akan membuat file database.db otomatis jika belum ada)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Membuat Tabel Users (Multi-tenant basis)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            password_hash TEXT,
            store_name TEXT
        )
    ''')

    # Membuat Tabel Products
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            product_id TEXT PRIMARY KEY,
            user_id TEXT,
            name TEXT,
            category TEXT,
            price REAL,
            stock INTEGER,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')

    # Membuat Tabel Transactions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id TEXT PRIMARY KEY,
            user_id TEXT,
            timestamp DATETIME,
            items_json TEXT,
            total_amount REAL,
            payment_type TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')

    # Simpan perubahan dan tutup koneksi
    conn.commit()
    conn.close()

# --- FUNGSI KEAMANAN (BARU) ---
def hash_password(password):
    """Mengenkripsi password menggunakan SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

# --- TAMBAHAN PHASE 2: DUMMY DATA & STATE ---
def seed_dummy_data():
    """Memasukkan data toko dan produk awal agar kasir bisa langsung dicoba."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        # Insert Dummy User
        user_id = str(uuid.uuid4())
        # Kita enkripsi password 'admin123' untuk akun demo ini
        cursor.execute("INSERT INTO users (user_id, username, password_hash, store_name) VALUES (?, ?, ?, ?)", 
                       (user_id, 'admin', hash_password('admin123'), 'Toko Demo UMKM'))
        
        # Insert Dummy Products
        products = [
            (str(uuid.uuid4()), user_id, 'Kopi Susu Gula Aren', 'Minuman', 18000, 50),
            (str(uuid.uuid4()), user_id, 'Roti Bakar Coklat', 'Makanan', 15000, 30),
            (str(uuid.uuid4()), user_id, 'Mie Goreng Spesial', 'Makanan', 22000, 40)
        ]
        cursor.executemany("INSERT INTO products (product_id, user_id, name, category, price, stock) VALUES (?, ?, ?, ?, ?, ?)", products)
        conn.commit()
    conn.close()

def init_session_state():
    """Inisialisasi state untuk menyimpan keranjang belanja dan status login."""
    if 'cart' not in st.session_state:
        st.session_state.cart = []
    
    # State untuk fitur Autentikasi/Login
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'active_user_id' not in st.session_state:
        st.session_state.active_user_id = None
    if 'store_name' not in st.session_state:
        st.session_state.store_name = ""

# --- TAMBAHAN PHASE 5: HALAMAN AUTENTIKASI ---
def page_auth():
    st.markdown("<h1 style='text-align: center;'>🛒 SaaS POS System</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Solusi Kasir & Manajemen Toko Berbasis Data</p>", unsafe_allow_html=True)
    st.write("---")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab_login, tab_register = st.tabs(["🔑 Login", "📝 Daftar Toko Baru"])
        
        with tab_login:
            st.subheader("Masuk ke Akun Anda")
            log_user = st.text_input("Username", key="log_user")
            log_pass = st.text_input("Password", type="password", key="log_pass")
            if st.button("Login", type="primary", use_container_width=True):
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute("SELECT user_id, store_name FROM users WHERE username=? AND password_hash=?", 
                               (log_user, hash_password(log_pass)))
                user = cursor.fetchone()
                conn.close()
                
                if user:
                    st.session_state.authenticated = True
                    st.session_state.active_user_id = user[0]
                    st.session_state.store_name = user[1]
                    st.success("Login Berhasil!")
                    st.rerun()
                else:
                    st.error("Username atau Password salah!")
                    
            st.info("💡 **Demo Akun:** Username: `admin`, Password: `admin123`")

        with tab_register:
            st.subheader("Buat Akun UMKM")
            reg_store = st.text_input("Nama Toko / Bisnis")
            reg_user = st.text_input("Username Pilihan")
            reg_pass = st.text_input("Password", type="password")
            
            if st.button("Daftar Sekarang", type="primary", use_container_width=True):
                if not reg_store or not reg_user or not reg_pass:
                    st.error("Semua kolom harus diisi!")
                else:
                    conn = sqlite3.connect(DB_NAME)
                    cursor = conn.cursor()
                    # Cek apakah username sudah ada
                    cursor.execute("SELECT user_id FROM users WHERE username=?", (reg_user,))
                    if cursor.fetchone():
                        st.error("Username sudah terdaftar! Pilih username lain.")
                    else:
                        new_user_id = str(uuid.uuid4())
                        cursor.execute("INSERT INTO users (user_id, username, password_hash, store_name) VALUES (?, ?, ?, ?)",
                                       (new_user_id, reg_user, hash_password(reg_pass), reg_store))
                        conn.commit()
                        st.success("Pendaftaran Berhasil! Silakan Login di tab sebelah kiri.")
                    conn.close()

# --- TAMBAHAN PHASE 2: HALAMAN KASIR ---
def page_kasir():
    st.header("🛒 Mesin Kasir")
    
    # Ambil data produk dari DB
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT product_id, name, price, stock FROM products WHERE user_id = ?", (st.session_state.active_user_id,))
    products = cursor.fetchall()
    conn.close()

    if not products:
        st.warning("Belum ada produk. Silakan tambah produk di menu Inventory.")
        return

    # Layout Kasir: Kiri (Pilih Menu), Kanan (Keranjang)
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Pilih Produk")
        # Format dropdown agar informatif (Nama - Harga - Sisa Stok)
        product_options = {p[0]: f"{p[1]} - Rp {p[2]:,.0f} (Stok: {p[3]})" for p in products}
        selected_prod_id = st.selectbox("Cari / Pilih Item", options=list(product_options.keys()), format_func=lambda x: product_options[x])
        
        qty = st.number_input("Jumlah", min_value=1, value=1, step=1)
        
        if st.button("Tambah ke Keranjang", type="primary"):
            # Cari detail produk yg dipilih berdasarkan ID
            prod_detail = next(p for p in products if p[0] == selected_prod_id)
            if qty > prod_detail[3]:
                st.error("Gagal: Stok produk tidak mencukupi!")
            else:
                # Cek apakah item sudah ada di keranjang, jika ada update qty-nya
                existing_item = next((item for item in st.session_state.cart if item['id'] == selected_prod_id), None)
                if existing_item:
                    existing_item['qty'] += qty
                    existing_item['subtotal'] = existing_item['price'] * existing_item['qty']
                else:
                    st.session_state.cart.append({
                        "id": prod_detail[0],
                        "name": prod_detail[1],
                        "price": prod_detail[2],
                        "qty": qty,
                        "subtotal": prod_detail[2] * qty
                    })
                st.success(f"{qty}x {prod_detail[1]} ditambahkan ke keranjang!")
                st.rerun()

    with col2:
        st.subheader("Keranjang Belanja")
        # Menampilkan isi keranjang
        if not st.session_state.cart:
            st.info("Keranjang masih kosong.")
        else:
            total_amount = 0
            for item in st.session_state.cart:
                st.write(f"**{item['name']}**")
                col_a, col_b = st.columns([2, 1])
                col_a.write(f"{item['qty']} x Rp {item['price']:,.0f}")
                col_b.write(f"**Rp {item['subtotal']:,.0f}**")
                total_amount += item['subtotal']
            
            st.divider()
            st.write(f"### Total: Rp {total_amount:,.0f}")
            
            payment_type = st.radio("Metode Pembayaran", ["Tunai", "QRIS"])
            
            if st.button("Bayar Sekarang", type="primary", use_container_width=True):
                # Proses 1: Catat transaksi ke DB
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                
                transaction_id = str(uuid.uuid4())
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                items_json = json.dumps(st.session_state.cart)
                
                cursor.execute(
                    "INSERT INTO transactions (transaction_id, user_id, timestamp, items_json, total_amount, payment_type) VALUES (?, ?, ?, ?, ?, ?)",
                    (transaction_id, st.session_state.active_user_id, timestamp, items_json, total_amount, payment_type)
                )
                
                # Proses 2: Kurangi stok produk secara otomatis
                for item in st.session_state.cart:
                    cursor.execute("UPDATE products SET stock = stock - ? WHERE product_id = ?", (item['qty'], item['id']))
                
                conn.commit()
                conn.close()
                
                # Proses 3: Bersihkan keranjang dan berikan feedback sukses
                st.session_state.cart = []
                st.success(f"Transaksi Berhasil Disimpan! (ID: {transaction_id[:8]})")
                st.balloons() # Animasi balon sebagai micro-interaction yang menyenangkan

# --- TAMBAHAN PHASE 3: HALAMAN INVENTORY ---
def page_inventory():
    st.header("📦 Manajemen Inventory")
    st.write("Kelola daftar produk dan stok toko Anda di sini.")

    # Bagian 1: Form Tambah Produk Baru menggunakan st.expander agar UI tidak penuh
    with st.expander("➕ Tambah Produk Baru", expanded=False):
        # st.form berguna agar halaman tidak me-refresh sebelum tombol submit ditekan
        with st.form("form_tambah_produk", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                new_name = st.text_input("Nama Produk", placeholder="Cth: Kopi Kenangan")
                new_category = st.selectbox("Kategori", ["Makanan", "Minuman", "Snack", "Lainnya"])
            with col2:
                new_price = st.number_input("Harga Jual (Rp)", min_value=0, step=1000)
                new_stock = st.number_input("Stok Awal", min_value=0, step=1)
            
            submitted = st.form_submit_button("Simpan Produk", type="primary")
            
            if submitted:
                if not new_name.strip():
                    st.error("Gagal: Nama produk tidak boleh kosong!")
                else:
                    # Simpan ke Database
                    conn = sqlite3.connect(DB_NAME)
                    cursor = conn.cursor()
                    new_id = str(uuid.uuid4())
                    cursor.execute(
                        "INSERT INTO products (product_id, user_id, name, category, price, stock) VALUES (?, ?, ?, ?, ?, ?)",
                        (new_id, st.session_state.active_user_id, new_name, new_category, new_price, new_stock)
                    )
                    conn.commit()
                    conn.close()
                    st.success(f"Produk '{new_name}' berhasil ditambahkan!")
                    st.rerun() # Refresh halaman untuk mengupdate tabel di bawahnya

    # Bagian 2: Tabel Daftar Produk
    st.subheader("Daftar Produk & Stok")
    
    conn = sqlite3.connect(DB_NAME)
    # Menggunakan Pandas read_sql_query untuk langsung mengubah output SQL menjadi DataFrame
    df_products = pd.read_sql_query(
        "SELECT name AS 'Nama Produk', category AS 'Kategori', price AS 'Harga (Rp)', stock AS 'Sisa Stok' FROM products WHERE user_id = ?", 
        conn, 
        params=(st.session_state.active_user_id,)
    )
    conn.close()

    if df_products.empty:
        st.info("Belum ada produk. Silakan tambahkan produk baru di atas.")
    else:
        # Menampilkan tabel interaktif yang cantik
        st.dataframe(df_products, use_container_width=True, hide_index=True)

# --- TAMBAHAN PHASE 4: HALAMAN DASHBOARD ANALYTICS ---
def page_dashboard():
    st.header("📊 Business Intelligence Dashboard")
    st.write("Wawasan data real-time untuk pengambilan keputusan bisnis Anda.")

    # 1. Ambil data transaksi dari database
    conn = sqlite3.connect(DB_NAME)
    df_trx = pd.read_sql_query(
        "SELECT transaction_id, timestamp, items_json, total_amount, payment_type FROM transactions WHERE user_id = ?",
        conn,
        params=(st.session_state.active_user_id,)
    )
    conn.close()

    if df_trx.empty:
        st.info("Belum ada data transaksi. Silakan lakukan beberapa penjualan di menu Kasir terlebih dahulu.")
        return

    # --- DATA PREPARATION (Mengekstrak JSON dan Format Waktu) ---
    df_trx['timestamp'] = pd.to_datetime(df_trx['timestamp'])
    
    # Membongkar items_json menjadi dataframe item tersendiri
    all_items = []
    for index, row in df_trx.iterrows():
        items = json.loads(row['items_json'])
        for item in items:
            all_items.append({
                'Nama Produk': item['name'],
                'Qty Terjual': item['qty'],
                'Pendapatan': item['subtotal']
            })
    df_items = pd.DataFrame(all_items)

    # --- BAGIAN ATAS: METRIK UTAMA (KPI) ---
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("💰 Total Omzet", f"Rp {df_trx['total_amount'].sum():,.0f}")
    with col2:
        st.metric("🧾 Total Transaksi", f"{len(df_trx)} Struk")
    with col3:
        total_items_sold = df_items['Qty Terjual'].sum() if not df_items.empty else 0
        st.metric("📦 Item Terjual", f"{total_items_sold} Unit")

    st.divider()

    # --- BAGIAN TENGAH: GRAFIK FAST MOVING & PEMBAYARAN ---
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.subheader("🔥 Produk Fast-Moving (Top Sales)")
        if not df_items.empty:
            # Mengelompokkan berdasarkan nama produk dan menjumlahkan kuantitas
            df_fast_moving = df_items.groupby('Nama Produk')['Qty Terjual'].sum().reset_index()
            # Streamlit bar_chart menjadikan index sebagai sumbu X
            st.bar_chart(df_fast_moving.set_index('Nama Produk'), color="#ff4b4b")
        else:
            st.write("Data produk belum cukup.")

    with col_chart2:
        st.subheader("💳 Tren Metode Pembayaran")
        # Mengelompokkan berdasarkan tipe pembayaran
        df_payment = df_trx.groupby('payment_type')['transaction_id'].count().reset_index()
        df_payment.rename(columns={'transaction_id': 'Jumlah Transaksi'}, inplace=True)
        st.bar_chart(df_payment.set_index('payment_type'), color="#0068c9")

    # --- BAGIAN BAWAH: ANALISIS JAM SIBUK ---
    st.subheader("⏰ Analisis Jam Sibuk (Peak Hours)")
    # Mengekstrak jam dari timestamp
    df_trx['Jam'] = df_trx['timestamp'].dt.hour
    df_peak = df_trx.groupby('Jam')['transaction_id'].count().reset_index()
    df_peak.rename(columns={'transaction_id': 'Jumlah Transaksi'}, inplace=True)
    
    # Buat rentang jam 0-23 agar grafiknya tidak terputus meski ada jam kosong
    all_hours = pd.DataFrame({'Jam': range(24)})
    df_peak_complete = pd.merge(all_hours, df_peak, on='Jam', how='left').fillna(0)
    
    st.area_chart(df_peak_complete.set_index('Jam'), color="#29b5e8")

# 3. STRUKTUR APLIKASI UTAMA
def main():
    # Panggil inisialisasi awal
    init_db()
    seed_dummy_data()
    init_session_state()

    # Cek apakah user sudah login
    if not st.session_state.authenticated:
        page_auth()
    else:
        # Layout Sidebar Navigasi (Hanya muncul jika sudah login)
        with st.sidebar:
            st.title("🛒 POS SaaS")
            st.write(f"Toko: **{st.session_state.store_name}**")
            st.write("---")
            
            # Menu Navigasi
            menu = st.radio("Navigasi Utama", ["Kasir", "Inventory", "Dashboard"])
            
            st.write("---")
            if st.button("🚪 Logout", use_container_width=True):
                st.session_state.clear()
                st.rerun()

        # Routing Halaman
        if menu == "Kasir":
            page_kasir()
        elif menu == "Inventory":
            page_inventory() 
        elif menu == "Dashboard":
            page_dashboard()

if __name__ == "__main__":
    main()