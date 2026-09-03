from io import BytesIO
import re

import pytesseract
from google.cloud import vision
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

    return value.strip()

def fix_fssai_number(value):
    if not value:
        return None

    return value


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
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n+', '\n', text)

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

    try:
        client = vision.ImageAnnotatorClient()

        vision_image = vision.Image(content=image_bytes)

        response = client.document_text_detection(
            image=vision_image
        )

        if response.error.message:
            raise RuntimeError(response.error.message)

        extracted_text = response.full_text_annotation.text

        if not extracted_text.strip():
            raise RuntimeError("Google Cloud Vision returned no text.")

        return normalize_ocr_text(extracted_text)

    except Exception as error:
        print(f"Cloud Vision failed: {error}")
        print("Falling back to Tesseract OCR.")

        pil_image = Image.open(BytesIO(image_bytes))

        gray = pil_image.convert("L")
        gray = ImageOps.autocontrast(gray)
        gray = gray.filter(ImageFilter.SHARPEN)

        gray = gray.resize(
            (gray.width * 3, gray.height * 3),
            Image.Resampling.LANCZOS
        )

        return normalize_ocr_text(
            pytesseract.image_to_string(
                gray,
                config="--oem 3 --psm 6"
            )
        )  

def find_labeled_value(text, labels, value_pattern, lookahead=5):
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for i, line in enumerate(lines):
        for label in labels:
            label_match = re.search(label, line, re.IGNORECASE)

            if not label_match:
                continue

            # First check text after the label on the same line
            after_label = line[label_match.end():]

            value_match = re.search(
                value_pattern,
                after_label,
                re.IGNORECASE
            )

            if value_match:
                return value_match.group(1)

            # Then check a few following OCR lines
            for next_line in lines[i + 1:i + 1 + lookahead]:
                value_match = re.search(
                    value_pattern,
                    next_line,
                    re.IGNORECASE
                )

                if value_match:
                    return value_match.group(1)

    return None

def build_compliance_report(extracted_text):
    product_name_match = re.search(
    r'(?:Product\s*Name|Name\s*of\s*(?:Commodity|Product)|Commodity\s*Name)\s*[:\-]?\s*([^\n]+)',
    extracted_text,
    re.IGNORECASE
)

    manufacturer_match = re.search(
    r'(?:Manufactured\s*By|Mfg\.?\s*by|Mfd\.?\s*by|Manufacturer)\s*[:\-]?\s*([^\n,]+?(?:Ltd\.?|Limited|Pvt\.?\s*Ltd\.?|LLP|Foods?|Foodworks))',
    extracted_text,
    re.IGNORECASE
    )

    marketed_by_match = re.search(
    r'(?:Marketed\s*By|Mkt\.?\s*by|Mktd\.?\s*by)\s*[:\-]?\s*([^\n,]+?(?:Ltd\.?|Limited|Pvt\.?\s*Ltd\.?|LLP|Foods?|Foodworks))',
    extracted_text,
    re.IGNORECASE
    )

    address_match = re.search(
    r'(?:Manufactured\s*By|Mfg\.?\s*by|Mfd\.?\s*by|Manufacturer|'
    r'Marketed\s*By|Mkt\.?\s*by|Mktd\.?\s*by)'
    r'\s*[:\-]?\s*'
    r'[^\n]*'
    r'(?:\n[^\n]*){0,4}?'
    r'\b\d{3}\s?\d{3}\b',
    extracted_text,
    re.IGNORECASE
)

    net_quantity_match = re.search(
    r'(?:NET\s*QUANTITY|NET\s*QTY|NET\s*WEIGHT|NET\s*WT)'
    r'\s*[:\-]?\s*'
    r'([0-9]+(?:\.[0-9]+)?\s*(?:g|gm|gram|grams|kg|ml|mL|l|L|litre|litres))',
    extracted_text,
    re.IGNORECASE
)

    if not net_quantity_match:
        net_quantity_value = find_labeled_value(
        extracted_text,
        [
            r'\bNET\s*QUANTITY\b',
            r'\bNET\s*QTY\b',
            r'\bNET\s*WEIGHT\b',
            r'\bNET\s*WT\b'
        ],
        r'([0-9]+(?:\.[0-9]+)?\s*(?:g|gm|gram|grams|kg|ml|mL|l|L|litre|litres))',
        lookahead=80
    )

        if net_quantity_value:
            net_quantity_match = re.search(
            r'([0-9]+(?:\.[0-9]+)?\s*(?:g|gm|gram|grams|kg|ml|mL|l|L|litre|litres))',
            net_quantity_value,
            re.IGNORECASE
        )

    mrp = find_labeled_value(
     extracted_text,
    [
        r'\bMRP\b',
        r'\bM\.?\s*R\.?\s*P\.?\b',
        r'\bMAXIMUM\s+RETAIL\s+PRICE\b',
        r'\bRETAIL\s+SALE\s+PRICE\b'
    ],
    r'(?:₹|€|Rs\.?|INR)?\s*([0-9]+(?:\.[0-9]{1,2})?)\s*(?:/-)?',
    lookahead=10
)

    date_pattern = (
    r'(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}'
    r'|[A-Za-z]{3}[./-]\d{2,4}'
    r'|[A-Za-z]{3}\s+\d{2,4}'
    r'|\d{2}[./-]\d{4})'
)

    mfg_date = find_labeled_value(
    extracted_text,
    [
        r'\bMFD\.?\b',
        r'\bMFG\.?\s*DATE\b',
        r'\bMANUFACTURING\s+DATE\b',
        r'\bPKD\.?\b',
        r'\bPACKED\s+ON\b'
    ],
    date_pattern,
    lookahead=15
)

    use_by_date = find_labeled_value(
    extracted_text,
    [
        r'\bUSE\s+BY\b',
        r'\bBEST\s+BEFORE\b',
        r'\bEXPIRY\b',
        r'\bEXP\.?\s*DATE\b'
    ],
    date_pattern,
    lookahead=15
)

    if use_by_date == mfg_date and mfg_date:
        lines = [line.strip() for line in extracted_text.splitlines() if line.strip()]

        all_dates = []

        for line in lines:
            match = re.fullmatch(date_pattern, line, re.IGNORECASE)
            if match:
                value = match.group(1)

                if value not in all_dates:
                 all_dates.append(value)

        if mfg_date in all_dates:
            mfg_index = all_dates.index(mfg_date)

            if mfg_index + 1 < len(all_dates):
              use_by_date = all_dates[mfg_index + 1]
            else:
                use_by_date = None

    email_match = re.search(
        r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',
        extracted_text
    )

    phone_match = re.search(
        r'\b(?:'
        r'1800(?:[-\s]?\d{2,4}){2,3}'
        r'|(?:\+91[-\s]?)?[6-9]\d{9}'
        r')\b',
        extracted_text,
        re.IGNORECASE
    )

    storage_match = re.search(
        r'\b('
        r'(?:STORE|KEEP)\s+[^\n]{0,80}?'
        r'(?:COOL|DRY|HYGIENIC|REFRIGERAT(?:ED|ION)|FROZEN|'
        r'MOISTURE|SUNLIGHT|TEMPERATURE)'
        r'[^\n]{0,80}'
        r')',
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

    address = address_match.group(0).strip() if address_match else None

    invalid_address_keywords = [
        "INGREDIENT",
        "FLAVOUR",
        "FLAVOR",
        "NUTRITION",
        "EMAIL",
        "@",
        "LIC.",
        "LIC NO",
        "FSSAI",
        "1800",
        "CUSTOMER CARE",
        "WECARE",
        "PROTEIN",
        "CARBOHYDRATE",
        "SUGAR",
        "ENERGY"
]

    if address and any(
        keyword in address.upper()
        for keyword in invalid_address_keywords
):
        address = None
    net_quantity = net_quantity_match.group(1).strip() if net_quantity_match else None


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