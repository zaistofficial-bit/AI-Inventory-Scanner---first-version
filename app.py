# app.py - النسخة المعدلة بالكامل
import streamlit as st
import pandas as pd
from io import BytesIO
from PIL import Image, ImageEnhance
import zxingcpp
import google.generativeai as genai
import json
import re

# ------------------- الإعدادات -------------------
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=GEMINI_API_KEY)

# ------------------- دوال المعالجة -------------------
def scan_barcode_advanced(image):
    try:
        gray = image.convert('L')
        enhancer = ImageEnhance.Contrast(gray)
        enhanced = enhancer.enhance(2.5)
        enlarged = enhanced.resize((int(enhanced.width*1.5), int(enhanced.height*1.5)), Image.Resampling.LANCZOS)
        results = zxingcpp.read_barcodes(enlarged)
        if results:
            return results[0].text.strip()
        results = zxingcpp.read_barcodes(image)
        if results:
            return results[0].text.strip()
    except:
        pass
    return None

def analyze_with_gemini(product_img, price_tag_img):
    prompt = """
    أنت خبير في المنتجات الإلكترونية. أخرج JSON فقط:
    {
        "product_name": "اسم المنتج",
        "brand": "العلامة التجارية",
        "category": "Laptop/Printer/Accessory/Mobile Accessory",
        "description": "وصف قصير (أقل من 10 كلمات)",
        "sku": "SKU مقترح",
        "price_from_label": "السعر"
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
        st.warning(f"⚠️ خطأ في Gemini: {str(e)[:100]}")
        pass
    return {}

def create_excel(inventory):
    if not inventory:
        return None
    df = pd.DataFrame(inventory)
    cols = ["SKU", "Product Name", "Brand", "Category", "Description", "Barcode", "Price", "Quantity", "Confidence"]
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df = df[cols]
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Inventory')
    return output.getvalue()

def reset_app():
    """إعادة ضبط كاملة مع زيادة عداد الكاميرا"""
    st.session_state.step = 0
    st.session_state.temp_images = [None, None, None]
    st.session_state.quantity = 1
    st.session_state.processed = False
    st.session_state.inventory_updated = False
    # زيادة العداد لإنشاء مفاتيح كاميرا جديدة
    if 'camera_counter' not in st.session_state:
        st.session_state.camera_counter = 0
    else:
        st.session_state.camera_counter += 1

# ------------------- واجهة المستخدم -------------------
st.set_page_config(page_title="AI Inventory Scanner", page_icon="📷", layout="centered")
st.title("📷 AI Inventory Scanner - الإصدار الاحترافي")
st.markdown("التقط 3 صور: **المنتج** ← **الباركود** ← **ملصق السعر**، ثم أدخل الكمية.")

# تهيئة حالة الجلسة
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
if 'inventory_updated' not in st.session_state:
    st.session_state.inventory_updated = False
if 'camera_counter' not in st.session_state:
    st.session_state.camera_counter = 0

# أزرار إضافية (تحميل Excel + مسح الجلسة)
col1, col2, col3 = st.columns([2, 1, 1])
with col2:
    if st.session_state.inventory:
        excel_data = create_excel(st.session_state.inventory)
        if excel_data:
            st.download_button("📥 تحميل Excel", data=excel_data, file_name="inventory.xlsx", key="excel_top")
    else:
        st.button("📥 Excel", disabled=True)
with col3:
    if st.button("🗑️ مسح الجلسة وبدء جديد"):
        st.session_state.inventory = []
        reset_app()
        st.rerun()
st.divider()

# ------------------- عرض المنتجات المضافة أثناء العمل -------------------
if st.session_state.inventory and st.session_state.step < 4:
    st.info(f"✅ تم إضافة {len(st.session_state.inventory)} منتج حتى الآن")
    # عرض جدول مصغر للمنتجات المضافة
    st.dataframe(pd.DataFrame(st.session_state.inventory), use_container_width=True)
    st.divider()

# ------------------- الخطوات مع مفاتيح كاميرا ديناميكية -------------------
counter = st.session_state.camera_counter  # لضمان اتساق المفاتيح داخل الجلسة

if st.session_state.step == 0:
    st.subheader("📦 صورة المنتج")
    img = st.camera_input("التقط الصورة", key=f"cam_product_{counter}")
    if img:
        pil_img = Image.open(img)
        pil_img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        st.session_state.temp_images[0] = pil_img
        st.success("✅ تم الالتقاط!")
        if st.button("➡️ التالي"):
            st.session_state.step = 1
            st.rerun()

elif st.session_state.step == 1:
    st.subheader("📊 صورة الباركود (قرّب الكاميرا)")
    img = st.camera_input("التقط الصورة", key=f"cam_barcode_{counter}")
    if img:
        pil_img = Image.open(img)
        pil_img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        st.session_state.temp_images[1] = pil_img
        st.success("✅ تم الالتقاط!")
        if st.button("➡️ التالي"):
            st.session_state.step = 2
            st.rerun()

elif st.session_state.step == 2:
    st.subheader("🏷️ صورة ملصق السعر")
    img = st.camera_input("التقط الصورة", key=f"cam_price_{counter}")
    if img:
        pil_img = Image.open(img)
        pil_img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        st.session_state.temp_images[2] = pil_img
        st.success("✅ تم الالتقاط!")
        if st.button("➡️ التالي"):
            st.session_state.step = 3
            st.rerun()

elif st.session_state.step == 3:
    st.subheader("🔢 أدخل كمية المنتج")
    quantity = st.number_input("الكمية المتوفرة:", min_value=0, step=1, value=st.session_state.quantity, key="quantity_input")
    if st.button("✅ تأكيد وتحليل المنتج"):
        st.session_state.quantity = quantity
        st.session_state.step = 4
        st.rerun()

elif st.session_state.step == 4 and not st.session_state.processed:
    st.subheader("🔍 جاري التحليل...")
    prod_img = st.session_state.temp_images[0]
    bar_img = st.session_state.temp_images[1]
    price_img = st.session_state.temp_images[2]
    
    with st.spinner("قراءة الباركود والذكاء الاصطناعي..."):
        barcode = scan_barcode_advanced(bar_img) if bar_img else None
        ai_result = analyze_with_gemini(prod_img, price_img)
    
    col_left, col_right = st.columns(2)
    with col_left:
        if prod_img:
            st.image(prod_img, caption="المنتج", width=150)
    with col_right:
        if ai_result:
            st.json(ai_result)
    
    if barcode:
        st.success(f"✅ الباركود: {barcode}")
    else:
        st.warning("⚠️ الباركود لم يُقرأ. تأكد من تقريب الكاميرا وإضاءة جيدة.")
    
    new_item = {
        "SKU": ai_result.get('sku', 'ERR') if ai_result else 'ERR',
        "Product Name": ai_result.get('product_name', 'غير معروف') if ai_result else 'غير معروف',
        "Brand": ai_result.get('brand', 'غير معروف') if ai_result else 'غير معروف',
        "Category": ai_result.get('category', 'غير معروف') if ai_result else 'غير معروف',
        "Description": ai_result.get('description', '') if ai_result else '',
        "Barcode": barcode if barcode else "لم يقرأ",
        "Price": ai_result.get('price_from_label', '') if ai_result else '',
        "Quantity": st.session_state.quantity,
        "Confidence": "85%"
    }
    st.session_state.inventory.append(new_item)
    st.session_state.processed = True
    st.session_state.inventory_updated = True
    
    # عرض المنتجات المضافة
    st.subheader(f"📋 تم إضافة {len(st.session_state.inventory)} منتج")
    st.dataframe(pd.DataFrame(st.session_state.inventory), use_container_width=True)
    
    # زر منتج آخر
    if st.button("➕ منتج آخر"):
        reset_app()
        st.rerun()

# ------------------- عرض النتائج إذا انتهى التحليل -------------------
if st.session_state.step == 4 and st.session_state.processed and not st.session_state.inventory_updated:
    st.subheader(f"📋 تم إضافة {len(st.session_state.inventory)} منتج")
    st.dataframe(pd.DataFrame(st.session_state.inventory), use_container_width=True)
    if st.button("➕ منتج آخر"):
        reset_app()
        st.rerun()
