#!/usr/bin/env python3
"""Generate realistic test documents with planted PII/PHI/PCI.

Creates a corpus of test documents across different categories:
- HR documents (employee records, benefits)
- Finance documents (invoices, payments)
- Medical documents (patient records, prescriptions)
- Clean documents (no sensitive data)
- Test/example documents (fake data that should be flagged)

Usage:
    python generate_test_corpus.py ./test_corpus --count 50
    
    # Or as module
    from scripts.generate_test_corpus import generate_corpus
    generate_corpus("./test_corpus", count=50)
"""

import argparse
import random
import string
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

# Try to use Faker for realistic data
try:
    from faker import Faker
    fake = Faker()
    HAS_FAKER = True
except ImportError:
    HAS_FAKER = False
    print("Warning: Faker not installed. Using basic random data.")
    print("Install with: pip install faker")


# =============================================================================
# Data Generators
# =============================================================================

def random_ssn(test_data: bool = False) -> str:
    """Generate random SSN."""
    if test_data:
        return random.choice([
            "123-45-6789",
            "000-00-0000",
            "111-11-1111",
            "999-99-9999",
        ])
    
    # Valid SSN format (not starting with 000, 666, 900-999)
    area = random.randint(1, 665) if random.random() > 0.5 else random.randint(667, 899)
    group = random.randint(1, 99)
    serial = random.randint(1, 9999)
    return f"{area:03d}-{group:02d}-{serial:04d}"


def random_credit_card(test_data: bool = False) -> str:
    """Generate random credit card (Luhn-valid)."""
    if test_data:
        return random.choice([
            "4111111111111111",
            "5500000000000004",
            "4242424242424242",
        ])
    
    # Generate Luhn-valid card
    prefix = random.choice(["4", "51", "52", "53", "54", "55", "34", "37"])
    length = 16 if prefix.startswith(("4", "5")) else 15
    
    # Generate random digits (excluding check digit)
    partial = prefix + "".join([str(random.randint(0, 9)) for _ in range(length - len(prefix) - 1)])
    
    # Calculate Luhn check digit
    # For check digit calculation, we process from right to left
    # and double every second digit (starting from the rightmost of the partial number)
    digits = [int(d) for d in partial]
    
    # Double every second digit from the right
    for i in range(len(digits) - 1, -1, -2):
        digits[i] *= 2
        if digits[i] > 9:
            digits[i] -= 9
    
    total = sum(digits)
    check_digit = (10 - (total % 10)) % 10
    
    return partial + str(check_digit)


def random_phone(test_data: bool = False) -> str:
    """Generate random phone number."""
    if test_data:
        return random.choice([
            "555-555-5555",
            "123-456-7890",
            "(555) 555-5555",
        ])
    
    area = random.randint(200, 999)
    exchange = random.randint(200, 999)
    subscriber = random.randint(1000, 9999)
    
    formats = [
        f"{area}-{exchange}-{subscriber}",
        f"({area}) {exchange}-{subscriber}",
        f"{area}.{exchange}.{subscriber}",
    ]
    return random.choice(formats)


def random_email(test_data: bool = False) -> str:
    """Generate random email."""
    if test_data:
        return random.choice([
            "test@example.com",
            "user@test.com",
            "noreply@example.org",
        ])
    
    if HAS_FAKER:
        return fake.email()
    
    name = "".join(random.choices(string.ascii_lowercase, k=8))
    domain = random.choice(["company.com", "corp.net", "business.org", "acme.io"])
    return f"{name}@{domain}"


def random_name() -> str:
    """Generate random person name."""
    if HAS_FAKER:
        return fake.name()
    
    first = random.choice(["John", "Jane", "Michael", "Sarah", "Robert", "Emily", "David", "Lisa"])
    last = random.choice(["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis"])
    return f"{first} {last}"


def random_address() -> str:
    """Generate random address."""
    if HAS_FAKER:
        return fake.address().replace("\n", ", ")
    
    number = random.randint(100, 9999)
    street = random.choice(["Main St", "Oak Ave", "Elm Street", "Park Blvd", "First Ave"])
    city = random.choice(["Springfield", "Riverside", "Clinton", "Madison", "Georgetown"])
    state = random.choice(["CA", "TX", "NY", "FL", "IL"])
    zip_code = random.randint(10000, 99999)
    return f"{number} {street}, {city}, {state} {zip_code}"


def random_mrn() -> str:
    """Generate random Medical Record Number."""
    return f"MRN{random.randint(10000000, 99999999)}"


def random_health_plan_id() -> str:
    """Generate random Health Plan ID."""
    prefix = random.choice(["HP", "HPI", "BCBS", "UHC", "AETNA"])
    return f"{prefix}{random.randint(1000000000, 9999999999)}"


def random_date(start_year: int = 1950, end_year: int = 2005) -> str:
    """Generate random date."""
    if HAS_FAKER:
        return fake.date_of_birth(minimum_age=18, maximum_age=80).strftime("%m/%d/%Y")
    
    year = random.randint(start_year, end_year)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return f"{month:02d}/{day:02d}/{year}"


# =============================================================================
# Document Templates
# =============================================================================

HR_TEMPLATES = [
    """EMPLOYEE RECORD

Name: {name}
Employee ID: EMP{emp_id}
Social Security Number: {ssn}
Date of Birth: {dob}
Phone: {phone}
Email: {email}
Address: {address}

Department: {department}
Start Date: {start_date}
Salary: ${salary:,}

Emergency Contact: {emergency_name}
Emergency Phone: {emergency_phone}
""",

    """BENEFITS ENROLLMENT FORM

Employee: {name}
SSN: {ssn}
DOB: {dob}

Health Plan Selection:
[X] Premium PPO - Employee + Family
Health Plan ID: {health_plan_id}

Beneficiary Information:
Name: {beneficiary_name}
Relationship: Spouse
SSN: {beneficiary_ssn}

Direct Deposit:
Bank Account: {account_number}
Routing: {routing_number}
""",

    """TERMINATION NOTICE

Date: {date}

Employee: {name}
SSN: {ssn}
Employee ID: EMP{emp_id}

Last Day of Employment: {end_date}
Reason: {termination_reason}

Final Paycheck Amount: ${final_pay:,.2f}
Accrued PTO Payout: ${pto_payout:,.2f}

COBRA Information will be sent to:
{address}

HR Representative: {hr_name}
""",
]

FINANCE_TEMPLATES = [
    """INVOICE

Invoice #: INV-{invoice_num}
Date: {date}

Bill To:
{name}
{address}

Payment Information:
Credit Card: {credit_card}
Expiration: {exp_date}

Items:
{items}

Subtotal: ${subtotal:,.2f}
Tax: ${tax:,.2f}
Total: ${total:,.2f}

Thank you for your business!
""",

    """PAYMENT RECEIPT

Transaction ID: TXN{txn_id}
Date: {date}

Customer: {name}
Email: {email}
Phone: {phone}

Payment Method: Credit Card ending in {card_last4}
Amount: ${amount:,.2f}

Billing Address:
{address}

For questions, contact billing@company.com
""",

    """WIRE TRANSFER CONFIRMATION

Transfer Reference: WT{ref_num}
Date: {date}

From Account: {from_account}
Routing Number: {routing_number}

To: {name}
Account: {to_account}
Amount: ${amount:,.2f}

Memo: {memo}

This transfer has been processed successfully.
""",
]

MEDICAL_TEMPLATES = [
    """PATIENT RECORD

Patient: {name}
MRN: {mrn}
DOB: {dob}
SSN: {ssn}

Address: {address}
Phone: {phone}
Email: {email}

Insurance:
Health Plan ID: {health_plan_id}
Group Number: GRP{group_num}

Primary Care Physician: Dr. {doctor_name}

Allergies: {allergies}

Current Medications:
{medications}

Medical History:
{medical_history}
""",

    """PRESCRIPTION

Date: {date}

Patient: {name}
DOB: {dob}
MRN: {mrn}

Rx: {medication}
Dosage: {dosage}
Quantity: {quantity}
Refills: {refills}

Diagnosis: {diagnosis}
ICD-10: {icd_code}

Prescriber: Dr. {doctor_name}
DEA#: {dea_number}
NPI: {npi}

Pharmacy: {pharmacy_name}
Phone: {pharmacy_phone}
""",

    """LAB RESULTS

Patient: {name}
MRN: {mrn}
DOB: {dob}

Collection Date: {collection_date}
Report Date: {report_date}

Ordering Physician: Dr. {doctor_name}

Test Results:
{lab_results}

Interpretation: {interpretation}

Health Plan ID: {health_plan_id}
Authorization #: AUTH{auth_num}
""",
]

CLEAN_TEMPLATES = [
    """COMPANY NEWSLETTER

Volume {vol}, Issue {issue}
{date}

HEADLINES

{headline1}
Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod 
tempor incididunt ut labore et dolore magna aliqua.

{headline2}
Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi 
ut aliquip ex ea commodo consequat.

UPCOMING EVENTS
- Team Building: {event_date1}
- Holiday Party: {event_date2}
- Training Session: {event_date3}

Have a great month!
""",

    """MEETING NOTES

Date: {date}
Attendees: {attendees}

Agenda:
1. Project status update
2. Budget review
3. Timeline discussion
4. Action items

Discussion:
{discussion}

Action Items:
{action_items}

Next Meeting: {next_meeting}
""",

    """PROJECT PROPOSAL

Title: {project_title}
Date: {date}
Author: {author}

Executive Summary:
{summary}

Objectives:
{objectives}

Timeline:
Phase 1: {phase1_dates}
Phase 2: {phase2_dates}
Phase 3: {phase3_dates}

Budget Estimate: ${budget:,}

Approval Required By: {approval_date}
""",
]

TEST_DATA_TEMPLATES = [
    """TEST DOCUMENT - DO NOT USE IN PRODUCTION

Sample SSN: 123-45-6789
Test Credit Card: 4111111111111111
Example Phone: 555-555-5555
Test Email: test@example.com

This document contains test data for validation purposes only.
""",

    """QA VALIDATION DATA

The following are SAMPLE values for testing:

SSN Examples:
- 000-00-0000 (invalid)
- 123-45-6789 (test)
- 111-11-1111 (test)

Credit Card Examples:
- 4242424242424242 (Stripe test)
- 5500000000000004 (test Mastercard)

DO NOT USE REAL DATA IN THIS DOCUMENT
""",

    """DEVELOPER NOTES

For testing, use these fake credentials:
- SSN: 123-45-6789
- Card: 4111-1111-1111-1111
- Phone: (555) 555-5555
- Email: user@test.com

Remember: Never commit real PII to version control!
""",
]


# =============================================================================
# Document Generation
# =============================================================================

def fill_hr_template(template: str) -> str:
    """Fill an HR template with random data."""
    return template.format(
        name=random_name(),
        emp_id=random.randint(10000, 99999),
        ssn=random_ssn(),
        dob=random_date(1960, 2000),
        phone=random_phone(),
        email=random_email(),
        address=random_address(),
        department=random.choice(["Engineering", "Sales", "Marketing", "HR", "Finance", "Operations"]),
        start_date=random_date(2015, 2023),
        salary=random.randint(50000, 200000),
        emergency_name=random_name(),
        emergency_phone=random_phone(),
        health_plan_id=random_health_plan_id(),
        beneficiary_name=random_name(),
        beneficiary_ssn=random_ssn(),
        account_number=random.randint(100000000, 999999999),
        routing_number=random.randint(100000000, 999999999),
        date=datetime.now().strftime("%m/%d/%Y"),
        end_date=(datetime.now() + timedelta(days=14)).strftime("%m/%d/%Y"),
        termination_reason=random.choice(["Resignation", "Position Elimination", "Retirement"]),
        final_pay=random.uniform(2000, 10000),
        pto_payout=random.uniform(500, 3000),
        hr_name=random_name(),
    )


def fill_finance_template(template: str) -> str:
    """Fill a finance template with random data."""
    subtotal = random.uniform(100, 5000)
    tax = subtotal * 0.08
    
    items = "\n".join([
        f"  - {random.choice(['Product', 'Service', 'Subscription'])} {i+1}: ${random.uniform(50, 500):,.2f}"
        for i in range(random.randint(2, 5))
    ])
    
    return template.format(
        invoice_num=random.randint(10000, 99999),
        date=datetime.now().strftime("%m/%d/%Y"),
        name=random_name(),
        address=random_address(),
        credit_card=random_credit_card(),
        exp_date=f"{random.randint(1,12):02d}/{random.randint(25, 29)}",
        items=items,
        subtotal=subtotal,
        tax=tax,
        total=subtotal + tax,
        txn_id=random.randint(100000000, 999999999),
        email=random_email(),
        phone=random_phone(),
        card_last4=str(random.randint(1000, 9999)),
        amount=random.uniform(50, 2000),
        ref_num=random.randint(100000000, 999999999),
        from_account=str(random.randint(100000000, 999999999)),
        routing_number=str(random.randint(100000000, 999999999)),
        to_account=str(random.randint(100000000, 999999999)),
        memo=random.choice(["Invoice Payment", "Services Rendered", "Consulting Fee"]),
    )


def fill_medical_template(template: str) -> str:
    """Fill a medical template with random data."""
    medications = "\n".join([
        f"  - {random.choice(['Lisinopril', 'Metformin', 'Atorvastatin', 'Amlodipine', 'Omeprazole'])} {random.choice(['10mg', '20mg', '40mg'])} {random.choice(['daily', 'twice daily'])}"
        for _ in range(random.randint(1, 4))
    ])
    
    lab_results = "\n".join([
        f"  {test}: {value} {unit} ({status})"
        for test, value, unit, status in [
            ("Glucose", random.randint(70, 120), "mg/dL", "Normal"),
            ("Cholesterol", random.randint(150, 250), "mg/dL", random.choice(["Normal", "High"])),
            ("Blood Pressure", f"{random.randint(110, 140)}/{random.randint(70, 90)}", "mmHg", "Normal"),
        ]
    ])
    
    return template.format(
        name=random_name(),
        mrn=random_mrn(),
        dob=random_date(1940, 2000),
        ssn=random_ssn(),
        address=random_address(),
        phone=random_phone(),
        email=random_email(),
        health_plan_id=random_health_plan_id(),
        group_num=random.randint(100000, 999999),
        doctor_name=random_name().split()[1],  # Last name
        allergies=random.choice(["None known", "Penicillin", "Sulfa drugs", "Latex"]),
        medications=medications,
        medical_history=random.choice(["Hypertension", "Type 2 Diabetes", "Hyperlipidemia", "No significant history"]),
        date=datetime.now().strftime("%m/%d/%Y"),
        medication=random.choice(["Lisinopril", "Metformin", "Atorvastatin", "Amlodipine"]),
        dosage=random.choice(["10mg", "20mg", "40mg", "500mg"]),
        quantity=random.choice(["30", "60", "90"]),
        refills=random.randint(0, 5),
        diagnosis=random.choice(["Essential hypertension", "Type 2 diabetes mellitus", "Hyperlipidemia"]),
        icd_code=random.choice(["I10", "E11.9", "E78.5", "J06.9"]),
        dea_number=f"A{random.randint(1000000, 9999999)}",
        npi=str(random.randint(1000000000, 9999999999)),
        pharmacy_name=random.choice(["CVS Pharmacy", "Walgreens", "Rite Aid", "Walmart Pharmacy"]),
        pharmacy_phone=random_phone(),
        collection_date=(datetime.now() - timedelta(days=3)).strftime("%m/%d/%Y"),
        report_date=datetime.now().strftime("%m/%d/%Y"),
        lab_results=lab_results,
        interpretation=random.choice(["Results within normal limits", "Some values elevated, follow-up recommended"]),
        auth_num=random.randint(100000000, 999999999),
    )


def fill_clean_template(template: str) -> str:
    """Fill a clean template with non-sensitive data."""
    return template.format(
        vol=random.randint(1, 20),
        issue=random.randint(1, 12),
        date=datetime.now().strftime("%B %Y"),
        headline1=random.choice(["New Product Launch Success", "Q3 Results Exceed Expectations", "Team Expansion Announced"]),
        headline2=random.choice(["Sustainability Initiative", "Customer Satisfaction Survey", "Office Renovation Complete"]),
        event_date1=(datetime.now() + timedelta(days=random.randint(7, 30))).strftime("%B %d"),
        event_date2=(datetime.now() + timedelta(days=random.randint(30, 60))).strftime("%B %d"),
        event_date3=(datetime.now() + timedelta(days=random.randint(14, 45))).strftime("%B %d"),
        attendees="Team Lead, Project Manager, Developer, Designer",
        discussion="Discussed project timeline, identified blockers, reviewed resource allocation.",
        action_items="- Complete design mockups by Friday\n- Schedule stakeholder review\n- Update project documentation",
        next_meeting=(datetime.now() + timedelta(days=7)).strftime("%B %d, %Y"),
        project_title=random.choice(["Digital Transformation", "Process Automation", "Customer Portal Upgrade"]),
        author=random_name(),
        summary="This proposal outlines a strategic initiative to improve operational efficiency and customer satisfaction.",
        objectives="- Increase efficiency by 20%\n- Reduce manual processes\n- Improve customer experience",
        phase1_dates="Q1 2024",
        phase2_dates="Q2 2024",
        phase3_dates="Q3 2024",
        budget=random.randint(50000, 500000),
        approval_date=(datetime.now() + timedelta(days=14)).strftime("%B %d, %Y"),
    )


# =============================================================================
# Corpus Generation
# =============================================================================

def generate_corpus(
    output_dir: str,
    count: int = 50,
    include_test_data: bool = True,
) -> dict:
    """
    Generate a test corpus with various document types.
    
    Args:
        output_dir: Directory to create documents in
        count: Total number of documents to create
        include_test_data: Include documents with obvious test data
    
    Returns:
        Statistics about generated documents
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Create subdirectories
    (output_path / "hr").mkdir(exist_ok=True)
    (output_path / "finance").mkdir(exist_ok=True)
    (output_path / "medical").mkdir(exist_ok=True)
    (output_path / "general").mkdir(exist_ok=True)
    if include_test_data:
        (output_path / "test_data").mkdir(exist_ok=True)
    
    stats = {
        "total": 0,
        "hr": 0,
        "finance": 0,
        "medical": 0,
        "clean": 0,
        "test_data": 0,
        "entities_planted": {
            "ssn": 0,
            "credit_card": 0,
            "phone": 0,
            "email": 0,
            "name": 0,
            "address": 0,
            "mrn": 0,
            "health_plan_id": 0,
        },
    }
    
    # Distribution: 25% HR, 25% Finance, 25% Medical, 15% Clean, 10% Test
    hr_count = int(count * 0.25)
    finance_count = int(count * 0.25)
    medical_count = int(count * 0.25)
    clean_count = int(count * 0.15)
    test_count = count - hr_count - finance_count - medical_count - clean_count
    
    # Generate HR documents
    for i in range(hr_count):
        template = random.choice(HR_TEMPLATES)
        content = fill_hr_template(template)
        filename = f"hr/employee_record_{i+1:03d}.txt"
        (output_path / filename).write_text(content)
        stats["hr"] += 1
        stats["total"] += 1
        stats["entities_planted"]["ssn"] += content.count("-") // 2  # Rough estimate
        stats["entities_planted"]["phone"] += 1
        stats["entities_planted"]["email"] += 1
    
    # Generate Finance documents
    for i in range(finance_count):
        template = random.choice(FINANCE_TEMPLATES)
        content = fill_finance_template(template)
        filename = f"finance/financial_doc_{i+1:03d}.txt"
        (output_path / filename).write_text(content)
        stats["finance"] += 1
        stats["total"] += 1
        stats["entities_planted"]["credit_card"] += 1
    
    # Generate Medical documents
    for i in range(medical_count):
        template = random.choice(MEDICAL_TEMPLATES)
        content = fill_medical_template(template)
        filename = f"medical/patient_record_{i+1:03d}.txt"
        (output_path / filename).write_text(content)
        stats["medical"] += 1
        stats["total"] += 1
        stats["entities_planted"]["ssn"] += 1
        stats["entities_planted"]["mrn"] += 1
        stats["entities_planted"]["health_plan_id"] += 1
    
    # Generate Clean documents
    for i in range(clean_count):
        template = random.choice(CLEAN_TEMPLATES)
        content = fill_clean_template(template)
        filename = f"general/document_{i+1:03d}.txt"
        (output_path / filename).write_text(content)
        stats["clean"] += 1
        stats["total"] += 1
    
    # Generate Test Data documents
    if include_test_data:
        for i, template in enumerate(TEST_DATA_TEMPLATES):
            filename = f"test_data/test_doc_{i+1:03d}.txt"
            (output_path / filename).write_text(template)
            stats["test_data"] += 1
            stats["total"] += 1
    
    # Create manifest
    manifest = {
        "generated_at": datetime.now().isoformat(),
        "stats": stats,
        "categories": {
            "hr": "Employee records, benefits forms - contains SSN, DOB, addresses",
            "finance": "Invoices, payments - contains credit cards, account numbers",
            "medical": "Patient records, prescriptions - contains PHI (MRN, health plan ID, diagnoses)",
            "general": "Clean documents - no sensitive data",
            "test_data": "Documents with obvious test/fake data that should be flagged",
        },
    }
    
    import json
    (output_path / "manifest.json").write_text(json.dumps(manifest, indent=2))
    
    return stats


def main():
    parser = argparse.ArgumentParser(description="Generate test corpus for scrubIQ")
    parser.add_argument("output_dir", help="Directory to create test documents")
    parser.add_argument("--count", "-n", type=int, default=50, help="Number of documents to generate")
    parser.add_argument("--no-test-data", action="store_true", help="Don't include test data documents")
    
    args = parser.parse_args()
    
    print(f"Generating {args.count} test documents in {args.output_dir}...")
    
    stats = generate_corpus(
        args.output_dir,
        count=args.count,
        include_test_data=not args.no_test_data,
    )
    
    print(f"\nGenerated {stats['total']} documents:")
    print(f"  HR:        {stats['hr']}")
    print(f"  Finance:   {stats['finance']}")
    print(f"  Medical:   {stats['medical']}")
    print(f"  Clean:     {stats['clean']}")
    print(f"  Test Data: {stats['test_data']}")
    
    print(f"\nEntities planted:")
    for entity, count in stats['entities_planted'].items():
        if count > 0:
            print(f"  {entity}: ~{count}")
    
    print(f"\nManifest written to {args.output_dir}/manifest.json")


if __name__ == "__main__":
    main()
