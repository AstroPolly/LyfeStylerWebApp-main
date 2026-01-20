# email_utils.py - исправленная версия
def send_verification_email(email: str, code: str):
    # В консоли покажем код (для разработки)
    print(f"📧 MOCK EMAIL to {email}")
    print(f"🔑 Your verification code: {code}")
    print("✅ In production, this would be sent via SMTP.")
    return True