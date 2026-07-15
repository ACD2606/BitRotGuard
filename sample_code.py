# =====================================================
#  Sample Python Script — For BitRot Guard Demo
# =====================================================
#  This file demonstrates what happens when bit rot
#  corrupts source code. A single bit flip can change
#  a variable name, break syntax, or silently alter
#  a calculation's result.
# =====================================================

import math

def calculate_loan_emi(principal, annual_rate, tenure_months):
    """Calculate Equated Monthly Installment (EMI) for a loan.
    
    Formula: EMI = P * r * (1+r)^n / ((1+r)^n - 1)
    Where: P = principal, r = monthly rate, n = tenure in months
    """
    monthly_rate = annual_rate / (12 * 100)
    factor = (1 + monthly_rate) ** tenure_months
    emi = principal * monthly_rate * factor / (factor - 1)
    return round(emi, 2)

def fibonacci(n):
    """Generate first n Fibonacci numbers."""
    if n <= 0:
        return []
    seq = [0, 1]
    for i in range(2, n):
        seq.append(seq[i-1] + seq[i-2])
    return seq[:n]

def celsius_to_fahrenheit(celsius):
    """Convert temperature from Celsius to Fahrenheit."""
    return (celsius * 9/5) + 32

# === Main execution ===
if __name__ == "__main__":
    # Loan EMI calculation
    principal = 500000  # Rs 5,00,000
    rate = 8.5          # 8.5% annual
    tenure = 60         # 5 years

    emi = calculate_loan_emi(principal, rate, tenure)
    print(f"Loan EMI: Rs {emi:,.2f}")
    print(f"Total payable: Rs {emi * tenure:,.2f}")
    print(f"Total interest: Rs {emi * tenure - principal:,.2f}")

    # Fibonacci
    print(f"\nFirst 10 Fibonacci: {fibonacci(10)}")

    # Temperature conversion
    temps = [0, 25, 37, 100]
    for c in temps:
        print(f"  {c}°C = {celsius_to_fahrenheit(c):.1f}°F")
