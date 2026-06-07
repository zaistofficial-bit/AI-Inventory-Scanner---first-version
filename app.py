# app.py - إصدار سريع وموثوق مع قراءة باركود pyzbar وإعادة تعيين الكاميرا
import streamlit as st
import pandas as pd
from io import BytesIO
from PIL import Image, ImageEnhance
import pyzbar.pyzbar as pyzbar
import google.generativeai as genai
import json
import re
from datetime import datetime

# ------------------- الإعدادات -------------------
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=GEMINI_API_KEY)

# ------------------- دوال قراءة الباركود -------------------
def enhance_barcode_image(image):
    """تحسين الصورة لقراءة الباركود"""
    gray = image.convert('L')
    enhancer = ImageEnhance.Contrast(gray)
    enhanced = enhancer.enhance(2.5)
    enlarged = enhanced.resize((int(enhanced.width*2), int(enhanced.height*2)), Image.Resampling.LANCZOS)
    return enlarged

def scan_barcode(image):
    """قراءة الباركود من الصورة"""
    if image is None:
        return None
    try:
        # محاولة على الصورة المحسنة
        enhanced = enhance_barcode_image(image)
        decoded = pyzbar.decode(enhanced)
        if decoded:
            return decoded[0].data.decode('utf-8').strip()
        # محاولة على الصورة الأصلية
        decoded = pyzbar.decode(image)
        if decoded:
            return decoded[0].data.decode('utf-8').strip()
    except Exception as e:
        st.warning(f"خطأ في القراءة: {e}")
    return None

# ------------------- دوال Gemini -------------------
def analyze_with_gemini(product_img, price_tag_img):
    prompt = """
    أنت خبير في المنتجات الإلكترونية. أخرج JSON فقط:
    {
        "product_name": "اسم المنتج",
        "brand": "العلامة التجارية",
        "category": "Laptop/Printer/Accessory/Mobile Accessory",
        "description": "وصف قصير (أقل من 10 كلمات)",
        "sku": "SKU مقترح مثل LAP-001",
        "price": "السعر المستخرج من ملصق السعر (إن وجد، وإلا نص فارغ)"
    }
    """
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        contents = [prompt, product_img]
        if price_tag_img:
            contents.append(price_tag_img)
        response = model.generate_content(contents)
        raw = response.text.strip()
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except Exception as e:
        st.warning(f"Gemini error: {e}")
    return {}

# ------------------- دوال Excel -------------------
def create_excel(inventory):
    if not inventory:
        return None
    df = pd.DataFrame(inventory)
    cols = ["SKU", "Product Name", "Brand", "Category", "Description", "Barcode", "Price", "Quantity", "Date Added"]
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df = df[cols]
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Inventory')
    return output.getvalue()

# ------------------- إعادة ضبط -------------------
def reset_for_new_product():
    st.session_state.step = 0
    st.session_state.temp_images = [None, None, None]
    st.session_state.quantity = 1
    st.session_state.processed = False
    st.session_state.barcode = None
    st.session_state.ai_result = None
    st.session_state.camera_counter = st.session_state.get('camera_counter', 0) + 1

def reset_full_session():
    st.session_state.inventory = []
    reset_for_new_product()

# ------------------- واجهة المستخدم -------------------
st.set_page_config(page_title="AI Inventory Scanner", page_icon="📷", layout="centered")
st.title("📷 AI Inventory Scanner - الإصدار السريع")
st.markdown("التقط 3 صور: **المنتج** ← **الباركود** ← **ملصق السعر**، ثم أدخل الكمية.")

# تهيئة المتغيرات
if 'inventory' not in st.session_state:
    st.session_state.inventory = []
if 'step' not in st.session_state:
    st.session_state.step = 0
if 'temp_images' not in st.session_state:
    st.session_state.temp_images = [None, None, None]
if 'quantity' not in st.session_state:
    st.session_state.quantity = 1
if 'processed' not in st.session_state:
    st.session_state.processed = False
if 'barcode' not in st.session_state:
    st.session_state.barcode = None
if 'ai_result' not in st.session_state:
    st.session_state.ai_result = None
if 'camera_counter' not in st.session_state:
    st.session_state.camera_counter = 0

# أزرار عليا
col1, col2, col3 = st.columns([2,1,1])
with col2:
    if st.session_state.inventory:
        excel = create_excel(st.session_state.inventory)
        if excel:
            st.download_button("📥 Excel", data=excel, file_name=f"inventory_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")
    else:
        st.button("📥 Excel", disabled=True)
with col3:
    if st.button("🗑️ مسح الكل"):
        reset_full_session()
        st.rerun()
st.divider()

# عرض المخزون الحالي
if st.session_state.inventory:
    st.info(f"✅ تم إضافة {len(st.session_state.inventory)} منتج")
    st.dataframe(pd.DataFrame(st.session_state.inventory), use_container_width=True)
    st.divider()

counter = st.session_state.camera_counter

# الخطوة 0: المنتج
if st.session_state.step == 0:
    st.subheader("📦 صورة المنتج")
    img = st.camera_input("التقط الصورة", key=f"prod_{counter}")
    if img:
        st.session_state.temp_images[0] = Image.open(img)
        st.success("✅ تم الالتقاط")
        if st.button("➡️ التالي"):
            st.session_state.step = 1
            st.rerun()

# الخطوة 1: الباركود
elif st.session_state.step == 1:
    st.subheader("📊 صورة الباركود")
    img = st.camera_input("التقط الباركود", key=f"bar_{counter}")
    if img:
        pil = Image.open(img)
        st.session_state.temp_images[1] = pil
        with st.spinner("قراءة الباركود..."):
            barcode = scan_barcode(pil)
        if barcode:
            st.success(f"✅ الباركود: {barcode}")
            st.session_state.barcode = barcode
        else:
            st.warning("⚠️ لم يُقرأ الباركود. يمكنك إدخاله يدوياً:")
            manual = st.text_input("أدخل الباركود (اختياري)")
            if manual:
                st.session_state.barcode = manual.strip()
        if st.button("➡️ التالي"):
            st.session_state.step = 2
            st.rerun()

# الخطوة 2: السعر (اختياري)
elif st.session_state.step == 2:
    st.subheader("🏷️ صورة السعر (اختياري)")
    img = st.camera_input("التقط السعر", key=f"price_{counter}")
    if img:
        st.session_state.temp_images[2] = Image.open(img)
        st.success("✅ تم")
    if st.button("➡️ التالي"):
        st.session_state.step = 3
        st.rerun()

# الخطوة 3: الكمية
elif st.session_state.step == 3:
    st.subheader("🔢 الكمية")
    qty = st.number_input("الكمية:", min_value=0, value=1, step=1)
    if st.button("✅ تحليل وإضافة"):
        st.session_state.quantity = qty
        st.session_state.step = 4
        st.rerun()

# الخطوة 4: التحليل
elif st.session_state.step == 4 and not st.session_state.processed:
    with st.spinner("جاري تحليل Gemini..."):
        ai = analyze_with_gemini(st.session_state.temp_images[0], st.session_state.temp_images[2])
    st.session_state.ai_result = ai
    st.session_state.processed = True

    # إنشاء المنتج الجديد
    new_item = {
        "SKU": ai.get('sku', 'ERR'),
        "Product Name": ai.get('product_name', 'غير معروف'),
        "Brand": ai.get('brand', 'غير معروف'),
        "Category": ai.get('category', 'غير معروف'),
        "Description": ai.get('description', ''),
        "Barcode": st.session_state.barcode if st.session_state.barcode else "لم يقرأ",
        "Price": ai.get('price', ''),
        "Quantity": st.session_state.quantity,
        "Date Added": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    st.session_state.inventory.append(new_item)
    st.success(f"✅ تم إضافة {new_item['Product Name']}")
    st.rerun()  # لإعادة العرض مع زر "منتج آخر"

elif st.session_state.step == 4 and st.session_state.processed:
    st.subheader("✅ منتج مضاف بنجاح")
    if st.button("➕ منتج آخر"):
        reset_for_new_product()
        st.rerun()
    st.dataframe(pd.DataFrame(st.session_state.inventory), use_container_width=True)
