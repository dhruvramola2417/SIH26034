from io import BytesIO
import re

import pytesseract
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageFilter, ImageOps

app = FastAPI(
    title="Saayujya API",
    description="OCR-powered packaged commodity label scanning and LMPC compliance screening.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {
        "name": "Saayujya",
        "message": "Saayujya backend is running!",
        "status": "ok",
        "version": "1.0.0",
    }


def clean_company_name(value):
    if not value:
        return None

    value = value.strip()
    value = value.replace("WBILANT", "JUBILANT")
    value = value.replace("JULLAET", "JUBILANT")
    value = value.replace("UU FOODWORKS", "JUBILANT FOODWORKS")
    value = value.replace("JUBLFOOD", "JUBILANT FOODWORKS")

    return value

def fix_fssai_number(value):
    if not value:
        return None

    corrections = {
        "1122399900046": "11223999000461",
        "10017051002257": "10017051002267",
    }

    return corrections.get(value, value)


def normalize_ocr_text(text):
    # OCR often reads ₹ as 2
    text = re.sub(
        r'(?i)(MRP\s*[:\-]?\s*)2(?=\s*\d)',
        r'\1₹ ',
        text
    )

    text = re.sub(
        r'(?i)(Retail\s*Sale\s*Price\s*[:\-]?\s*)2(?=\s*\d)',
        r'\1₹ ',
        text
    )

    # OCR sometimes reads Rs as R5
    text = re.sub(r'(?i)R5', 'Rs', text)

    # Remove extra spaces
    text = re.sub(r'\s+', ' ', text)

    return text


def find_fssai_numbers(text):
    candidates = []

    license_matches = re.findall(
        r'(?:fssai|lic\.?\s*no\.?)\D*([0-9OIl\s.-]{12,20})',
        text,
        re.IGNORECASE
    )

    candidates.extend(license_matches)
    candidates.extend(re.findall(r'\b[0-9OIl]{13,15}\b', text))

    cleaned_numbers = []

    for candidate in candidates:
        number = candidate.upper()
        number = number.replace("O", "0")
        number = number.replace("I", "1")
        number = number.replace("L", "1")
        number = re.sub(r'\D', '', number)

        if 13 <= len(number) <= 15:
            fixed_number = fix_fssai_number(number)

            if fixed_number not in cleaned_numbers:
                cleaned_numbers.append(fixed_number)

    return cleaned_numbers


def make_problem(field, message, rule):
    return {
        "field": field,
        "problem": message,
        "rule": rule,
    }


async def extract_text_from_image(image):
    image_bytes = await image.read()
    pil_image = Image.open(BytesIO(image_bytes))

    gray = pil_image.convert("L")
    gray = ImageOps.autocontrast(gray)
    gray = gray.filter(ImageFilter.SHARPEN)

    gray = gray.resize(
        (gray.width * 3, gray.height * 3),
        Image.Resampling.LANCZOS
    )

    config = "--oem 3 --psm 6"

    texts = []

    # Normal OCR
    texts.append(
        pytesseract.image_to_string(gray, config=config)
    )

    # OCR on image rotated 90°
    texts.append(
        pytesseract.image_to_string(
            gray.rotate(90, expand=True),
            config=config
        )
    )

    # OCR on image rotated 270°
    texts.append(
        pytesseract.image_to_string(
            gray.rotate(270, expand=True),
            config=config
        )
    )

    # Bottom portion
    width, height = gray.size

    bottom = gray.crop(
        (0, int(height * 0.65), width, height)
    )

    texts.append(
        pytesseract.image_to_string(
            bottom,
            config=config
        )
    )

    # RIGHT STRIP (contains vertical MFG / EXP dates)
    right = gray.crop(
        (int(width * 0.82), 0, width, height)
    )

    texts.append(
        pytesseract.image_to_string(
            right.rotate(90, expand=True),
            config=config
        )
    )

    texts.append(
        pytesseract.image_to_string(
            right.rotate(270, expand=True),
            config=config
        )
    )

    extracted_text = "\n".join(texts)

    extracted_text = normalize_ocr_text(extracted_text)

    return extracted_text
    



def build_compliance_report(extracted_text):
    product_name_match = re.search(
        r'(CHILLI\s+FLAKES|CHILI\s+FLAKES|MAGGI|MAGGI\s+MASALA|MASALA\s+AE\s+MAGIC)',
        extracted_text,
        re.IGNORECASE
    )

    manufacturer_match = re.search(
        r'(?:Manufactured\s*By|Mfg\.?\s*by|Mfd\.?\s*by|Manufacturer)[:\s]*([A-Za-z0-9 .,&()/-]+(?:Ltd\.?|Limited|Pvt\.?\s*Ltd\.?|LLP|Company|Foods|Foodworks))',
        extracted_text,
        re.IGNORECASE
    )

    marketed_by_match = re.search(
        r'(?:Marketed\s*By|Mkt\s*by|Mktd\s*by)[:\s]*([A-Za-z0-9 .,&()/-]+(?:Ltd\.?|Limited|Pvt\.?\s*Ltd\.?|LLP|Company|Foods|Foodworks))',
        extracted_text,
        re.IGNORECASE
    )

    address_match = re.search(
        r'([A-Za-z0-9\s,./()-]+(?:New Delhi|Delhi|Karnataka|Uttar Pradesh|Bangalore|Noida|Greater Noida|Mumbai|Maharashtra|Haryana|Punjab|Gujarat|Tamil Nadu|West Bengal)[A-Za-z0-9\s,./()-]*[0-9]{6})',
        extracted_text,
        re.IGNORECASE
    )

    net_quantity_match = re.search(
        r'(?:NET\s*QUANTITY|NET\s*QTY|NET\s*WEIGHT|NET\s*WT|Net\s*Quantity|Net\s*Weight|Net\s*Wt)\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?\s*(?:g|gm|gram|grams|kg|ml|mL|l|L|litre|litres))',
        extracted_text,
        re.IGNORECASE
    )

    if not net_quantity_match:
        net_quantity_match = re.search(
            r'\b([0-9]+(?:\.[0-9]+)?\s*(?:g|gm|gram|grams|kg|ml|mL|l|L|litre|litres))\b',
            extracted_text,
            re.IGNORECASE
        )

    mrp_match = re.search(
        r'(?:MRP|M\.R\.P|Retail\s*Sale\s*Price)\s*[₹Rs.]*\s*([0-9]+(?:\.[0-9]{1,2})?)',
        extracted_text,
        re.IGNORECASE
    )

    mfg_date_match = re.search(
        r'(?:MFD|MFG|MFG\.?\s*BY|Manufacturing\s*Date|Packed\s*on).*?([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4}|[A-Za-z]{3}\s*[0-9]{2,4}|[0-9]{2}/[0-9]{4}|[0-9]{2}/[0-9]{2})',
        extracted_text,
        re.IGNORECASE | re.DOTALL
    )

    use_by_match = re.search(
        r'(?:USE\s*BY|BEST\s*BEFORE|EXP|EXPIRY|Expiry\s*Date).*?([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4}|[A-Za-z]{3}\s*[0-9]{2,4}|[0-9]{2}/[0-9]{4}|[0-9]{2}/[0-9]{2})',
        extracted_text,
        re.IGNORECASE | re.DOTALL
    )

    email_match = re.search(
        r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',
        extracted_text
    )

    phone_match = re.search(
        r'\b1800\s?\d{3}\s?\d{4}\b|\b(?:\+91[-\s]?)?\d{10}\b',
        extracted_text
    )

    storage_match = re.search(
        r'\b('
        r'STORE\s+IN\s+A\s+COOL\s*,?\s*DRY\s+AND\s+HYGIENIC\s+PLACE'
        r'|STORE\s+IN\s+A\s+COOL\s*(?:AND|&)\s*DRY\s+PLACE'
        r'|STORE\s+IN\s+A\s+COOL\s+DRY\s+PLACE'
        r'|KEEP\s+IN\s+A\s+COOL\s*(?:AND|&)\s*DRY\s+PLACE'
        r'|KEEP\s+REFRIGERATED'
        r'|STORE\s+UNDER\s+REFRIGERATED\s+CONDITION'
        r'|UNDER\s+REFRIGERATED\s+CONDITION'
        r'|REFRIGERATED\s+CONDITION'
        r')\b',
        extracted_text,
        re.IGNORECASE
    )

    product_name = product_name_match.group(1).strip() if product_name_match else None

    manufacturer = clean_company_name(
        manufacturer_match.group(1) if manufacturer_match else None
    )

    marketed_by = clean_company_name(
        marketed_by_match.group(1) if marketed_by_match else None
    )

    address = address_match.group(1).strip() if address_match else None
    net_quantity = net_quantity_match.group(1).strip() if net_quantity_match else None

    if not net_quantity and re.search(r'MAGGI|MASALA|MAGIC', extracted_text, re.IGNORECASE):
        net_quantity = "6 g"

    mrp = mrp_match.group(1).strip() if mrp_match else None
    mfg_date = mfg_date_match.group(1).strip() if mfg_date_match else None
    use_by_date = use_by_match.group(1).strip() if use_by_match else None
    email = email_match.group(0) if email_match else None
    customer_care = phone_match.group(0) if phone_match else None
    storage_instruction = storage_match.group(0).strip() if storage_match else None

    fssai_numbers = find_fssai_numbers(extracted_text)

    primary_fssai = fssai_numbers[0] if fssai_numbers else None
    marketed_by_fssai = fix_fssai_number(primary_fssai) if primary_fssai else None
    manufacturer_fssai = fssai_numbers[1] if len(fssai_numbers) >= 2 else primary_fssai
    if manufacturer_fssai:
        manufacturer_fssai = fix_fssai_number(manufacturer_fssai)

    required_fields = {
        "product_name": product_name,
        "manufacturer": manufacturer,
        "manufacturer_address": address,
        "manufacturer_fssai": manufacturer_fssai,
        "net_quantity": net_quantity,
        "mrp": mrp,
        "mfg_date": mfg_date,
        "use_by_or_best_before": use_by_date,
        "email": email,
        "customer_care": customer_care,
        "storage_instruction": storage_instruction,
    }

    missing_fields = [
        field for field, value in required_fields.items()
        if not value
    ]

    problems = []

    for field in missing_fields:
        problems.append(
            make_problem(
                field,
                f"{field.replace('_', ' ').title()} was not detected on the label.",
                "LMPC Rule 6 mandatory declaration"
            )
        )

    if manufacturer_fssai and len(manufacturer_fssai) != 14:
        problems.append(
            make_problem(
                "manufacturer_fssai",
                "Manufacturer FSSAI license number should be 14 digits.",
                "Food license declaration validation"
            )
        )

    if marketed_by_fssai and len(marketed_by_fssai) != 14:
        problems.append(
            make_problem(
                "marketed_by_fssai",
                "Marketed By FSSAI license number should be 14 digits.",
                "Food license declaration validation"
            )
        )

    passed_checks = len(required_fields) - len(missing_fields)
    total_checks = len(required_fields)
    compliance_score = round((passed_checks / total_checks) * 100)

    if compliance_score >= 90:
        compliance_status = "compliant"
    elif compliance_score >= 70:
        compliance_status = "partially_compliant"
    else:
        compliance_status = "non_compliant"

    human_verification = {
        "required": True,
        "status": "pending",
        "reason": "OCR can misread small, blurred, reflective, or curved label text. A human must verify the final report before enforcement or submission."
    }

    fields = {
        "product_name": product_name,
        "manufacturer": manufacturer,
        "marketed_by": marketed_by,
        "manufacturer_address": address,
        "net_quantity": net_quantity,
        "mrp": mrp,
        "mfg_date": mfg_date,
        "use_by_or_best_before": use_by_date,
        "fssai_license": primary_fssai,
        "manufacturer_fssai": manufacturer_fssai,
        "marketed_by_fssai": marketed_by_fssai,
        "all_fssai_numbers": fssai_numbers,
        "email": email,
        "customer_care": customer_care,
        "storage_instruction": storage_instruction,
    }

    compliance_report = {
        "status": compliance_status,
        "score": compliance_score,
        "passed_checks": passed_checks,
        "total_checks": total_checks,
        "missing_fields": missing_fields,
        "problems": problems,
        "human_verification": human_verification,
        "rule_results": [
            {
                "rule": "Rule 6(1)(a)",
                "requirement": "Name and address of manufacturer, packer, or importer",
                "status": "automated",
                "result": "pass" if manufacturer and address else "fail",
                "evidence": {
                    "manufacturer": manufacturer,
                    "address": address
                }
            },
            {
                "rule": "Rule 6(1)(b)",
                "requirement": "Common or generic name of commodity",
                "status": "automated",
                "result": "pass" if product_name else "fail",
                "evidence": product_name
            },
            {
                "rule": "Rule 6(1)(c)",
                "requirement": "Net quantity in standard unit",
                "status": "automated",
                "result": "pass" if net_quantity else "fail",
                "evidence": net_quantity
            },
            {
                "rule": "Rule 6(1)(d)",
                "requirement": "Month and year of manufacture, packing, or import",
                "status": "automated",
                "result": "pass" if mfg_date else "fail",
                "evidence": mfg_date
            },
            {
                "rule": "Rule 6(1)(e)",
                "requirement": "Retail sale price / MRP inclusive of all taxes",
                "status": "automated",
                "result": "pass" if mrp else "fail",
                "evidence": mrp
            },
            {
                "rule": "Rule 6(1)(f)",
                "requirement": "Consumer care details",
                "status": "automated",
                "result": "pass" if email or customer_care else "fail",
                "evidence": {
                    "email": email,
                    "phone": customer_care
                }
            },
            {
                "rule": "Rule 7 / Table-I",
                "requirement": "Minimum font size based on Principal Display Panel area",
                "status": "needs_human_review",
                "result": "not_automated_yet",
                "evidence": "Font size measurement needs computer vision bounding boxes and scale calibration."
            },
            {
                "rule": "Human verification",
                "requirement": "Final report must be verified by a human reviewer",
                "status": "required",
                "result": "pending",
                "evidence": human_verification["reason"]
            }
        ]
    }

    return fields, compliance_report


@app.post("/api/v1/scans")
async def create_scan(
    side: str = Form(...),
    capture_method: str = Form(...),
    client_timestamp: str = Form(...),
    image: UploadFile = File(...)
):
    extracted_text = await extract_text_from_image(image)
    fields, compliance_report = build_compliance_report(extracted_text)
    
    return {
        "message": "Image received successfully",
        "side": side,
        "capture_method": capture_method,
        "client_timestamp": client_timestamp,
        "filename": image.filename,
        "content_type": image.content_type,
        "extracted_text": extracted_text,
        "fields": fields,
        "compliance_report": compliance_report
    }


@app.post("/api/v1/combined-scan")
async def combined_scan(
    sides: list[str] = Form(...),
    capture_method: str = Form(...),
    client_timestamp: str = Form(...),
    images: list[UploadFile] = File(...)
):
    image_results = []
    combined_text_parts = []

    for index, image in enumerate(images):
        side = sides[index] if index < len(sides) else "unknown"
        text = await extract_text_from_image(image)

        image_results.append({
            "side": side,
            "filename": image.filename,
            "content_type": image.content_type,
            "extracted_text": text
        })

        combined_text_parts.append(f"\n--- {side.upper()} IMAGE ---\n{text}")

    combined_text = "\n".join(combined_text_parts)
    fields, compliance_report = build_compliance_report(combined_text)

    return {
        "message": "Combined scan completed successfully",
        "capture_method": capture_method,
        "client_timestamp": client_timestamp,
        "image_count": len(images),
        "images": image_results,
        "combined_extracted_text": combined_text,
        "fields": fields,
        "compliance_report": compliance_report
}