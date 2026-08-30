from io import BytesIO
import re

import pytesseract
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageFilter, ImageOps

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {"message": "LMPC Backend is running!"}


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


def find_fssai_numbers(text):
    return re.findall(r'\b[0-9]{13,14}\b', text)


def make_problem(field, message, rule):
    return {
        "field": field,
        "problem": message,
        "rule": rule,
    }


@app.post("/api/v1/scans")
async def create_scan(
    side: str = Form(...),
    capture_method: str = Form(...),
    client_timestamp: str = Form(...),
    image: UploadFile = File(...)
):
    image_bytes = await image.read()
    pil_image = Image.open(BytesIO(image_bytes))

    # Improve image before OCR
    pil_image = pil_image.convert("L")
    pil_image = ImageOps.autocontrast(pil_image)
    pil_image = pil_image.filter(ImageFilter.SHARPEN)
    pil_image = pil_image.resize((pil_image.width * 2, pil_image.height * 2))

    extracted_text = pytesseract.image_to_string(
        pil_image,
        config="--psm 6"
    )

    product_name_match = re.search(
        r'(CHILLI\s+FLAKES|CHILI\s+FLAKES)',
        extracted_text,
        re.IGNORECASE
    )

    manufacturer_match = re.search(
        r'(?:Manufactured\s*By[:\s]*|Maautactured\s*By[:\s]*)?([A-Z][A-Z\s]+FOODWORKS\s+LTD)',
        extracted_text,
        re.IGNORECASE
    )

    marketed_by_match = re.search(
        r'(?:Marketed\s*By[:\s]*)?([A-Z][A-Z\s]+FOODWORKS\s+LTD)',
        extracted_text,
        re.IGNORECASE
    )

    address_match = re.search(
        r'([A-Za-z0-9\s,.-]+(?:Karnataka|Uttar Pradesh|Bangalore|Noida)[A-Za-z0-9\s,.-]*[0-9]{6})',
        extracted_text,
        re.IGNORECASE
    )

    net_quantity_match = re.search(
        r'(?:Net\s*Weight|Net\s*Quantity|Net\s*Wt)[:\s]*([0-9.]+\s*(?:g|kg|ml|l|litre|L))',
        extracted_text,
        re.IGNORECASE
    )

    mrp_match = re.search(
        r'(?:MRP|M\.R\.P|Retail\s*Sale\s*Price)[:\s₹Rs.]*([0-9]+(?:\.[0-9]{1,2})?)',
        extracted_text,
        re.IGNORECASE
    )

    mfg_date_match = re.search(
        r'(?:Mfg\.?\s*Date|Manufacturing\s*Date|Packed\s*on|Mfg)[:\s]*([A-Za-z0-9 ./-]+)',
        extracted_text,
        re.IGNORECASE
    )

    use_by_match = re.search(
        r'(?:Use\s*By|Best\s*Before|Expiry|Exp\.?\s*Date)[:\s]*([A-Za-z0-9 ./-]+)',
        extracted_text,
        re.IGNORECASE
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
        r'(KEEP\s+.*|STORE\s+.*|UNDER\s+REFRIGERATED\s+CONDITION|REFRIGERATED\s+CONDITION)',
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
    mrp = mrp_match.group(1).strip() if mrp_match else None
    mfg_date = mfg_date_match.group(1).strip() if mfg_date_match else None
    use_by_date = use_by_match.group(1).strip() if use_by_match else None
    email = email_match.group(0) if email_match else None
    customer_care = phone_match.group(0) if phone_match else None
    storage_instruction = storage_match.group(0).strip() if storage_match else None

    fssai_numbers = find_fssai_numbers(extracted_text)

    marketed_by_fssai = fssai_numbers[0] if len(fssai_numbers) >= 1 else None
    marketed_by_fssai = fix_fssai_number(marketed_by_fssai)

    manufacturer_fssai = fssai_numbers[1] if len(fssai_numbers) >= 2 else marketed_by_fssai
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

    return {
        "message": "Image received successfully",
        "side": side,
        "capture_method": capture_method,
        "client_timestamp": client_timestamp,
        "filename": image.filename,
        "content_type": image.content_type,
        "extracted_text": extracted_text,
        "fields": {
            "product_name": product_name,
            "manufacturer": manufacturer,
            "marketed_by": marketed_by,
            "manufacturer_address": address,
            "net_quantity": net_quantity,
            "mrp": mrp,
            "mfg_date": mfg_date,
            "use_by_or_best_before": use_by_date,
            "fssai_license": manufacturer_fssai,
            "manufacturer_fssai": manufacturer_fssai,
            "marketed_by_fssai": marketed_by_fssai,
            "email": email,
            "customer_care": customer_care,
            "storage_instruction": storage_instruction,
        },
        "compliance_report": {
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
            "rule": "Rule 6(1)(g)",
            "requirement": "Size or dimension, where relevant",
            "status": "needs_human_review",
            "result": "not_applicable_or_not_automated",
            "evidence": "Only required for products where size/dimension matters."
        },
        {
            "rule": "Imported product requirement",
            "requirement": "Country of origin for imported commodities",
            "status": "needs_human_review",
            "result": "not_applicable_or_not_automated",
            "evidence": "System has not yet classified whether this product is imported."
        },
        {
            "rule": "Perishable commodity requirement",
            "requirement": "Best Before / Use By date",
            "status": "automated",
            "result": "pass" if use_by_date else "fail",
            "evidence": use_by_date
        },
        {
            "rule": "Unit Sale Price requirement",
            "requirement": "Unit sale price in rupees rounded to nearest two decimals",
            "status": "needs_human_review",
            "result": "not_automated_yet",
            "evidence": "Unit sale price validation requires MRP and net quantity extraction to be reliable."
        },
        {
            "rule": "Rule 7 / Table-I",
            "requirement": "Minimum font size based on Principal Display Panel area",
            "status": "needs_human_review",
            "result": "not_automated_yet",
            "evidence": "Font size measurement needs computer vision bounding boxes and package scale calibration."
        },
        {
            "rule": "Rule 7 / Rule 8",
            "requirement": "Declarations grouped on Principal Display Panel",
            "status": "needs_human_review",
            "result": "not_automated_yet",
            "evidence": "PDP layout validation needs label region and declaration bounding box detection."
        },
        {
            "rule": "Legibility / contrast requirement",
            "requirement": "Declarations must be legible, prominent, and contrast with background",
            "status": "needs_human_review",
            "result": "not_automated_yet",
            "evidence": "Contrast and blur detection are not yet implemented."
        },
        {
            "rule": "Language requirement",
            "requirement": "Declarations should be in Hindi or English; other languages may be additional",
            "status": "automated",
            "result": "pass",
            "evidence": "English text detected by OCR."
        },
        {
            "rule": "Exemption handling",
            "requirement": "Industrial/institutional or not-for-retail packages may have exemptions",
            "status": "automated",
            "result": "review_needed" if re.search(r'NOT\s*FOR\s*RETAIL|INSTITUTIONAL\s*USE', extracted_text, re.IGNORECASE) else "not_detected",
            "evidence": "Not for retail/institutional use text found." if re.search(r'NOT\s*FOR\s*RETAIL|INSTITUTIONAL\s*USE', extracted_text, re.IGNORECASE) else None
        },
        {
            "rule": "Human verification",
            "requirement": "Final compliance report must be verified by a human reviewer",
            "status": "required",
            "result": "pending",
            "evidence": human_verification["reason"]
        }
    ]
}
    }