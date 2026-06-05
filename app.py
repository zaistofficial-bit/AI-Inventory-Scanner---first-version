# app.py
import streamlit as st
import pandas as pd
from io import BytesIO
from PIL import Image
from pyrxing import read_barcode  # الطريقة الصحيحة
import easyocr
import google.generativeai as genai
import numpy as np
import json
import re

# ------------------- الإعدادات -------------------
# GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"  <-- يمكنك حذف هذا السطر أو تعليقه
import streamlit as st

# اقرأ المفتاح من مكان آمن
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

genai.configure(api_key=GEMINI_API_KEY)

@st.cache_resource
def load_ocr_reader():
    return easyocr.Reader(['ar', 'en'], gpu=False)

# ------------------- دوال المعالجة -------------------
def scan_barcode(image):
    """تقرأ الباركود من الصورة باستخدام pyrxing"""
    try:
        result = read_barcode(image)
        if result is not None and result.text:
            return result.text.strip()
    except Exception as e:
        st.warning(f"فشل قراءة الباركود: {e}")
    return None

def extract_text_from_label(image, reader):
    """تستخرج النصوص من الملصق"""
    try:
        # تصغير حجم الصورة لتسريع OCR
        img_small = image.copy()
        img_small.thumbnail((800, 800), Image.Resampling.LANCZOS)
        result = reader.readtext(np.array(img_small))
        text = ' '.join([item[1] for item in result])
        return text.strip() if text else None
    except Exception as e:
        st.warning(f"فشل OCR: {e}")
        return None

def preprocess_image_for_gemini(image):
    """تجهيز الصورة لإرسالها إلى Gemini"""
    img = image.copy()
    # تصغير الحجم لتسريع الرفع
    img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
    return img

def analyze_product_with_gemini(image):
    """تحليل المنتج باستخدام Gemini API"""
    prompt = """
    أنت خبير في تصنيف المنتجات الإلكترونية فقط (كمبيوترات، لابتوبات، طابعات، شاشات، إكسسوارات موبايل، سماعات، كاميرات، كابلات، شواحن).
    إذا كان المنتج ليس من هذه الفئات، أعد الفئة كـ "غير إلكتروني".
    أجب فقط بصيغة JSON صالحة بدون أي نص إضافي:
    {
        "product_name": "اسم المنتج بالانجليزي",
        "brand": "اسم العلامة التجارية",
        "category": "Laptop / Printer / Accessory / Mobile Accessory / Other",
        "description": "وصف قصير جداً (أقل من 12 كلمة)",
        "sku": "مثل LAP-001 أو ACC-002"
    }
    """
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content([prompt, image])
        raw = response.text.strip()
        # استخراج JSON من النص
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            return result
        else:
            st.error("لم يتم العثور على JSON في رد Gemini")
            return {}
    except Exception as e:
        st.error(f"خطأ في Gemini API: {e}")
        st.info("تأكد من صحة مفتاح API ومن تفعيل billing (ولو بالمجان) في Google Cloud Console")
        return {}

def create_excel(inventory):
    """إنشاء ملف Excel من قائمة المنتجات"""
    if not inventory:
        return None
    df = pd.DataFrame(inventory)
    cols = ["SKU", "Product Name", "Brand", "Category", "Description", "Barcode", "Model (OCR)", "Confidence Score"]
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df = df[cols]
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Inventory')
    return output.getvalue()

# ------------------- واجهة المستخدم -------------------
st.set_page_config(page_title="AI Inventory Scanner - Electronic Store", page_icon="📷", layout="centered")
st.title("📷 AI Inventory Scanner")
st.markdown("**للمنتجات الإلكترونية فقط** (كمبيوترات، إكسسوارات، طابعات، شاشات)")

# تهيئة حالة الجلسة
if 'inventory' not in st.session_state:
    st.session_state.inventory = []
if 'step' not in st.session_state:
    st.session_state.step = 0  # 0=منتج, 1=باركود, 2=ملصق
if 'temp_images' not in st.session_state:
    st.session_state.temp_images = [None, None, None]
if 'ocr_reader' not in st.session_state:
    with st.spinner("جاري تحميل OCR (أول مرة فقط قد يستغرق دقيقة)..."):
        st.session_state.ocr_reader = load_ocr_reader()
        st.success("OCR جاهز!")

# زر تحميل Excel في الأعلى (إذا وجد منتجات)
col_top1, col_top2 = st.columns([3, 1])
with col_top2:
    if st.session_state.inventory:
        excel_data = create_excel(st.session_state.inventory)
        if excel_data:
            st.download_button("📥 تحميل Excel", data=excel_data, file_name="inventory.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.button("📥 Excel", disabled=True)

st.divider()

# ------------------- خطوات التقاط الصور -------------------
if st.session_state.step < 3:
    step_names = ["1️⃣ صورة المنتج", "2️⃣ صورة الباركود", "3️⃣ صورة الملصق"]
    st.subheader(step_names[st.session_state.step])
    
    # عرض الصورة الملتقطة سابقاً لهذه الخطوة إن وجدت
    if st.session_state.temp_images[st.session_state.step] is not None:
        st.image(st.session_state.temp_images[st.session_state.step], caption="الصورة الحالية", width=200)
        if st.button("📸 إعادة التصوير"):
            st.session_state.temp_images[st.session_state.step] = None
            st.rerun()
        if st.button("➡️ التالي (استخدام الصورة الحالية)"):
            st.session_state.step += 1
            st.rerun()
    else:
        # كاميرا جديدة
        img = st.camera_input("التقط الصورة الآن")
        if img is not None:
            pil_img = Image.open(img)
            # معالجة مسبقة للصورة
            pil_img = preprocess_image_for_gemini(pil_img)
            st.session_state.temp_images[st.session_state.step] = pil_img
            st.success("✅ تم الالتقاط! اضغط 'التالي'")
            if st.button("➡️ التالي"):
                st.session_state.step += 1
                st.rerun()

# ------------------- بعد التقاط جميع الصور -------------------
elif st.session_state.step == 3:
    st.subheader("🔍 جاري تحليل المنتج...")
    prod_img = st.session_state.temp_images[0]
    bar_img = st.session_state.temp_images[1]
    lab_img = st.session_state.temp_images[2]
    
    with st.spinner("معالجة الباركود والملصق والذكاء الاصطناعي (قد يستغرق 5-10 ثوان)..."):
        barcode = scan_barcode(bar_img) if bar_img else None
        label_text = extract_text_from_label(lab_img, st.session_state.ocr_reader) if lab_img else None
        ai_result = analyze_product_with_gemini(prod_img)
    
    # عرض النتائج
    st.success("تم التحليل")
    col1, col2 = st.columns(2)
    with col1:
        st.image(prod_img, caption="المنتج", width=150)
    with col2:
        if ai_result:
            st.json(ai_result)
        else:
            st.warning("فشل تحليل Gemini. تحقق من مفتاح API أو اتصال الإنترنت.")
    
    # بناء سجل المنتج
    new_item = {
        "SKU": ai_result.get('sku', 'ERR-SKU') if ai_result else 'ERR-SKU',
        "Product Name": ai_result.get('product_name', 'غير معروف') if ai_result else 'غير معروف',
        "Brand": ai_result.get('brand', 'غير معروف') if ai_result else 'غير معروف',
        "Category": ai_result.get('category', 'غير معروف') if ai_result else 'غير معروف',
        "Description": ai_result.get('description', '') if ai_result else '',
        "Barcode": barcode if barcode else "لم يقرأ",
        "Model (OCR)": label_text[:100] if label_text else "لا يوجد",
        "Confidence Score": "80%" if barcode or label_text else "50%"
    }
    st.session_state.inventory.append(new_item)
    
    # زرين
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("➕ منتج آخر"):
            st.session_state.step = 0
            st.session_state.temp_images = [None, None, None]
            st.rerun()
    with col_b:
        if st.session_state.inventory:
            excel_data = create_excel(st.session_state.inventory)
            if excel_data:
                st.download_button("📥 إنهاء وتحميل Excel", data=excel_data, file_name="inventory.xlsx")
    
    st.divider()
    st.subheader(f"📋 المنتجات المضافة ({len(st.session_state.inventory)})")
    st.dataframe(pd.DataFrame(st.session_state.inventory))

# ------------------- عرض ملخص أثناء العمل -------------------
if st.session_state.step < 3 and st.session_state.inventory:
    st.divider()
    st.info(f"✅ تم إضافة {len(st.session_state.inventory)} منتج حتى الآن")
