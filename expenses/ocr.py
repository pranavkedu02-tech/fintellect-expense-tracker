import re
import pytesseract
from PIL import Image
from django.conf import settings

pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD


def extract_text_from_image(image_file):
    """Takes an uploaded image file and returns all text Tesseract can read from it."""
    image = Image.open(image_file)
    text = pytesseract.image_to_string(image)
    return text


def guess_amount(text):
    """
    Very simple pattern matching: looks for lines containing 'total'
    and tries to pull out a number from them. Falls back to the
    largest number found anywhere in the text if no 'total' line exists.
    This is a best-effort guess, not guaranteed to be correct.
    """
    lines = text.lower().splitlines()
    number_pattern = r"[\d,]+\.?\d{0,2}"

    # First, look specifically for a line mentioning "total"
    for line in lines:
        if "total" in line:
            matches = re.findall(number_pattern, line)
            if matches:
                cleaned = matches[-1].replace(",", "")
                try:
                    return float(cleaned)
                except ValueError:
                    continue

    # Fallback: grab the largest number found anywhere in the receipt
    all_matches = re.findall(number_pattern, text)
    numbers = []
    for m in all_matches:
        cleaned = m.replace(",", "")
        try:
            numbers.append(float(cleaned))
        except ValueError:
            continue

    return max(numbers) if numbers else None