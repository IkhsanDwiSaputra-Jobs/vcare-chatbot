# app.py
from dotenv import load_dotenv
load_dotenv()
from flask import (Flask, render_template, request, jsonify,
                   redirect, url_for, flash, session)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user, logout_user,
                         login_required, current_user)
from flask_bcrypt import Bcrypt
import datetime
import json
from serpapi import GoogleSearch
import os
from openai import OpenAI # [MODIFIKASI] Mengimpor kelas OpenAI secara langsung

app = Flask(__name__)

# KONEKSI KE DATABASE
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'kunci_rahasia_yang_sangat_aman_bro_default')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('SUPABASE_DB_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# [MODIFIKASI] Inisialisasi client OpenAI. 
# Kunci API akan diambil secara otomatis dari environment variable `OPENAI_API_KEY`
try:
    client = OpenAI()
    # Memeriksa apakah kunci API benar-benar ada
    if not client.api_key:
        print("PERINGATAN: Variabel environment OPENAI_API_KEY tidak ditemukan.")
except Exception as e:
    print(f"Error saat menginisialisasi client OpenAI: {e}")
    client = None


# === MODEL DATABASE (Tidak ada perubahan) ===
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(150), nullable=False)
    nim = db.Column(db.String(50), unique=True, nullable=False)
    diagnosa_history = db.relationship('DiagnosaHistory', backref='pasien', lazy=True)

    password_hash = db.Column(db.String(128), nullable=False)
    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

class DiagnosaHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    nama_lengkap_pasien = db.Column(db.String(150), nullable=False)
    tanggal_lahir_pasien = db.Column(db.Date, nullable=False)
    jenis_kelamin_pasien = db.Column(db.String(20), nullable=False)
    gejala_dialami_json = db.Column(db.Text, nullable=False)
    hasil_diagnosa_text = db.Column(db.Text, nullable=False)
    hasil_diagnosa_json = db.Column(db.Text, nullable=True)
    tanggal_diagnosa = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# === DATA HYBRID CASE-BASED (Tidak ada perubahan) ===
penyakit_cbr = {
    "KOPE01": "Gastritis Akut", "KOPE02": "Gastritis Kronis", "KOPE03": "Gastritis Erosif"
}
gejala_cbr = {
    "KDGJ01": {"nama": "Nyeri pada ulu hati", "bobot": 5},
    "KDGJ02": {"nama": "Mual dan ingin muntah", "bobot": 4},
    "KDGJ03": {"nama": "Perut terasa kembung", "bobot": 3},
    "KDGJ04": {"nama": "Kehilangan nafsu makan", "bobot": 4},
    "KDGJ05": {"nama": "Sering bersendawa", "bobot": 2},
    "KDGJ06": {"nama": "Cepat merasa kenyang saat makan", "bobot": 3},
    "KDGJ07": {"nama": "Rasa panas atau terbakar di dada (heartburn)", "bobot": 5},
    "KDGJ08": {"nama": "Muntah darah", "bobot": 5},
    "KDGJ09": {"nama": "Feses berwarna gelap atau hitam", "bobot": 5},
    "KDGJ10": {"nama": "Merasa lemas dan pusing", "bobot": 3},
    "KDGJ11": {"nama": "Penurunan berat badan tanpa sebab", "bobot": 4}
}
rules_cbr = {
    "KOPE01": ["KDGJ01", "KDGJ02", "KDGJ03", "KDGJ04", "KDGJ05", "KDGJ06"],
    "KOPE02": ["KDGJ01", "KDGJ04", "KDGJ06", "KDGJ07", "KDGJ10", "KDGJ11"],
    "KOPE03": ["KDGJ01", "KDGJ02", "KDGJ07", "KDGJ08", "KDGJ09"]
}

# === ROUTES AUTENTIKASI (Tidak ada perubahan) ===
@app.route('/')
def landing_page():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    return render_template('landing.html', title="Selamat Datang")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('home'))
    if request.method == 'POST':
        nama, nim, password = request.form.get('nama'), request.form.get('nim'),  request.form.get('password')
        if not all([nama, nim,  password]):
            flash('Semua field registrasi wajib diisi!', 'danger'); return redirect(url_for('register'))
        if  User.query.filter_by(nim=nim).first():
            flash('NIM sudah terdaftar.', 'warning'); return redirect(url_for('register'))
        try:
            new_user = User(nama=nama, nim=nim); new_user.set_password(password)
            db.session.add(new_user); db.session.commit()
            flash('Registrasi berhasil! Silakan login.', 'success'); return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback(); flash(f'Terjadi kesalahan: {str(e)}', 'danger')
    return render_template('register.html', title="Daftar Akun")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('home'))
    if request.method == 'POST':
        identifier, password = request.form.get('identifier'), request.form.get('password')
        user = User.query.filter((User.nama == identifier)  | (User.nim == identifier)).first()
        if user and user.check_password(password):
            login_user(user, remember=request.form.get('remember'))
            return redirect(request.args.get('next') or url_for('home'))
        else:
            flash('Login gagal. Periksa kembali data Anda.', 'danger')
    return render_template('login.html', title="Login")

@app.route('/logout')
@login_required
def logout():
    logout_user(); flash('Anda telah logout.', 'info'); return redirect(url_for('landing_page'))

@app.route('/home')
@login_required
def home():
    return render_template('home.html', title="Beranda VCare")

# === PROSES DIAGNOSA (ALUR CHAT) (Tidak ada perubahan) ===
@app.route('/mulai_diagnosa', methods=['GET', 'POST'])
@login_required
def mulai_diagnosa():
    if request.method == 'POST':
        nama_lengkap, tanggal_lahir_str, jenis_kelamin = request.form.get('nama_lengkap'), request.form.get('tanggal_lahir'), request.form.get('jenis_kelamin')
        if not all([nama_lengkap, tanggal_lahir_str, jenis_kelamin]):
            flash('Semua data diri wajib diisi!', 'danger'); return redirect(url_for('mulai_diagnosa'))
        try:
            datetime.datetime.strptime(tanggal_lahir_str, '%Y-%m-%d')
        except ValueError:
            flash('Format tanggal lahir tidak valid.', 'danger'); return redirect(url_for('mulai_diagnosa'))
        session['data_pasien_diagnosa'] = {'nama_lengkap': nama_lengkap, 'tanggal_lahir': tanggal_lahir_str, 'jenis_kelamin': jenis_kelamin}
        return redirect(url_for('chat_diagnosa_hybrid'))
    return render_template('form_data_diri.html', title="Data Diri Pasien")

@app.route('/chat_diagnosa')
@login_required
def chat_diagnosa_hybrid():
    if 'data_pasien_diagnosa' not in session:
        flash('Silakan isi data diri pasien terlebih dahulu.', 'warning')
        return redirect(url_for('mulai_diagnosa'))
    return render_template('chat_hybrid.html', title="Diagnosa Penyakit Lambung", gejala_list=gejala_cbr)

@app.route('/proses_diagnosa', methods=['POST'])
@login_required
def proses_diagnosa_endpoint():
    if 'data_pasien_diagnosa' not in session:
        return jsonify({'error': 'Sesi data pasien tidak ditemukan.'}), 400
    gejala_pengguna = request.form.getlist('gejala')
    if not gejala_pengguna:
        return jsonify({'error': 'Tidak ada gejala yang dipilih.'}), 400
    hasil_perhitungan = []
    for kode_penyakit, gejala_kasus_lama in rules_cbr.items():
        total_bobot_kasus_lama = sum(gejala_cbr[kode]['bobot'] for kode in gejala_kasus_lama)
        gejala_sama = [kode for kode in gejala_pengguna if kode in gejala_kasus_lama]
        total_bobot_gejala_sama = sum(gejala_cbr[kode]['bobot'] for kode in gejala_sama)
        similarity = (total_bobot_gejala_sama / total_bobot_kasus_lama) * 100 if total_bobot_kasus_lama > 0 else 0
        hasil_perhitungan.append({
            "kode_penyakit": kode_penyakit,
            "nama_penyakit": penyakit_cbr[kode_penyakit],
            "similarity": round(similarity, 2)
        })
    hasil_perhitungan.sort(key=lambda x: x['similarity'], reverse=True)
    if hasil_perhitungan[0]['similarity'] == 0:
        hasil_diagnosa_text = "Berdasarkan gejala, tidak ditemukan penyakit yang cocok."
    else:
        hasil_diagnosa_text = f"Hasil teratas: {hasil_perhitungan[0]['nama_penyakit']} ({hasil_perhitungan[0]['similarity']:.2f}%)."
    data_pasien = session['data_pasien_diagnosa']
    try:
        tgl_lahir = datetime.datetime.strptime(data_pasien['tanggal_lahir'], '%Y-%m-%d').date()
        gejala_dialami_untuk_db = {kode: gejala_cbr[kode]['nama'] for kode in gejala_pengguna}
        riwayat = DiagnosaHistory(
            user_id=current_user.id,
            nama_lengkap_pasien=data_pasien['nama_lengkap'],
            tanggal_lahir_pasien=tgl_lahir,
            jenis_kelamin_pasien=data_pasien['jenis_kelamin'],
            gejala_dialami_json=json.dumps(gejala_dialami_untuk_db, ensure_ascii=False),
            hasil_diagnosa_text=hasil_diagnosa_text,
            hasil_diagnosa_json=json.dumps(hasil_perhitungan, ensure_ascii=False)
        )
        db.session.add(riwayat)
        db.session.commit()
        session.pop('data_pasien_diagnosa', None)
    except Exception as e:
        db.session.rollback()
        print(f"Error saat menyimpan riwayat: {e}")
    return jsonify(hasil_perhitungan)

# === ROUTES RIWAYAT (Tidak ada perubahan) ===
@app.route('/riwayat_diagnosa')
@login_required
def riwayat_diagnosa():
    histories = DiagnosaHistory.query.filter_by(user_id=current_user.id).order_by(DiagnosaHistory.tanggal_diagnosa.desc()).all()
    for history in histories:
        try:
            history.gejala_parsed = list(json.loads(history.gejala_dialami_json).values())
        except (json.JSONDecodeError, TypeError):
            history.gejala_parsed = []
        try:
            history.hasil_parsed = json.loads(history.hasil_diagnosa_json)
        except (json.JSONDecodeError, TypeError, AttributeError):
            history.hasil_parsed = None
    return render_template('riwayat_diagnosa.html', title="Riwayat Diagnosa", histories=histories)

# === [MODIFIKASI] PENGATURAN CHAT UMUM DENGAN AI ===
@app.route('/chat_vcare_umum')
@login_required
def chat_vcare_umum():
    # [MODIFIKASI] Menghapus parameter yang tidak lagi digunakan di template
    return render_template('chat_fc.html',
                           title="Chat VCare Umum",
                           initial_message="Hallo! Saya VCare Assistant. Ada yang bisa saya bantu seputar informasi kesehatan lambung dan pencernaan?",
                           initial_bot_message="Silakan ketik pertanyaan Anda."
                           )

@app.route('/proses_chat_umum', methods=['POST'])
@login_required
def proses_chat_umum_endpoint():
    user_message = request.json.get('message')
    if not user_message:
        return jsonify({'bot_reply': "Maaf, saya tidak menerima pesan kosong."})

    if not client or not client.api_key:
        return jsonify({'bot_reply': "Maaf, fitur chat sedang tidak tersedia karena kunci API belum diatur di server."})

    system_prompt = """
    Anda adalah "VCare Assistant", sebuah AI asisten kesehatan yang ramah dan informatif.
    PERAN UTAMA ANDA:
    1. Memberikan informasi umum yang akurat mengenai penyakit gastritis (maag) dan gangguan sistem pencernaan lainnya (seperti GERD, dispepsia, tukak lambung).
    2. Menjawab pertanyaan seputar gejala, penyebab umum, dan tips pencegahan atau gaya hidup sehat terkait gangguan pencernaan.
    3. Memberikan penjelasan istilah medis terkait pencernaan dengan bahasa yang mudah dimengerti.

    ATURAN KETAT:
    1. JANGAN PERNAH MEMBERIKAN DIAGNOSA. Selalu sertakan disclaimer bahwa Anda bukan pengganti dokter. Contoh: "Informasi ini bersifat umum dan bukan pengganti nasihat medis profesional. Untuk diagnosa dan penanganan yang tepat, harap konsultasikan dengan dokter."
    2. JIKA PENGGUNA BERTANYA DI LUAR TOPIK KESEHATAN, PENCERNAAN, ATAU GASTRITIS, Anda **WAJIB** menolak dengan sopan dan mengarahkan kembali ke topik. Contoh penolakan: "Maaf, sebagai VCare Assistant, fokus saya adalah membantu dengan pertanyaan seputar kesehatan lambung dan sistem pencernaan. Apakah ada yang bisa saya bantu terkait topik tersebut?"
    3. Jangan menjawab pertanyaan tentang resep obat spesifik. Anda hanya boleh menyarankan konsultasi ke dokter atau apoteker.
    4. Jaga agar jawaban tetap ringkas, jelas, dan mudah dipahami oleh orang awam. Gunakan poin atau daftar jika memungkinkan untuk mempermudah pembacaan.
    5. Selalu berkomunikasi dalam Bahasa Indonesia yang baik dan sopan.
    """
    
    try:
        # [MODIFIKASI] Menggunakan client yang sudah diinisialisasi di atas
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7
        )
        bot_response = completion.choices[0].message.content
        return jsonify({'bot_reply': bot_response})

    except Exception as e:
        print(f"OpenAI API Error: {e}")
        return jsonify({'bot_reply': "Maaf, sepertinya sedang terjadi masalah koneksi dengan layanan AI kami. Silakan coba beberapa saat lagi."}), 500


# === ROUTES LAINNYA (Tidak ada perubahan) ===
@app.route('/cari-faskes')
@login_required
def cari_faskes():
    lat, lon = request.args.get('lat'), request.args.get('lon')
    if not lat or not lon:
        flash('Koordinat lokasi tidak ditemukan.', 'danger'); return redirect(url_for('home'))
    serpapi_key = os.getenv('SERPAPI_API_KEY')
    if not serpapi_key:
        flash('Kunci API SerpApi tidak dikonfigurasi.', 'danger'); return redirect(url_for('home'))
    params = {"engine": "google_maps", "q": "sakit | puskesmas | klinik | apotek | dokter", "ll": f"@{lat},{lon},16z", "hl": "id", "api_key": serpapi_key}
    places = []
    try:
        results_dict = GoogleSearch(params).get_dict()
        if 'error' in results_dict: raise Exception(results_dict['error'])
        for result in results_dict.get('local_results', []):
            places.append({'name': result.get('title'), 'address': result.get('address'), 'rating': result.get('rating'), 'reviews': result.get('reviews'), 'type': result.get('type'), 'thumbnail': result.get('thumbnail'), 'maps_url': f"https://www.google.com/maps/search/?api=1&query={result.get('title')}&query_place_id={result.get('place_id')}"})
    except Exception as e:
        print(f"ERROR: SerpApi: {e}")
    return render_template('hasil_faskes.html', places=places, user_lat=lat, user_lon=lon)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
