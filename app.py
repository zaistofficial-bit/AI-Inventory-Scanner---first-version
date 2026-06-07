# app.py - النسخة السلسة مع جميع الميزات الجديدة
import streamlit as st
import pandas as pd
from io import BytesIO
from PIL import Image, ImageEnhance
from pyrxing import read_barcode
import google.generativeai as genai
import json
import re

# ------------------- الإعدادات -------------------
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=GEMINI_API_KEY)

# ------------------- دوال قوية -------------------
def scan_barcode_advanced(image):
    """قراءة باركود حتى لو كان صغيراً جداً"""
    try:
        # تحسين الصورة للقراءة
        gray = image.convert('L')
        enhancer = ImageEnhance.Contrast(gray)
        enhanced = enhancer.enhance(2.5)
        # تكبير الصورة
        enlarged = enhanced.resize((int(enhanced.width*1.5), int(enhanced.height*1.5)), Image.Resampling.LANCZOS)
        result = read_barcode(enlarged)
        if result and result.text:
            return result.text.strip()
        result = read_barcode(image)
        if result and result.text:
            return result.text.strip()
    except:
        pass
    return None

def analyze_with_gemini(product_img, price_tag_img):
    """Gemini يحلل المنتج ويقرأ ملصق السعر إن وجد"""
    prompt = """
    أنت خبير في المنتجات الإلكترونية. أخرج JSON فقط:
    {
        "product_name": "اسم المنتج",
        "brand": "العلامة التجارية",
        "category": "Laptop/Printer/Accessory/Mobile Accessory",
        "description": "وصف قصير (أقل من 10 كلمات)",
        "sku": "SKU مقترح مثل LAP-001",
        "price_from_label": "السعر المستخرج من الصورة الثانية (إن وجد، وإلا '')"
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
        st.error(f"Gemini error: {e}")
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

# ------------------- واجهة المستخدم السلسة -------------------
st.set_page_config(page_title="AI Inventory Scanner", page_icon="📷", layout="centered")
st.title("📷 AI Inventory Scanner - الإصدار الاحترافي")
st.markdown("التقط 3 صور: **المنتج** ← **الباركود** ← **ملصق السعر**، ثم أدخل الكمية.")

# حالة الجلسة
if 'inventory' not in st.session_state:
    st.session_state.inventory = []
if 'step' not in st.session_state:
    st.session_state.step = 0  # 0:منتج, 1:باركود, 2:سعر, 3:كمية
if 'temp_images' not in st.session_state:
    st.session_state.temp_images = [None, None, None]
if 'quantity' not in st.session_state:
    st.session_state.quantity = 1

# زر Excel
if st.session_state.inventory:
    excel_data = create_excel(st.session_state.inventory)
    if excel_data:
        st.download_button("📥 تحميل Excel", data=excel_data, file_name="inventory.xlsx")
st.divider()

# ------------------- الخطوات السلسة -------------------
if st.session_state.step < 3:
    step_names = ["📦 صورة المنتج", "📊 صورة الباركود (قرّب الكاميرا)", "🏷️ صورة ملصق السعر"]
    st.subheader(step_names[st.session_state.step])
    
    # كاميرا مباشرة (بدون أزرار إضافية)
    img = st.camera_input("التقط الصورة", key=f"cam_{st.session_state.step}")
    
    if img is not None:
        pil_img = Image.open(img)
        pil_img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        st.session_state.temp_images[st.session_state.step] = pil_img
        st.success("✅ تم الالتقاط! اضغط 'التالي'")
        
        # زر التالي مباشرة (هذا كان يعمل بشكل سلس في الأصل)
        if st.button("➡️ التالي"):
            st.session_state.step += 1
            st.rerun()

# ------------------- إدخال الكمية -------------------
elif st.session_state.step == 3:
    st.subheader("🔢 أدخل كمية المنتج")
    quantity = st.number_input("الكمية المتوفرة:", min_value=0, step=1, value=1)
    if st.button("✅ تأكيد وتحليل المنتج"):
        st.session_state.quantity = quantity
        st.session_state.step = 4
        st.rerun()

# ------------------- المعالجة -------------------
elif st.session_state.step == 4:
    st.subheader("🔍 جاري التحليل...")
    prod_img = st.session_state.temp_images[0]
    bar_img = st.session_state.temp_images[1]
    price_img = st.session_state.temp_images[2]
    
    with st.spinner("قراءة الباركود والذكاء الاصطناعي..."):
        barcode = scan_barcode_advanced(bar_img) if bar_img else None
        ai_result = analyze_with_gemini(prod_img, price_img)
    
    # عرض النتائج
    col1, col2 = st.columns(2)
    with col1:
        st.image(prod_img, width=150)
    with col2:
        if ai_result:
            st.json(ai_result)
    
    if not barcode:
        st.warning("⚠️ الباركود لم يُقرأ. تأكد من تقريب الكاميرا وإضاءة جيدة.")
    else:
        st.success(f"✅ الباركود: {barcode}")
    
    # حفظ المنتج
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
    
    # زر منتج آخر
    if st.button("➕ منتج آخر"):
        st.session_state.step = 0
        st.session_state.temp_images = [None, None, None]
        st.session_state.quantity = 1
        st.rerun()
    
    st.divider()
    st.subheader(f"📋 تم إضافة {len(st.session_state.inventory)} منتج")
    st.dataframe(pd.DataFrame(st.session_state.inventory))

# ------------------- عرض المنتجات أثناء العمل -------------------
if 0 < st.session_state.step < 4 and st.session_state.inventory:
    st.info(f"✅ تم إضافة {len(st.session_state.inventory)} منتج حتى الآن")
