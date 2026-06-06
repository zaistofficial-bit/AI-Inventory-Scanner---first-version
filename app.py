# app.py - النسخة النهائية للمرحلة الأولى
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

# ------------------- دوال معالجة قوية -------------------
def scan_barcode_advanced(image):
    """قراءة باركود حتى لو كان صغيراً جداً - مع تحسينات قوية"""
    try:
        # تحويل الصورة إلى تدرج رمادي ورفع التباين
        gray = image.convert('L')
        enhancer = ImageEnhance.Contrast(gray)
        enhanced = enhancer.enhance(2.5)
        
        # تكبير الصورة قليلاً لتحسين القراءة
        width, height = enhanced.size
        enlarged = enhanced.resize((int(width*1.5), int(height*1.5)), Image.Resampling.LANCZOS)
        
        # محاولة القراءة من الصورة المحسنة
        result = read_barcode(enlarged)
        if result and result.text:
            return result.text.strip()
        
        # محاولة ثانية من الصورة الأصلية
        result = read_barcode(image)
        if result and result.text:
            return result.text.strip()
            
    except Exception:
        pass
    return None

def analyze_product_with_gemini(product_img, price_tag_img=None):
    """Gemini يحلل المنتج ويقرأ ملصق السعر إن وجد"""
    prompt = """
    أنت خبير في المنتجات الإلكترونية. قم بتحليل الصورة(ز) التالية:
    - الصورة الأولى: المنتج نفسه.
    - الصورة الثانية (إن وجدت): ملصق سعر مكتوب عليه رقم (مثل 49.99 ريال أو 120 درهم).

    أخرج فقط JSON صالحاً بهذه الحقول:
    {
        "product_name": "اسم المنتج بالانجليزي",
        "brand": "العلامة التجارية",
        "category": "Laptop/Printer/Accessory/Mobile Accessory",
        "description": "وصف قصير جداً (أقل من 12 كلمة)",
        "sku": "مثل LAP-001",
        "price_from_label": "السعر المستخرج من ملصق السعر (إن وجد، وإلا فاتركها فارغة)"
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
        return {}
    except Exception as e:
        st.error(f"خطأ Gemini: {e}")
        return {}

def create_excel(inventory):
    """إنشاء Excel بجميع الأعمدة المطلوبة"""
    if not inventory:
        return None
    df = pd.DataFrame(inventory)
    cols = ["SKU", "Product Name", "Brand", "Category", "Description", 
            "Barcode", "Price", "Quantity", "Confidence Score"]
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df = df[cols]
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Inventory')
    return output.getvalue()

# ------------------- واجهة المستخدم -------------------
st.set_page_config(page_title="AI Inventory Scanner Pro", page_icon="📦", layout="centered")
st.title("📦 AI Inventory Scanner - الإصدار الاحترافي")
st.markdown("**للمحلات الإلكترونية** | التقط 4 صور: المنتج، الباركود، ملصق السعر، الكمية (تدخل يدوياً)")

# تهيئة حالة الجلسة
if 'inventory' not in st.session_state:
    st.session_state.inventory = []
if 'step' not in st.session_state:
    st.session_state.step = 0  # 0=منتج, 1=باركود, 2=سعر, 3=كمية (إدخال يدوي)
if 'temp_images' not in st.session_state:
    st.session_state.temp_images = [None, None, None]  # منتج, باركود, سعر
if 'quantity' not in st.session_state:
    st.session_state.quantity = 1
if 'processing_done' not in st.session_state:
    st.session_state.processing_done = False

# زر Excel في الأعلى
col_top1, col_top2 = st.columns([3, 1])
with col_top2:
    if st.session_state.inventory:
        excel_data = create_excel(st.session_state.inventory)
        if excel_data:
            st.download_button("📥 تحميل Excel", data=excel_data, file_name="inventory.xlsx")
    else:
        st.button("📥 Excel", disabled=True)

st.divider()

# ------------------- الخطوة 1,2,3: التقاط الصور -------------------
if st.session_state.step < 3:
    step_names = ["1️⃣ صورة المنتج", "2️⃣ صورة الباركود (حتى لو صغير)", "3️⃣ صورة ملصق السعر (اللي وضعته أنت)"]
    st.subheader(step_names[st.session_state.step])
    
    if st.session_state.temp_images[st.session_state.step] is not None:
        st.image(st.session_state.temp_images[st.session_state.step], caption="الصورة الحالية", width=200)
        if st.button("📸 إعادة التصوير"):
            st.session_state.temp_images[st.session_state.step] = None
            st.rerun()
        if st.button("➡️ التالي"):
            st.session_state.step += 1
            st.rerun()
    else:
        img = st.camera_input("التقط الصورة الآن")
        if img is not None:
            pil_img = Image.open(img)
            pil_img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            st.session_state.temp_images[st.session_state.step] = pil_img
            st.success("✅ تم الالتقاط! اضغط 'التالي'")
            if st.button("➡️ التالي"):
                st.session_state.step += 1
                st.rerun()

# ------------------- الخطوة 4: إدخال الكمية يدوياً -------------------
elif st.session_state.step == 3:
    st.subheader("4️⃣ أدخل كمية المنتج المتوفرة")
    quantity = st.number_input("الكمية", min_value=0, step=1, value=1)
    if st.button("✅ تأكيد الكمية وتحليل المنتج"):
        st.session_state.quantity = quantity
        st.session_state.step = 4  # انتقل للمعالجة
        st.rerun()

# ------------------- الخطوة 5: معالجة وعرض النتيجة -------------------
elif st.session_state.step == 4 and not st.session_state.processing_done:
    st.subheader("🔍 جاري التحليل...")
    prod_img = st.session_state.temp_images[0]
    bar_img = st.session_state.temp_images[1]
    price_img = st.session_state.temp_images[2]
    
    with st.spinner("قراءة الباركود والذكاء الاصطناعي..."):
        barcode = scan_barcode_advanced(bar_img) if bar_img else None
        ai_result = analyze_product_with_gemini(prod_img, price_img)
    
    st.success("تم التحليل")
    
    # عرض النتائج
    col1, col2 = st.columns(2)
    with col1:
        st.image(prod_img, caption="المنتج", width=150)
    with col2:
        if ai_result:
            st.json(ai_result)
    
    # إظهار تحذير للباركود إن لم يقرأ
    if not barcode:
        st.warning("⚠️ لم يتم قراءة الباركود. تأكد من تصويره بشكل مقرب وواضح.")
    else:
        st.success(f"✅ الباركود: {barcode}")
    
    # حفظ المنتج في الجرد
    new_item = {
        "SKU": ai_result.get('sku', 'ERR-SKU') if ai_result else 'ERR-SKU',
        "Product Name": ai_result.get('product_name', 'غير معروف') if ai_result else 'غير معروف',
        "Brand": ai_result.get('brand', 'غير معروف') if ai_result else 'غير معروف',
        "Category": ai_result.get('category', 'غير معروف') if ai_result else 'غير معروف',
        "Description": ai_result.get('description', '') if ai_result else '',
        "Barcode": barcode if barcode else "لم يقرأ",
        "Price": ai_result.get('price_from_label', '') if ai_result else '',
        "Quantity": st.session_state.quantity,
        "Confidence Score": "85%"
    }
    st.session_state.inventory.append(new_item)
    
    # أزرار التحكم
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("➕ منتج آخر"):
            # إعادة ضبط كل شيء
            st.session_state.step = 0
            st.session_state.temp_images = [None, None, None]
            st.session_state.quantity = 1
            st.session_state.processing_done = False
            st.rerun()
    with col_b:
        if st.session_state.inventory:
            excel_data = create_excel(st.session_state.inventory)
            if excel_data:
                st.download_button("📥 إنهاء وتحميل Excel", data=excel_data, file_name="inventory.xlsx")
    
    st.divider()
    st.subheader(f"📋 المنتجات المضافة ({len(st.session_state.inventory)})")
    st.dataframe(pd.DataFrame(st.session_state.inventory))
    
    st.session_state.processing_done = True

# ------------------- عرض المنتجات أثناء العمل -------------------
if st.session_state.step < 4 and st.session_state.inventory:
    st.divider()
    st.info(f"✅ تم إضافة {len(st.session_state.inventory)} منتج حتى الآن")
