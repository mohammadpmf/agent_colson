"""
حل معادله درجه ۲ با ضرایب a, b, c
"""

import math


def solve_quadratic(a: float, b: float, c: float):
    """
    معادله a x^2 + b x + c = 0 را حل کرده و ریشه‌ها را برمی‌گرداند.

    Returns:
        tuple: (x1, x2) که می‌توانند float یا complex باشند.
    """
    if a == 0:
        raise ValueError("ضریب a نمی‌تواند صفر باشد (معادله درجه ۲ نیست).")

    delta = b**2 - 4 * a * c

    if delta >= 0:
        # ریشه‌های حقیقی
        sqrt_delta = math.sqrt(delta)
        x1 = (-b + sqrt_delta) / (2 * a)
        x2 = (-b - sqrt_delta) / (2 * a)
        return (x1, x2)
    else:
        # ریشه‌های موهومی (مختلط)
        real_part = -b / (2 * a)
        imag_part = math.sqrt(-delta) / (2 * a)
        x1 = complex(real_part, imag_part)
        x2 = complex(real_part, -imag_part)
        return (x1, x2)


def main():
    print("=== حل معادله درجه ۲ ===")
    print("فرم: a x^2 + b x + c = 0\n")

    try:
        a = float(input("لطفاً ضریب a را وارد کنید: "))
        b = float(input("لطفاً ضریب b را وارد کنید: "))
        c = float(input("لطفاً ضریب c را وارد کنید: "))

        x1, x2 = solve_quadratic(a, b, c)

        print("\nریشه‌های معادله:")
        print(f"x1 = {x1}")
        print(f"x2 = {x2}")

    except ValueError as e:
        print(f"\nخطا: {e}")
    except Exception as e:
        print(f"\nخطای غیرمنتظره: {e}")


if __name__ == "__main__":
    main()