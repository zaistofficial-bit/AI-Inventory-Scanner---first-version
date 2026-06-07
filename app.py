# app.py - النسخة النهائية المستقرة مع قراءة باركود قوية وإعادة محاولة
import streamlit as st
import pandas as pd
from io import BytesIO
from PIL import Image, ImageEnhance, ImageFilter
import google.generativeai as genai
import json
import re
from datetime import datetime
import cv2
import numpy as np

# ------------------- الإعدادات -------------------
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=GEMINI_API_KEY)

# ------------------- دوال معالجة الباركود -------------------
def preprocess_barcode_image(pil_image):
    """تحسين الصورة لزيادة فرصة قراءة الباركود"""
    # تحويل إلى تدرج رمادي
    gray = pil_image.convert('L')
    # تحسين التباين
    enhancer = ImageEnhance.Contrast(gray)
    enhanced = enhancer.enhance(2.5)
    # تكبير الصورة
    scaled = enhanced.resize((int(enhanced.width * 1.5), int(enhanced.height * 1.5)), Image.Resampling.LANCZOS)
    return scaled

def scan_barcode_with_cv2(pil_image):
    """قراءة الباركود باستخدام OpenCV"""
    try:
        img = np.array(pil_image.convert('RGB'))
        img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        detector = cv2.barcode_BarcodeDetector()
        ok, decoded_info, _ = detector.detectAndDecode(img_bgr)
        if ok and decoded_info:
            return decoded_info.strip()
    except Exception:
        pass
    return None

def scan_barcode_with_pyzbar(pil_image):
    """قراءة الباركود باستخدام pyzbar (بديل أخف)"""
    try:
        from pyzbar import pyzbar
        decoded = pyzbar.decode(pil_image)
        if decoded:
            return decoded[0].data.decode('utf-8').strip()
    except Exception:
        pass
    return None

def scan_barcode_advanced(pil_image, method='auto'):
    """وظيفة رئيسية لقراءة الباركود مع عدة محاولات"""
    if pil_image is None:
        return None
    # تحسين الصورة أولاً
    enhanced = preprocess_barcode_image(pil_image)
    if method == 'cv2':
        return scan_barcode_with_cv2(enhanced)
    elif method == 'pyzbar':
        return scan_barcode_with_pyzbar(enhanced)
    else:
        # auto: جرب كل الطرق
        barcode = scan_barcode_with_cv2(enhanced)
        if barcode:
            return barcode
        barcode = scan_barcode_with_pyzbar(enhanced)
        if barcode:
            return barcode
        # تجربة على الصورة الأصلية بدون تحسين
        barcode = scan_barcode_with_pyzbar(pil_image)
        if barcode:
            return barcode
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
        "price_from_label": "السعر من ملصق السعر (إن وجد)"
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
        st.warning(f"⚠️ خطأ Gemini: {str(e)[:100]}")
    return {}

# ------------------- دوال Excel -------------------
def create_excel(inventory):
    if not inventory:
        return None
    df = pd.DataFrame(inventory)
    cols = ["SKU", "Product Name", "Brand", "Category", "Description",
            "Barcode", "Price", "Quantity", "Confidence", "Date Added"]
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df = df[cols]
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Inventory')
    return output.getvalue()

# ------------------- دوال إدارة الجلسة -------------------
def reset_for_new_product():
    st.session_state.step = 0
    st.session_state.temp_images = [None, None, None]
    st.session_state.quantity = 1
    st.session_state.processed = False
    st.session_state.current_product_added = False
    st.session_state.barcode_failed = False
    st.session_state.barcode_retry_method = None
    st.session_state.barcode_image = None
    st.session_state.manual_barcode = None
    st.session_state.camera_counter = st.session_state.get('camera_counter', 0) + 1

def reset_full_session():
    st.session_state.inventory = []
    reset_for_new_product()

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
if 'current_product_added' not in st.session_state:
    st.session_state.current_product_added = False
if 'barcode_failed' not in st.session_state:
    st.session_state.barcode_failed = False
if 'barcode_retry_method' not in st.session_state:
    st.session_state.barcode_retry_method = None
if 'barcode_image' not in st.session_state:
    st.session_state.barcode_image = None
if 'manual_barcode' not in st.session_state:
    st.session_state.manual_barcode = None
if 'camera_counter' not in st.session_state:
    st.session_state.camera_counter = 0

# أزرار التحكم العلوية
col1, col2, col3 = st.columns([2, 1, 1])
with col2:
    if st.session_state.inventory:
        excel_data = create_excel(st.session_state.inventory)
        if excel_data:
            st.download_button("📥 تحميل Excel", data=excel_data,
                               file_name=f"inventory_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                               key="excel_top")
    else:
        st.button("📥 Excel", disabled=True)
with col3:
    if st.button("🗑️ مسح الجلسة بالكامل"):
        reset_full_session()
        st.rerun()
st.divider()

# عرض المنتجات المضافة حالياً
if st.session_state.inventory:
    st.info(f"📦 تم إضافة {len(st.session_state.inventory)} منتج حتى الآن")
    st.dataframe(pd.DataFrame(st.session_state.inventory), use_container_width=True)
    st.divider()

# ------------------- الخطوات -------------------
counter = st.session_state.camera_counter

# الخطوة 0: صورة المنتج
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

# الخطوة 1: صورة الباركود مع إعادة محاولة
elif st.session_state.step == 1:
    st.subheader("📊 صورة الباركود (قرّب الكاميرا)")
    st.caption("تأكد من الإضاءة الجيدة وتقريب الكاميرا من الباركود")

    if st.session_state.barcode_failed and st.session_state.barcode_image:
        st.error("❌ لم يتم قراءة الباركود في المحاولة السابقة.")
        st.info("🔍 نصائح: إضاءة جيدة، تقريب الكاميرا، وضوح الباركود.")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            if st.button("🔄 إعادة المحاولة (طريقة أخرى)"):
                barcode = scan_barcode_advanced(st.session_state.barcode_image, method='pyzbar')
                if barcode:
                    st.success(f"✅ تم القراءة: {barcode}")
                    st.session_state.temp_images[1] = st.session_state.barcode_image
                    st.session_state.barcode_failed = False
                    st.session_state.step = 2
                    st.rerun()
                else:
                    st.error("فشلت المحاولة مرة أخرى. أدخل الباركود يدوياً.")
                    manual = st.text_input("أدخل الباركود (أو اتركه فارغاً)")
                    if st.button("✅ قبول"):
                        st.session_state.manual_barcode = manual.strip()
                        st.session_state.temp_images[1] = st.session_state.barcode_image
                        st.session_state.barcode_failed = False
                        st.session_state.step = 2
                        st.rerun()
        with col_b:
            if st.button("📸 إعادة التقاط الصورة"):
                st.session_state.barcode_failed = False
                st.session_state.barcode_image = None
                st.rerun()
        with col_c:
            if st.button("⏩ تخطي الباركود"):
                st.session_state.temp_images[1] = None
                st.session_state.barcode_failed = False
                st.session_state.step = 2
                st.rerun()
    else:
        img = st.camera_input("التقط الصورة", key=f"cam_barcode_{counter}")
        if img:
            pil_img = Image.open(img)
            pil_img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            st.session_state.barcode_image = pil_img
            with st.spinner("جاري قراءة الباركود..."):
                barcode = scan_barcode_advanced(pil_img, method='auto')
            if barcode:
                st.success(f"✅ تم القراءة: {barcode}")
                st.session_state.temp_images[1] = pil_img
                st.session_state.barcode_failed = False
                if st.button("➡️ التالي"):
                    st.session_state.step = 2
                    st.rerun()
            else:
                st.error("❌ لم يتم التعرف على الباركود. اضغط 'إعادة المحاولة' لاستخدام طريقة أخرى.")
                st.session_state.barcode_failed = True
                st.rerun()

# الخطوة 2: صورة السعر (اختياري)
elif st.session_state.step == 2:
    st.subheader("🏷️ صورة ملصق السعر (اختياري)")
    img = st.camera_input("التقط الصورة (اختياري)", key=f"cam_price_{counter}")
    if img:
        pil_img = Image.open(img)
        pil_img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        st.session_state.temp_images[2] = pil_img
        st.success("✅ تم الالتقاط!")
    if st.button("➡️ التالي"):
        st.session_state.step = 3
        st.rerun()

# الخطوة 3: إدخال الكمية
elif st.session_state.step == 3:
    st.subheader("🔢 أدخل كمية المنتج")
    quantity = st.number_input("الكمية المتوفرة:", min_value=0, step=1, value=st.session_state.quantity)
    if st.button("✅ تأكيد وتحليل المنتج"):
        st.session_state.quantity = quantity
        st.session_state.step = 4
        st.rerun()

# الخطوة 4: التحليل والإضافة
elif st.session_state.step == 4 and not st.session_state.current_product_added:
    st.subheader("🔍 جاري التحليل...")
    prod_img = st.session_state.temp_images[0]
    bar_img = st.session_state.temp_images[1]
    price_img = st.session_state.temp_images[2]

    # استرجاع الباركود (يدوي أو من الصورة)
    barcode = None
    if st.session_state.manual_barcode:
        barcode = st.session_state.manual_barcode
        st.session_state.manual_barcode = None
    elif bar_img:
        barcode = scan_barcode_advanced(bar_img)

    with st.spinner("تحليل المنتج بالذكاء الاصطناعي..."):
        ai_result = analyze_with_gemini(prod_img, price_img) if prod_img else {}

    # عرض النتائج
    col_left, col_right = st.columns(2)
    with col_left:
        if prod_img:
            st.image(prod_img, caption="المنتج", width=150)
        if barcode:
            st.success(f"✅ الباركود: {barcode}")
        else:
            st.warning("⚠️ لم يتم قراءة الباركود. يمكنك الاستمرار بدون باركود.")
    with col_right:
        if ai_result:
            st.json(ai_result)
        else:
            st.error("❌ فشل تحليل Gemini. حاول مرة أخرى.")

    # منع التكرار
    sku = ai_result.get('sku', 'ERR') if ai_result else 'ERR'
    duplicate = False
    for item in st.session_state.inventory:
        if barcode and item.get('Barcode') == barcode and barcode != "لم يقرأ":
            duplicate = True
            st.warning(f"⚠️ الباركود {barcode} موجود مسبقاً للمنتج '{item['Product Name']}'. لن تتم الإضافة.")
            break
        if sku != 'ERR' and item.get('SKU') == sku:
            st.warning(f"⚠️ SKU {sku} موجود مسبقاً. تم تعديله تلقائياً.")
            sku = f"{sku}_{len(st.session_state.inventory)+1}"
            break

    if not duplicate:
        new_item = {
            "SKU": sku,
            "Product Name": ai_result.get('product_name', 'غير معروف') if ai_result else 'غير معروف',
            "Brand": ai_result.get('brand', 'غير معروف') if ai_result else 'غير معروف',
            "Category": ai_result.get('category', 'غير معروف') if ai_result else 'غير معروف',
            "Description": ai_result.get('description', '') if ai_result else '',
            "Barcode": barcode if barcode else "لم يقرأ",
            "Price": ai_result.get('price_from_label', '') if ai_result else '',
            "Quantity": st.session_state.quantity,
            "Confidence": "85%",
            "Date Added": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        st.session_state.inventory.append(new_item)
        st.session_state.current_product_added = True
        st.success(f"✅ تمت إضافة المنتج '{new_item['Product Name']}' بنجاح!")
    else:
        st.session_state.current_product_added = True

    if st.button("➕ منتج آخر"):
        reset_for_new_product()
        st.rerun()

    if st.session_state.inventory:
        st.subheader("📋 المخزون الحالي")
        st.dataframe(pd.DataFrame(st.session_state.inventory), use_container_width=True)

elif st.session_state.step == 4 and st.session_state.current_product_added:
    st.success("✅ تمت إضافة المنتج بنجاح")
    if st.button("➕ منتج آخر"):
        reset_for_new_product()
        st.rerun()
    if st.session_state.inventory:
        st.dataframe(pd.DataFrame(st.session_state.inventory), use_container_width=True)
