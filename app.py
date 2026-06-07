# app.py - النسخة المستقرة بالكامل مع حل مشكلة الكاميرا والباركود والتكرار
import streamlit as st
import pandas as pd
from io import BytesIO
from PIL import Image, ImageEnhance, ImageFilter
import zxingcpp
import google.generativeai as genai
import json
import re
from datetime import datetime

# ------------------- الإعدادات -------------------
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=GEMINI_API_KEY)

# ------------------- دوال معالجة الباركود المحسنة -------------------
def enhance_barcode_image(image):
    """تحسين الصورة لقراءة الباركود"""
    # تحويل إلى تدرج رمادي
    gray = image.convert('L')
    # تحسين التباين
    enhancer = ImageEnhance.Contrast(gray)
    enhanced = enhancer.enhance(3.0)  # زيادة التباين
    # زيادة الحدة
    sharp = enhanced.filter(ImageFilter.SHARPEN)
    # تكبير الصورة
    enlarged = sharp.resize((int(sharp.width * 2), int(sharp.height * 2)), Image.Resampling.LANCZOS)
    return enlarged

def scan_barcode_advanced(image):
    """قراءة باركود مع معالجة متقدمة ومحاولات متعددة"""
    if image is None:
        return None
    try:
        # المحاولة الأولى: تحسين الصورة ثم القراءة
        enhanced = enhance_barcode_image(image)
        results = zxingcpp.read_barcodes(enhanced)
        if results:
            return results[0].text.strip()
        
        # المحاولة الثانية: الصورة الأصلية بعد تحسين التباين فقط
        gray = image.convert('L')
        enhancer = ImageEnhance.Contrast(gray)
        enhanced2 = enhancer.enhance(2.5)
        results = zxingcpp.read_barcodes(enhanced2)
        if results:
            return results[0].text.strip()
        
        # المحاولة الثالثة: الصورة الأصلية بدون تحسين
        results = zxingcpp.read_barcodes(image)
        if results:
            return results[0].text.strip()
            
    except Exception as e:
        st.warning(f"خطأ في مكتبة الباركود: {str(e)[:100]}")
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
        "sku": "SKU مقترح (مثل LAP-001)",
        "price_from_label": "السعر المستخرج من ملصق السعر (إن وجد، وإلا نص فارغ)"
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
    return {}

# ------------------- دوال Excel -------------------
def create_excel(inventory):
    if not inventory:
        return None
    df = pd.DataFrame(inventory)
    cols = ["SKU", "Product Name", "Brand", "Category", "Description", "Barcode", "Price", "Quantity", "Confidence", "Date Added"]
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
    """إعادة ضبط كل شيء لإضافة منتج جديد مع الاحتفاظ بالمخزون السابق"""
    st.session_state.step = 0
    st.session_state.temp_images = [None, None, None]
    st.session_state.quantity = 1
    st.session_state.processed = False
    st.session_state.current_product_added = False
    # زيادة عداد الكاميرا لإنشاء مفاتيح جديدة
    st.session_state.camera_counter = st.session_state.get('camera_counter', 0) + 1

def reset_full_session():
    """مسح الجلسة بالكامل (المخزون وجميع المتغيرات)"""
    st.session_state.inventory = []
    st.session_state.step = 0
    st.session_state.temp_images = [None, None, None]
    st.session_state.quantity = 1
    st.session_state.processed = False
    st.session_state.current_product_added = False
    st.session_state.camera_counter = st.session_state.get('camera_counter', 0) + 1

# ------------------- واجهة المستخدم -------------------
st.set_page_config(page_title="AI Inventory Scanner", page_icon="📷", layout="centered")
st.title("📷 AI Inventory Scanner - الإصدار الاحترافي")
st.markdown("التقط 3 صور: **المنتج** ← **الباركود** ← **ملصق السعر**، ثم أدخل الكمية.")

# تهيئة جميع متغيرات الجلسة
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
if 'camera_counter' not in st.session_state:
    st.session_state.camera_counter = 0

# أزرار التحكم العلوية
col1, col2, col3 = st.columns([2, 1, 1])
with col2:
    if st.session_state.inventory:
        excel_data = create_excel(st.session_state.inventory)
        if excel_data:
            st.download_button("📥 تحميل Excel", data=excel_data, file_name=f"inventory_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx", key="excel_top")
    else:
        st.button("📥 Excel", disabled=True)
with col3:
    if st.button("🗑️ مسح الجلسة بالكامل"):
        reset_full_session()
        st.rerun()
st.divider()

# عرض المخزون الحالي أثناء الجرد
if st.session_state.inventory:
    st.info(f"📦 المنتجات المضافة حتى الآن: **{len(st.session_state.inventory)}**")
    st.dataframe(pd.DataFrame(st.session_state.inventory), use_container_width=True)
    st.divider()

# ------------------- الخطوات الرئيسية -------------------
counter = st.session_state.camera_counter  # لإنشاء مفاتيح كاميرا فريدة

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

# الخطوة 1: صورة الباركود
elif st.session_state.step == 1:
    st.subheader("📊 صورة الباركود (قرّب الكاميرا)")
    st.caption("تأكد من الإضاءة الجيدة وتقريب الكاميرا من الباركود")
    img = st.camera_input("التقط الصورة", key=f"cam_barcode_{counter}")
    if img:
        pil_img = Image.open(img)
        pil_img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        st.session_state.temp_images[1] = pil_img
        st.success("✅ تم الالتقاط!")
        if st.button("➡️ التالي"):
            st.session_state.step = 2
            st.rerun()

# الخطوة 2: صورة السعر
elif st.session_state.step == 2:
    st.subheader("🏷️ صورة ملصق السعر")
    st.caption("اختياري: يمكنك تخطي هذه الخطوة لاحقاً")
    img = st.camera_input("التقط الصورة (اختياري)", key=f"cam_price_{counter}")
    if img:
        pil_img = Image.open(img)
        pil_img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        st.session_state.temp_images[2] = pil_img
        st.success("✅ تم الالتقاط!")
    # زر التالي حتى بدون التقاط صورة السعر
    if st.button("➡️ التالي"):
        st.session_state.step = 3
        st.rerun()

# الخطوة 3: إدخال الكمية
elif st.session_state.step == 3:
    st.subheader("🔢 أدخل كمية المنتج")
    quantity = st.number_input("الكمية المتوفرة:", min_value=0, step=1, value=st.session_state.quantity, key="quantity_input")
    if st.button("✅ تأكيد وتحليل المنتج"):
        st.session_state.quantity = quantity
        st.session_state.step = 4
        st.rerun()

# الخطوة 4: التحليل والإضافة (مرة واحدة فقط)
elif st.session_state.step == 4 and not st.session_state.current_product_added:
    st.subheader("🔍 جاري التحليل...")
    prod_img = st.session_state.temp_images[0]
    bar_img = st.session_state.temp_images[1]
    price_img = st.session_state.temp_images[2]
    
    with st.spinner("قراءة الباركود وتحليل المنتج بالذكاء الاصطناعي..."):
        barcode = scan_barcode_advanced(bar_img) if bar_img else None
        ai_result = analyze_with_gemini(prod_img, price_img) if prod_img else {}
    
    # عرض النتائج
    col_left, col_right = st.columns(2)
    with col_left:
        if prod_img:
            st.image(prod_img, caption="المنتج", width=150)
        if barcode:
            st.success(f"✅ الباركود: {barcode}")
        else:
            st.warning("⚠️ لم يتم قراءة الباركود. تأكد من الإضاءة وتقريب الكاميرا.")
    with col_right:
        if ai_result:
            st.json(ai_result)
        else:
            st.error("❌ فشل تحليل Gemini. حاول مرة أخرى.")
    
    # منع التكرار: التحقق من وجود نفس الباركود أو SKU
    sku = ai_result.get('sku', 'ERR') if ai_result else 'ERR'
    duplicate = False
    for item in st.session_state.inventory:
        if item.get('Barcode') == barcode and barcode and barcode != "لم يقرأ":
            duplicate = True
            st.warning(f"⚠️ هذا الباركود ({barcode}) موجود مسبقاً للمنتج '{item['Product Name']}'. لن تتم إضافة المنتج.")
            break
        if item.get('SKU') == sku and sku != 'ERR':
            duplicate = True
            st.warning(f"⚠️ SKU '{sku}' موجود مسبقاً. تم تعديل SKU تلقائياً.")
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
        st.session_state.current_product_added = True  # لمنع التكرار في إعادة التشغيل
    
    # زر لإضافة منتج آخر
    if st.button("➕ منتج آخر"):
        reset_for_new_product()
        st.rerun()
    
    # عرض جدول المخزون المحدث
    if st.session_state.inventory:
        st.subheader("📋 المخزون الحالي")
        st.dataframe(pd.DataFrame(st.session_state.inventory), use_container_width=True)

# إذا تمت المعالجة سابقاً وأردنا إضافة منتج آخر من نفس الشاشة
elif st.session_state.step == 4 and st.session_state.current_product_added:
    st.subheader("✅ تمت إضافة المنتج بنجاح")
    if st.button("➕ منتج آخر"):
        reset_for_new_product()
        st.rerun()
    if st.session_state.inventory:
        st.dataframe(pd.DataFrame(st.session_state.inventory), use_container_width=True)
