"""
Seed LabTestCatalog with common lab tests and aliases.

Covers: CBC, CMP, Lipids, Thyroid, A1C, Urinalysis, CRP/ESR.
Each test gets a canonical entry + one or more aliases for import matching.
"""

import uuid
from django.db import migrations


def seed_catalog(apps, schema_editor):
    LabTestCatalog = apps.get_model("medical", "LabTestCatalog")
    LabTestAlias = apps.get_model("medical", "LabTestAlias")

    # Define tests: (name, short_name, category, unit, range_low, range_high, aliases)
    tests = [
        # CBC
        ("White Blood Cell Count", "WBC", "hematology", "x10^3/uL", "4.0", "11.0", 10,
         ["wbc", "white blood cell count", "white blood cells", "wbc count", "leukocyte count"]),
        ("Red Blood Cell Count", "RBC", "hematology", "x10^6/uL", "4.00", "5.50", 20,
         ["rbc", "red blood cell count", "red blood cells", "rbc count", "erythrocyte count"]),
        ("Hemoglobin", "Hgb", "hematology", "g/dL", "12.0", "16.0", 30,
         ["hemoglobin", "hgb", "hb"]),
        ("Hematocrit", "Hct", "hematology", "%" , "36.0", "46.0", 40,
         ["hematocrit", "hct"]),
        ("Mean Corpuscular Volume", "MCV", "hematology", "fL", "80.0", "100.0", 50,
         ["mcv", "mean corpuscular volume"]),
        ("Mean Corpuscular Hemoglobin", "MCH", "hematology", "pg", "27.0", "33.0", 60,
         ["mch", "mean corpuscular hemoglobin"]),
        ("Mean Corpuscular Hemoglobin Concentration", "MCHC", "hematology", "g/dL", "32.0", "36.0", 70,
         ["mchc", "mean corpuscular hemoglobin concentration"]),
        ("Red Cell Distribution Width", "RDW", "hematology", "%", "11.5", "14.5", 80,
         ["rdw", "red cell distribution width", "rdw-cv"]),
        ("Platelet Count", "PLT", "hematology", "x10^3/uL", "150", "400", 90,
         ["platelet count", "plt", "platelets", "thrombocyte count"]),
        ("Mean Platelet Volume", "MPV", "hematology", "fL", "7.5", "12.5", 100,
         ["mpv", "mean platelet volume"]),
        ("Neutrophils", "Neut", "hematology", "%", "40", "70", 110,
         ["neutrophils", "neutrophils %", "neut", "neut %", "neutrophil percentage"]),
        ("Lymphocytes", "Lymph", "hematology", "%", "20", "40", 120,
         ["lymphocytes", "lymphocytes %", "lymph", "lymph %", "lymphocyte percentage"]),
        ("Monocytes", "Mono", "hematology", "%", "2", "8", 130,
         ["monocytes", "monocytes %", "mono", "mono %"]),
        ("Eosinophils", "Eos", "hematology", "%", "1", "4", 140,
         ["eosinophils", "eosinophils %", "eos", "eos %"]),
        ("Basophils", "Baso", "hematology", "%", "0", "2", 150,
         ["basophils", "basophils %", "baso", "baso %"]),

        # CMP - Chemistry
        ("Glucose", "Glu", "chemistry", "mg/dL", "70", "99", 200,
         ["glucose", "glucose, serum", "fasting glucose", "blood glucose", "glucose fasting"]),
        ("Blood Urea Nitrogen", "BUN", "kidney", "mg/dL", "7", "25", 210,
         ["bun", "blood urea nitrogen", "urea nitrogen"]),
        ("Creatinine", "Creat", "kidney", "mg/dL", "0.60", "1.20", 220,
         ["creatinine", "creatinine, serum", "creat"]),
        ("Estimated Glomerular Filtration Rate", "eGFR", "kidney", "mL/min/1.73m2", "60", "", 230,
         ["egfr", "estimated glomerular filtration rate", "gfr", "egfr non-afr amer"]),
        ("BUN/Creatinine Ratio", "BUN/Cr", "kidney", "", "6", "22", 240,
         ["bun/creatinine ratio", "bun/cr ratio", "bun creatinine ratio"]),
        ("Sodium", "Na", "electrolytes", "mmol/L", "136", "145", 250,
         ["sodium", "na", "sodium, serum"]),
        ("Potassium", "K", "electrolytes", "mmol/L", "3.5", "5.1", 260,
         ["potassium", "k", "potassium, serum"]),
        ("Chloride", "Cl", "electrolytes", "mmol/L", "98", "107", 270,
         ["chloride", "cl", "chloride, serum"]),
        ("Carbon Dioxide", "CO2", "electrolytes", "mmol/L", "20", "29", 280,
         ["carbon dioxide", "co2", "carbon dioxide, total", "bicarbonate", "total co2"]),
        ("Calcium", "Ca", "chemistry", "mg/dL", "8.6", "10.2", 290,
         ["calcium", "ca", "calcium, serum", "total calcium"]),
        ("Total Protein", "TP", "chemistry", "g/dL", "6.0", "8.3", 300,
         ["total protein", "protein, total", "tp"]),
        ("Albumin", "Alb", "chemistry", "g/dL", "3.5", "5.0", 310,
         ["albumin", "albumin, serum", "alb"]),
        ("Globulin", "Glob", "chemistry", "g/dL", "2.0", "3.5", 320,
         ["globulin", "glob", "globulin, total"]),
        ("Albumin/Globulin Ratio", "A/G", "chemistry", "", "1.0", "2.5", 330,
         ["a/g ratio", "albumin/globulin ratio", "ag ratio"]),
        ("Bilirubin, Total", "TBili", "liver", "mg/dL", "0.2", "1.2", 340,
         ["bilirubin, total", "total bilirubin", "bilirubin total", "tbili"]),
        ("Alkaline Phosphatase", "ALP", "liver", "U/L", "44", "121", 350,
         ["alkaline phosphatase", "alp", "alk phos"]),
        ("AST", "AST", "liver", "U/L", "10", "40", 360,
         ["ast", "ast (sgot)", "sgot", "aspartate aminotransferase"]),
        ("ALT", "ALT", "liver", "U/L", "7", "56", 370,
         ["alt", "alt (sgpt)", "sgpt", "alanine aminotransferase"]),

        # Lipids
        ("Total Cholesterol", "TC", "lipids", "mg/dL", "", "200", 400,
         ["total cholesterol", "cholesterol, total", "cholesterol total", "cholesterol"]),
        ("Triglycerides", "TG", "lipids", "mg/dL", "", "150", 410,
         ["triglycerides", "tg", "triglyceride"]),
        ("HDL Cholesterol", "HDL", "lipids", "mg/dL", "40", "", 420,
         ["hdl cholesterol", "hdl", "hdl-c", "hdl cholesterol direct"]),
        ("LDL Cholesterol", "LDL", "lipids", "mg/dL", "", "100", 430,
         ["ldl cholesterol", "ldl cholesterol (calc)", "ldl", "ldl-c", "ldl calculated"]),
        ("VLDL Cholesterol", "VLDL", "lipids", "mg/dL", "5", "40", 440,
         ["vldl cholesterol", "vldl cholesterol (calc)", "vldl", "vldl calculated"]),
        ("Total Cholesterol/HDL Ratio", "TC/HDL", "lipids", "", "", "5.0", 450,
         ["total cholesterol/hdl ratio", "tc/hdl ratio", "cholesterol/hdl ratio", "chol/hdl ratio"]),
        ("Non-HDL Cholesterol", "Non-HDL", "lipids", "mg/dL", "", "130", 460,
         ["non-hdl cholesterol", "non hdl cholesterol"]),

        # Thyroid
        ("Thyroid Stimulating Hormone", "TSH", "thyroid", "mIU/L", "0.40", "4.50", 500,
         ["tsh", "thyroid stimulating hormone", "thyrotropin"]),
        ("Free T4", "FT4", "thyroid", "ng/dL", "0.82", "1.77", 510,
         ["free t4", "ft4", "free thyroxine", "t4 free"]),
        ("Free T3", "FT3", "thyroid", "pg/mL", "2.0", "4.4", 520,
         ["free t3", "ft3", "free triiodothyronine", "t3 free"]),

        # A1C / Diabetes
        ("Hemoglobin A1c", "HbA1c", "diabetes", "%", "", "5.7", 600,
         ["hemoglobin a1c", "hba1c", "a1c", "glycated hemoglobin", "glycosylated hemoglobin"]),
        ("Estimated Average Glucose", "eAG", "diabetes", "mg/dL", "", "", 610,
         ["estimated average glucose", "eag", "average glucose"]),

        # Urinalysis
        ("Urine Color", "", "urinalysis", "", "", "", 700,
         ["color", "urine color"]),
        ("Urine Appearance", "", "urinalysis", "", "", "", 710,
         ["appearance", "urine appearance"]),
        ("Specific Gravity", "SpGr", "urinalysis", "", "1.005", "1.030", 720,
         ["specific gravity", "sp gravity", "spgr", "sp. gravity"]),
        ("Urine pH", "", "urinalysis", "", "5.0", "8.0", 730,
         ["ph", "urine ph"]),
        ("Urine Protein", "", "urinalysis", "", "", "", 740,
         ["protein", "urine protein", "protein, urine"]),
        ("Urine Glucose", "", "urinalysis", "", "", "", 750,
         ["glucose, urine", "urine glucose", "glucose urine"]),
        ("Ketones", "", "urinalysis", "", "", "", 760,
         ["ketones", "urine ketones", "ketones, urine"]),
        ("Urine Blood", "", "urinalysis", "", "", "", 770,
         ["blood, urine", "urine blood", "blood urine", "occult blood"]),
        ("Leukocyte Esterase", "", "urinalysis", "", "", "", 780,
         ["leukocyte esterase", "leuk esterase"]),
        ("Nitrite", "", "urinalysis", "", "", "", 790,
         ["nitrite", "nitrites", "urine nitrite"]),

        # Inflammation
        ("C-Reactive Protein", "CRP", "inflammation", "mg/L", "", "3.0", 800,
         ["c-reactive protein", "crp", "c-reactive protein (crp)", "hs-crp", "high sensitivity crp"]),
        ("Erythrocyte Sedimentation Rate", "ESR", "inflammation", "mm/hr", "0", "20", 810,
         ["esr", "erythrocyte sedimentation rate", "esr (sed rate)", "sed rate", "sedimentation rate"]),
    ]

    for name, short_name, category, unit, r_low, r_high, sort_order, aliases in tests:
        test_id = uuid.uuid4()
        LabTestCatalog.objects.create(
            id=test_id,
            name=name,
            short_name=short_name,
            category=category,
            default_unit=unit,
            default_range_low=r_low,
            default_range_high=r_high,
            is_system_seeded=True,
            needs_review=False,
            sort_order=sort_order,
        )
        for alias_text in aliases:
            LabTestAlias.objects.create(
                id=uuid.uuid4(),
                alias=alias_text.strip().lower(),
                canonical_test_id=test_id,
            )


def reverse_seed(apps, schema_editor):
    LabTestCatalog = apps.get_model("medical", "LabTestCatalog")
    LabTestCatalog.objects.filter(is_system_seeded=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_catalog, reverse_seed),
    ]
