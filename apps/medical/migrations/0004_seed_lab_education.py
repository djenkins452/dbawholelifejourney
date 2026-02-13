"""
Seed LabEducationContent for all system-seeded lab tests.

Educational content only — no medical advice, diagnosis, or personal recommendations.
All content uses neutral, plain-language phrasing:
  - "Low levels are commonly associated with..."
  - "High levels may be seen in..."
  - "Factors that can influence this test include..."
"""

import uuid
from django.db import migrations


# Education data keyed by LabTestCatalog.name (must match seed_lab_catalog exactly)
EDUCATION_DATA = {
    # =========================================================================
    # CBC (Hematology)
    # =========================================================================
    "White Blood Cell Count": {
        "summary_plain_name": "White Blood Cell Count (WBC)",
        "what_it_measures": (
            "This test measures the total number of white blood cells (leukocytes) "
            "in a sample of blood. White blood cells are part of the immune system."
        ),
        "what_it_reflects": (
            "The white blood cell count reflects the body's current immune activity. "
            "It provides a general picture of whether the immune system is responding "
            "to something such as infection, inflammation, or stress."
        ),
        "low_general_associations": (
            "Low levels are commonly associated with certain viral infections, "
            "bone marrow conditions, autoimmune disorders, and some medications "
            "that suppress immune function."
        ),
        "high_general_associations": (
            "High levels may be seen in bacterial infections, inflammatory conditions, "
            "physical or emotional stress, allergic reactions, and certain blood disorders."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include recent illness, physical stress, "
            "smoking, medications (especially steroids or chemotherapy), pregnancy, "
            "and time of day the sample was drawn."
        ),
        "typical_panel": "Complete Blood Count (CBC)",
    },
    "Red Blood Cell Count": {
        "summary_plain_name": "Red Blood Cell Count (RBC)",
        "what_it_measures": (
            "This test measures the number of red blood cells (erythrocytes) in a blood sample. "
            "Red blood cells carry oxygen from the lungs to the rest of the body."
        ),
        "what_it_reflects": (
            "The red blood cell count reflects the blood's oxygen-carrying capacity. "
            "It provides information about how effectively the body is producing and "
            "maintaining red blood cells."
        ),
        "low_general_associations": (
            "Low levels are commonly associated with various types of anemia, blood loss, "
            "nutritional deficiencies (iron, vitamin B12, folate), chronic kidney disease, "
            "and bone marrow conditions."
        ),
        "high_general_associations": (
            "High levels may be seen in dehydration, chronic lung disease, living at high altitude, "
            "heart conditions, and certain bone marrow disorders."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include hydration status, altitude, "
            "smoking, pregnancy, recent blood loss, and certain medications."
        ),
        "typical_panel": "Complete Blood Count (CBC)",
    },
    "Hemoglobin": {
        "summary_plain_name": "Hemoglobin (Hgb)",
        "what_it_measures": (
            "This test measures the amount of hemoglobin protein in the blood. "
            "Hemoglobin is the protein inside red blood cells that binds to oxygen "
            "and carries it throughout the body."
        ),
        "what_it_reflects": (
            "Hemoglobin reflects the blood's ability to transport oxygen. "
            "It is one of the primary indicators used to evaluate for anemia "
            "or other conditions affecting red blood cell function."
        ),
        "low_general_associations": (
            "Low levels are commonly associated with iron deficiency anemia, "
            "vitamin B12 or folate deficiency, chronic disease, blood loss, "
            "and bone marrow disorders."
        ),
        "high_general_associations": (
            "High levels may be seen in dehydration, chronic lung disease, "
            "living at high altitude, polycythemia, and heavy smoking."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include hydration, altitude, "
            "smoking, pregnancy, recent blood donation, and iron intake."
        ),
        "typical_panel": "Complete Blood Count (CBC)",
    },
    "Hematocrit": {
        "summary_plain_name": "Hematocrit (Hct)",
        "what_it_measures": (
            "This test measures the percentage of blood volume that is made up of red blood cells. "
            "It is expressed as a percentage."
        ),
        "what_it_reflects": (
            "Hematocrit reflects the proportion of red blood cells relative to total blood volume. "
            "It helps evaluate the blood's capacity to deliver oxygen and is often used "
            "alongside hemoglobin to assess for anemia or dehydration."
        ),
        "low_general_associations": (
            "Low levels are commonly associated with anemia, blood loss, "
            "nutritional deficiencies, overhydration, and chronic disease."
        ),
        "high_general_associations": (
            "High levels may be seen in dehydration, chronic lung disease, "
            "heart conditions, polycythemia, and high-altitude living."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include hydration status, altitude, "
            "pregnancy, recent blood loss, and certain medications."
        ),
        "typical_panel": "Complete Blood Count (CBC)",
    },
    "Mean Corpuscular Volume": {
        "summary_plain_name": "Mean Corpuscular Volume (MCV)",
        "what_it_measures": (
            "This test measures the average size of red blood cells. "
            "It is expressed in femtoliters (fL)."
        ),
        "what_it_reflects": (
            "MCV reflects the average volume of individual red blood cells. "
            "The size of red blood cells can provide clues about the underlying "
            "cause when anemia or other blood conditions are present."
        ),
        "low_general_associations": (
            "Low levels (small red blood cells, or microcytosis) are commonly associated "
            "with iron deficiency, thalassemia trait, chronic disease, and lead exposure."
        ),
        "high_general_associations": (
            "High levels (large red blood cells, or macrocytosis) may be seen in "
            "vitamin B12 deficiency, folate deficiency, liver disease, "
            "hypothyroidism, and alcohol use."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include nutritional status "
            "(iron, B12, folate), alcohol consumption, certain medications, "
            "and thyroid function."
        ),
        "typical_panel": "Complete Blood Count (CBC)",
    },
    "Mean Corpuscular Hemoglobin": {
        "summary_plain_name": "Mean Corpuscular Hemoglobin (MCH)",
        "what_it_measures": (
            "This test measures the average amount of hemoglobin per red blood cell. "
            "It is expressed in picograms (pg)."
        ),
        "what_it_reflects": (
            "MCH reflects how much oxygen-carrying hemoglobin is present in each "
            "red blood cell on average. It is closely related to MCV and provides "
            "similar information about red blood cell characteristics."
        ),
        "low_general_associations": (
            "Low levels are commonly associated with iron deficiency anemia "
            "and thalassemia trait."
        ),
        "high_general_associations": (
            "High levels may be seen in macrocytic anemias, such as those caused "
            "by vitamin B12 or folate deficiency."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include iron status, B12 and folate levels, "
            "and conditions that affect red blood cell production."
        ),
        "typical_panel": "Complete Blood Count (CBC)",
    },
    "Mean Corpuscular Hemoglobin Concentration": {
        "summary_plain_name": "Mean Corpuscular Hemoglobin Concentration (MCHC)",
        "what_it_measures": (
            "This test measures the average concentration of hemoglobin within red blood cells. "
            "It is expressed in grams per deciliter (g/dL)."
        ),
        "what_it_reflects": (
            "MCHC reflects how densely packed hemoglobin is within each red blood cell. "
            "It helps characterize different types of anemia based on hemoglobin concentration."
        ),
        "low_general_associations": (
            "Low levels are commonly associated with iron deficiency anemia "
            "and thalassemia, where cells are pale (hypochromic)."
        ),
        "high_general_associations": (
            "High levels may be seen in hereditary spherocytosis, severe dehydration, "
            "and certain hemolytic anemias."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include iron status, hydration, "
            "and inherited red blood cell conditions."
        ),
        "typical_panel": "Complete Blood Count (CBC)",
    },
    "Red Cell Distribution Width": {
        "summary_plain_name": "Red Cell Distribution Width (RDW)",
        "what_it_measures": (
            "This test measures the variation in size among red blood cells. "
            "It is expressed as a percentage."
        ),
        "what_it_reflects": (
            "RDW reflects how uniform or varied red blood cells are in size. "
            "A higher value means there is more variation, which can indicate "
            "the body is producing red blood cells of different sizes."
        ),
        "low_general_associations": (
            "Low levels generally indicate uniform red blood cell size, "
            "which is typically considered normal."
        ),
        "high_general_associations": (
            "High levels may be seen in iron deficiency, vitamin B12 or folate deficiency, "
            "mixed anemias, recent blood transfusion, and chronic liver disease."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include nutritional deficiencies, "
            "recent blood transfusions, and chronic illness."
        ),
        "typical_panel": "Complete Blood Count (CBC)",
    },
    "Platelet Count": {
        "summary_plain_name": "Platelet Count (PLT)",
        "what_it_measures": (
            "This test measures the number of platelets (thrombocytes) in a blood sample. "
            "Platelets are cell fragments that help blood clot."
        ),
        "what_it_reflects": (
            "The platelet count reflects the body's clotting ability and bone marrow function. "
            "Platelets play a key role in stopping bleeding by forming clots."
        ),
        "low_general_associations": (
            "Low levels (thrombocytopenia) are commonly associated with viral infections, "
            "certain medications, autoimmune conditions, liver disease, "
            "and bone marrow disorders."
        ),
        "high_general_associations": (
            "High levels (thrombocytosis) may be seen in iron deficiency, "
            "inflammatory conditions, infections, post-surgery recovery, "
            "and certain blood disorders."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include recent illness, surgery, "
            "medications (such as blood thinners), alcohol consumption, and pregnancy."
        ),
        "typical_panel": "Complete Blood Count (CBC)",
    },
    "Mean Platelet Volume": {
        "summary_plain_name": "Mean Platelet Volume (MPV)",
        "what_it_measures": (
            "This test measures the average size of platelets in the blood. "
            "It is expressed in femtoliters (fL)."
        ),
        "what_it_reflects": (
            "MPV reflects the average size and age of platelets. Younger platelets "
            "tend to be larger, so MPV can provide information about platelet "
            "production in the bone marrow."
        ),
        "low_general_associations": (
            "Low levels are commonly associated with conditions that suppress "
            "bone marrow production, such as certain medications or aplastic anemia."
        ),
        "high_general_associations": (
            "High levels may be seen when the body is actively producing new platelets, "
            "such as after blood loss, during recovery from infection, "
            "or in inflammatory conditions."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include the age of the blood sample "
            "(platelets swell over time in EDTA tubes), medications, and bone marrow activity."
        ),
        "typical_panel": "Complete Blood Count (CBC)",
    },
    "Neutrophils": {
        "summary_plain_name": "Neutrophils",
        "what_it_measures": (
            "This test measures the percentage of neutrophils among white blood cells. "
            "Neutrophils are the most abundant type of white blood cell."
        ),
        "what_it_reflects": (
            "Neutrophils are a first-line defense against bacterial infections. "
            "Their percentage reflects the body's response to infection or inflammation."
        ),
        "low_general_associations": (
            "Low levels (neutropenia) are commonly associated with certain viral infections, "
            "autoimmune conditions, bone marrow suppression, and some medications."
        ),
        "high_general_associations": (
            "High levels (neutrophilia) may be seen in bacterial infections, "
            "physical stress, inflammation, smoking, and steroid use."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include infection, stress, "
            "medications (especially steroids and chemotherapy), smoking, and exercise."
        ),
        "typical_panel": "Complete Blood Count (CBC) with Differential",
    },
    "Lymphocytes": {
        "summary_plain_name": "Lymphocytes",
        "what_it_measures": (
            "This test measures the percentage of lymphocytes among white blood cells. "
            "Lymphocytes include T cells, B cells, and natural killer cells."
        ),
        "what_it_reflects": (
            "Lymphocytes are key players in the adaptive immune response. "
            "They are important for fighting viral infections and producing antibodies."
        ),
        "low_general_associations": (
            "Low levels (lymphopenia) are commonly associated with certain viral infections "
            "(including HIV), autoimmune conditions, steroid use, and stress."
        ),
        "high_general_associations": (
            "High levels (lymphocytosis) may be seen in viral infections, "
            "chronic infections, and certain blood disorders."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include acute illness, stress, "
            "medications, and chronic infections."
        ),
        "typical_panel": "Complete Blood Count (CBC) with Differential",
    },
    "Monocytes": {
        "summary_plain_name": "Monocytes",
        "what_it_measures": (
            "This test measures the percentage of monocytes among white blood cells. "
            "Monocytes are the largest type of white blood cell."
        ),
        "what_it_reflects": (
            "Monocytes help the body fight certain infections and assist in removing "
            "dead or damaged cells. They can develop into macrophages in tissues."
        ),
        "low_general_associations": (
            "Low levels are uncommon and may be seen with certain bone marrow conditions "
            "or overwhelming infections."
        ),
        "high_general_associations": (
            "High levels (monocytosis) may be seen in chronic infections, "
            "autoimmune disorders, certain blood disorders, and recovery from acute infections."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include chronic infection, "
            "inflammatory conditions, and recovery from acute illness."
        ),
        "typical_panel": "Complete Blood Count (CBC) with Differential",
    },
    "Eosinophils": {
        "summary_plain_name": "Eosinophils",
        "what_it_measures": (
            "This test measures the percentage of eosinophils among white blood cells."
        ),
        "what_it_reflects": (
            "Eosinophils are involved in the body's response to allergic reactions "
            "and parasitic infections. They also play a role in inflammation."
        ),
        "low_general_associations": (
            "Low levels are generally not clinically significant on their own. "
            "They may be seen during acute stress or with steroid use."
        ),
        "high_general_associations": (
            "High levels (eosinophilia) may be seen in allergic conditions (asthma, hay fever), "
            "parasitic infections, skin disorders, and certain autoimmune conditions."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include allergies, parasitic exposure, "
            "medications, and steroid use."
        ),
        "typical_panel": "Complete Blood Count (CBC) with Differential",
    },
    "Basophils": {
        "summary_plain_name": "Basophils",
        "what_it_measures": (
            "This test measures the percentage of basophils among white blood cells. "
            "Basophils are the least common type of white blood cell."
        ),
        "what_it_reflects": (
            "Basophils are involved in allergic and inflammatory responses. "
            "They release histamine and other chemicals during these reactions."
        ),
        "low_general_associations": (
            "Low levels are common and generally not clinically significant, "
            "as basophils normally make up a very small percentage of white blood cells."
        ),
        "high_general_associations": (
            "High levels (basophilia) may be seen in allergic reactions, "
            "certain blood disorders, hypothyroidism, and chronic inflammation."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include allergic conditions, "
            "thyroid function, and certain medications."
        ),
        "typical_panel": "Complete Blood Count (CBC) with Differential",
    },

    # =========================================================================
    # CMP - Chemistry / Kidney / Electrolytes / Liver
    # =========================================================================
    "Glucose": {
        "summary_plain_name": "Glucose (Blood Sugar)",
        "what_it_measures": (
            "This test measures the amount of glucose (sugar) in the blood. "
            "Glucose is the body's primary source of energy."
        ),
        "what_it_reflects": (
            "Blood glucose reflects how the body is managing blood sugar levels. "
            "It is influenced by food intake, insulin production, and how cells "
            "absorb and use glucose."
        ),
        "low_general_associations": (
            "Low levels (hypoglycemia) are commonly associated with fasting, "
            "excessive insulin, certain medications, liver disease, "
            "and adrenal insufficiency."
        ),
        "high_general_associations": (
            "High levels (hyperglycemia) may be seen in diabetes, prediabetes, "
            "stress, certain medications (especially steroids), pancreatitis, "
            "and Cushing syndrome."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include fasting status, "
            "recent food intake, physical activity, stress, medications, "
            "and time of day."
        ),
        "typical_panel": "Comprehensive Metabolic Panel (CMP), Basic Metabolic Panel (BMP)",
    },
    "Blood Urea Nitrogen": {
        "summary_plain_name": "Blood Urea Nitrogen (BUN)",
        "what_it_measures": (
            "This test measures the amount of urea nitrogen in the blood. "
            "Urea is a waste product formed in the liver when protein is broken down."
        ),
        "what_it_reflects": (
            "BUN reflects how well the kidneys are filtering waste from the blood. "
            "It is also influenced by liver function and protein intake."
        ),
        "low_general_associations": (
            "Low levels are commonly associated with low-protein diets, "
            "severe liver disease, overhydration, and malnutrition."
        ),
        "high_general_associations": (
            "High levels may be seen in kidney dysfunction, dehydration, "
            "high-protein diets, gastrointestinal bleeding, heart failure, "
            "and certain medications."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include hydration status, "
            "protein intake, medications, kidney function, and age."
        ),
        "typical_panel": "Comprehensive Metabolic Panel (CMP), Basic Metabolic Panel (BMP)",
    },
    "Creatinine": {
        "summary_plain_name": "Creatinine",
        "what_it_measures": (
            "This test measures the amount of creatinine in the blood. "
            "Creatinine is a waste product produced by muscles during normal activity."
        ),
        "what_it_reflects": (
            "Creatinine levels reflect kidney filtration function. The kidneys normally "
            "filter creatinine out of the blood at a fairly constant rate."
        ),
        "low_general_associations": (
            "Low levels are commonly associated with low muscle mass, "
            "advanced age, and certain liver conditions."
        ),
        "high_general_associations": (
            "High levels may be seen in reduced kidney function, dehydration, "
            "high muscle mass, high-protein diets, and certain medications."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include muscle mass, age, sex, "
            "hydration status, protein intake, and certain medications."
        ),
        "typical_panel": "Comprehensive Metabolic Panel (CMP), Basic Metabolic Panel (BMP)",
    },
    "Estimated Glomerular Filtration Rate": {
        "summary_plain_name": "Estimated GFR (eGFR)",
        "what_it_measures": (
            "This test estimates how much blood the kidneys filter per minute. "
            "It is calculated from the creatinine level, age, sex, and other factors."
        ),
        "what_it_reflects": (
            "eGFR reflects overall kidney filtration capacity. "
            "It is the most widely used measure for evaluating kidney function."
        ),
        "low_general_associations": (
            "Low levels are commonly associated with reduced kidney function, "
            "which can range from mild impairment to advanced kidney disease."
        ),
        "high_general_associations": (
            "High levels generally indicate normal kidney function. "
            "Very high values are uncommon and may be seen in early diabetes or pregnancy."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include age, muscle mass, hydration, "
            "medications, and the formula used for calculation."
        ),
        "typical_panel": "Comprehensive Metabolic Panel (CMP)",
    },
    "BUN/Creatinine Ratio": {
        "summary_plain_name": "BUN/Creatinine Ratio",
        "what_it_measures": (
            "This test calculates the ratio between blood urea nitrogen and creatinine levels. "
            "It is a derived value, not a directly measured substance."
        ),
        "what_it_reflects": (
            "The ratio helps distinguish between different causes of abnormal kidney markers. "
            "It can provide additional context when BUN or creatinine levels are abnormal."
        ),
        "low_general_associations": (
            "Low ratios are commonly associated with liver disease, "
            "low-protein diets, and rhabdomyolysis (muscle breakdown)."
        ),
        "high_general_associations": (
            "High ratios may be seen in dehydration, gastrointestinal bleeding, "
            "high-protein diets, heart failure, and kidney conditions."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include hydration, protein intake, "
            "kidney function, liver function, and gastrointestinal health."
        ),
        "typical_panel": "Comprehensive Metabolic Panel (CMP)",
    },
    "Sodium": {
        "summary_plain_name": "Sodium (Na)",
        "what_it_measures": (
            "This test measures the amount of sodium in the blood. "
            "Sodium is an electrolyte that helps regulate water balance and nerve/muscle function."
        ),
        "what_it_reflects": (
            "Sodium levels reflect the body's fluid balance. "
            "The kidneys, hormones, and fluid intake all work together "
            "to keep sodium within a narrow range."
        ),
        "low_general_associations": (
            "Low levels (hyponatremia) are commonly associated with excess fluid intake, "
            "certain medications (especially diuretics), heart failure, "
            "liver cirrhosis, kidney disease, and hormonal imbalances."
        ),
        "high_general_associations": (
            "High levels (hypernatremia) may be seen in dehydration, "
            "excessive salt intake, diabetes insipidus, and certain kidney conditions."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include hydration status, "
            "medications (especially diuretics), kidney function, and hormonal balance."
        ),
        "typical_panel": "Comprehensive Metabolic Panel (CMP), Basic Metabolic Panel (BMP)",
    },
    "Potassium": {
        "summary_plain_name": "Potassium (K)",
        "what_it_measures": (
            "This test measures the amount of potassium in the blood. "
            "Potassium is an electrolyte essential for heart, muscle, and nerve function."
        ),
        "what_it_reflects": (
            "Potassium levels reflect the balance between intake, cellular exchange, "
            "and kidney excretion. Even small changes can affect heart rhythm."
        ),
        "low_general_associations": (
            "Low levels (hypokalemia) are commonly associated with diuretic use, "
            "vomiting, diarrhea, excessive sweating, and certain kidney conditions."
        ),
        "high_general_associations": (
            "High levels (hyperkalemia) may be seen in kidney disease, "
            "certain medications (ACE inhibitors, potassium-sparing diuretics), "
            "tissue injury, and acidosis."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include medications, kidney function, "
            "diet, hydration, and sample handling (hemolysis can falsely elevate potassium)."
        ),
        "typical_panel": "Comprehensive Metabolic Panel (CMP), Basic Metabolic Panel (BMP)",
    },
    "Chloride": {
        "summary_plain_name": "Chloride (Cl)",
        "what_it_measures": (
            "This test measures the amount of chloride in the blood. "
            "Chloride is an electrolyte that works with sodium and potassium "
            "to maintain fluid balance and acid-base balance."
        ),
        "what_it_reflects": (
            "Chloride levels reflect the body's acid-base and fluid balance. "
            "Chloride often changes in parallel with sodium levels."
        ),
        "low_general_associations": (
            "Low levels (hypochloremia) are commonly associated with prolonged vomiting, "
            "chronic respiratory conditions, metabolic alkalosis, and overhydration."
        ),
        "high_general_associations": (
            "High levels (hyperchloremia) may be seen in dehydration, "
            "kidney disease, metabolic acidosis, and excessive saline infusion."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include hydration, vomiting/diarrhea, "
            "medications, kidney function, and respiratory conditions."
        ),
        "typical_panel": "Comprehensive Metabolic Panel (CMP), Basic Metabolic Panel (BMP)",
    },
    "Carbon Dioxide": {
        "summary_plain_name": "Carbon Dioxide (CO2 / Bicarbonate)",
        "what_it_measures": (
            "This test measures the total carbon dioxide content in the blood, "
            "primarily in the form of bicarbonate. Bicarbonate is a buffer that helps "
            "maintain the blood's acid-base balance."
        ),
        "what_it_reflects": (
            "CO2 levels reflect the body's acid-base balance and how well "
            "the lungs and kidneys are maintaining proper blood pH."
        ),
        "low_general_associations": (
            "Low levels are commonly associated with metabolic acidosis, "
            "kidney disease, diabetic ketoacidosis, and chronic diarrhea."
        ),
        "high_general_associations": (
            "High levels may be seen in metabolic alkalosis, chronic vomiting, "
            "chronic lung disease, and overuse of antacids."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include lung function, "
            "kidney function, vomiting/diarrhea, and medications."
        ),
        "typical_panel": "Comprehensive Metabolic Panel (CMP), Basic Metabolic Panel (BMP)",
    },
    "Calcium": {
        "summary_plain_name": "Calcium (Ca)",
        "what_it_measures": (
            "This test measures the total amount of calcium in the blood. "
            "Calcium is essential for bone health, muscle contraction, "
            "nerve function, and blood clotting."
        ),
        "what_it_reflects": (
            "Blood calcium levels reflect the balance between calcium intake, "
            "bone storage, kidney excretion, and hormonal regulation "
            "(primarily parathyroid hormone and vitamin D)."
        ),
        "low_general_associations": (
            "Low levels (hypocalcemia) are commonly associated with vitamin D deficiency, "
            "hypoparathyroidism, kidney disease, low albumin levels, "
            "and certain medications."
        ),
        "high_general_associations": (
            "High levels (hypercalcemia) may be seen in hyperparathyroidism, "
            "certain cancers, excessive vitamin D or calcium supplementation, "
            "and prolonged immobility."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include albumin levels "
            "(calcium binds to albumin in blood), vitamin D status, "
            "parathyroid function, kidney function, and medications."
        ),
        "typical_panel": "Comprehensive Metabolic Panel (CMP)",
    },
    "Total Protein": {
        "summary_plain_name": "Total Protein",
        "what_it_measures": (
            "This test measures the total amount of protein in the blood, "
            "including both albumin and globulin."
        ),
        "what_it_reflects": (
            "Total protein reflects the overall protein status and can indicate "
            "nutritional health, liver function, kidney function, and immune activity."
        ),
        "low_general_associations": (
            "Low levels are commonly associated with liver disease, kidney disease "
            "(protein loss in urine), malnutrition, and malabsorption syndromes."
        ),
        "high_general_associations": (
            "High levels may be seen in chronic inflammation, chronic infections, "
            "dehydration, and certain blood disorders."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include hydration status, nutrition, "
            "liver function, kidney function, and inflammatory conditions."
        ),
        "typical_panel": "Comprehensive Metabolic Panel (CMP)",
    },
    "Albumin": {
        "summary_plain_name": "Albumin",
        "what_it_measures": (
            "This test measures the amount of albumin in the blood. "
            "Albumin is the most abundant protein in blood plasma, "
            "produced by the liver."
        ),
        "what_it_reflects": (
            "Albumin reflects liver synthetic function and nutritional status. "
            "It helps maintain fluid balance in blood vessels "
            "and transports hormones, vitamins, and medications."
        ),
        "low_general_associations": (
            "Low levels are commonly associated with liver disease, kidney disease "
            "(nephrotic syndrome), malnutrition, inflammation, and chronic illness."
        ),
        "high_general_associations": (
            "High levels are uncommon and are most often seen in dehydration."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include hydration, nutrition, "
            "liver function, kidney function, and inflammatory conditions."
        ),
        "typical_panel": "Comprehensive Metabolic Panel (CMP)",
    },
    "Globulin": {
        "summary_plain_name": "Globulin",
        "what_it_measures": (
            "This test measures the amount of globulin proteins in the blood. "
            "Globulins include immune system proteins (immunoglobulins/antibodies) "
            "and transport proteins."
        ),
        "what_it_reflects": (
            "Globulin levels reflect immune system activity, liver function, "
            "and the body's inflammatory state."
        ),
        "low_general_associations": (
            "Low levels are commonly associated with immune deficiency conditions, "
            "certain kidney conditions, and liver disease."
        ),
        "high_general_associations": (
            "High levels may be seen in chronic infections, chronic inflammation, "
            "autoimmune diseases, liver disease, and certain blood disorders."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include immune status, "
            "chronic infections, liver function, and inflammatory conditions."
        ),
        "typical_panel": "Comprehensive Metabolic Panel (CMP)",
    },
    "Albumin/Globulin Ratio": {
        "summary_plain_name": "Albumin/Globulin Ratio (A/G Ratio)",
        "what_it_measures": (
            "This test calculates the ratio of albumin to globulin in the blood. "
            "It is a derived value from the albumin and total protein measurements."
        ),
        "what_it_reflects": (
            "The A/G ratio reflects the relative balance between albumin and globulin, "
            "which can provide information about liver function, kidney function, "
            "and immune activity."
        ),
        "low_general_associations": (
            "Low ratios are commonly associated with conditions that increase globulin "
            "(chronic infections, autoimmune disease) or decrease albumin "
            "(liver disease, malnutrition)."
        ),
        "high_general_associations": (
            "High ratios are uncommon and may be seen in conditions with "
            "decreased globulin production, such as certain immune deficiencies."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include liver function, "
            "immune status, nutritional status, and chronic illness."
        ),
        "typical_panel": "Comprehensive Metabolic Panel (CMP)",
    },
    "Bilirubin, Total": {
        "summary_plain_name": "Bilirubin, Total",
        "what_it_measures": (
            "This test measures the total amount of bilirubin in the blood. "
            "Bilirubin is a yellow pigment produced when red blood cells break down."
        ),
        "what_it_reflects": (
            "Bilirubin levels reflect how well the liver is processing and excreting "
            "this breakdown product. The liver converts bilirubin so it can be "
            "removed from the body through bile."
        ),
        "low_general_associations": (
            "Low levels are generally not clinically significant."
        ),
        "high_general_associations": (
            "High levels may be seen in liver disease (hepatitis, cirrhosis), "
            "bile duct obstruction, hemolytic anemia (increased red blood cell breakdown), "
            "and Gilbert syndrome (a common, benign genetic condition)."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include fasting status, "
            "liver function, medications, and hemolysis (red blood cell breakdown)."
        ),
        "typical_panel": "Comprehensive Metabolic Panel (CMP), Liver Function Panel",
    },
    "Alkaline Phosphatase": {
        "summary_plain_name": "Alkaline Phosphatase (ALP)",
        "what_it_measures": (
            "This test measures the amount of alkaline phosphatase enzyme in the blood. "
            "ALP is found in the liver, bones, kidneys, and intestines."
        ),
        "what_it_reflects": (
            "ALP levels reflect liver and bone health. Elevated levels can come from "
            "either the liver or bones, so additional tests are sometimes needed "
            "to determine the source."
        ),
        "low_general_associations": (
            "Low levels are uncommon and may be associated with nutritional deficiencies "
            "(zinc, magnesium), hypothyroidism, and certain rare genetic conditions."
        ),
        "high_general_associations": (
            "High levels may be seen in liver disease, bile duct obstruction, "
            "bone conditions (Paget disease, fractures, bone growth), "
            "pregnancy, and growing children."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include age (higher in children "
            "and adolescents due to bone growth), pregnancy, recent meals, "
            "and medications."
        ),
        "typical_panel": "Comprehensive Metabolic Panel (CMP), Liver Function Panel",
    },
    "AST": {
        "summary_plain_name": "AST (Aspartate Aminotransferase)",
        "what_it_measures": (
            "This test measures the amount of AST enzyme in the blood. "
            "AST is found in the liver, heart, muscles, kidneys, and brain."
        ),
        "what_it_reflects": (
            "AST levels reflect tissue health, particularly the liver. "
            "When cells in these organs are damaged, AST is released into the bloodstream."
        ),
        "low_general_associations": (
            "Low levels are generally considered normal and not clinically significant."
        ),
        "high_general_associations": (
            "High levels may be seen in liver disease (hepatitis, cirrhosis), "
            "heart conditions, muscle injury, strenuous exercise, "
            "certain medications, and alcohol use."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include medications, alcohol consumption, "
            "intense physical exercise, and muscle injury."
        ),
        "typical_panel": "Comprehensive Metabolic Panel (CMP), Liver Function Panel",
    },
    "ALT": {
        "summary_plain_name": "ALT (Alanine Aminotransferase)",
        "what_it_measures": (
            "This test measures the amount of ALT enzyme in the blood. "
            "ALT is found primarily in the liver."
        ),
        "what_it_reflects": (
            "ALT levels are a more specific indicator of liver health compared to AST, "
            "since ALT is more concentrated in the liver. When liver cells are damaged, "
            "ALT is released into the bloodstream."
        ),
        "low_general_associations": (
            "Low levels are generally considered normal and not clinically significant."
        ),
        "high_general_associations": (
            "High levels may be seen in liver disease (hepatitis, fatty liver, cirrhosis), "
            "certain medications, alcohol use, and bile duct obstruction."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include medications, alcohol consumption, "
            "body weight, and liver conditions."
        ),
        "typical_panel": "Comprehensive Metabolic Panel (CMP), Liver Function Panel",
    },

    # =========================================================================
    # Lipids
    # =========================================================================
    "Total Cholesterol": {
        "summary_plain_name": "Total Cholesterol",
        "what_it_measures": (
            "This test measures the total amount of cholesterol in the blood, "
            "including HDL, LDL, and VLDL cholesterol."
        ),
        "what_it_reflects": (
            "Total cholesterol reflects the overall cholesterol level in the blood. "
            "Cholesterol is a waxy substance used by the body to build cells "
            "and produce hormones."
        ),
        "low_general_associations": (
            "Low levels are uncommon and may be associated with malnutrition, "
            "hyperthyroidism, liver disease, and certain genetic conditions."
        ),
        "high_general_associations": (
            "High levels may be seen in diets high in saturated fat, genetic factors, "
            "hypothyroidism, liver disease, kidney disease, and diabetes."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include diet, physical activity, "
            "body weight, genetics, age, sex, and medications."
        ),
        "typical_panel": "Lipid Panel",
    },
    "Triglycerides": {
        "summary_plain_name": "Triglycerides",
        "what_it_measures": (
            "This test measures the amount of triglycerides in the blood. "
            "Triglycerides are the most common type of fat in the body."
        ),
        "what_it_reflects": (
            "Triglyceride levels reflect how the body processes dietary fat and carbohydrates. "
            "Excess calories from food are converted into triglycerides and stored in fat cells."
        ),
        "low_general_associations": (
            "Low levels are uncommon and may be associated with a very low-fat diet, "
            "hyperthyroidism, malabsorption, and malnutrition."
        ),
        "high_general_associations": (
            "High levels may be seen in diets high in sugar and refined carbohydrates, "
            "obesity, diabetes, hypothyroidism, kidney disease, "
            "certain medications, and excessive alcohol intake."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include recent food intake "
            "(fasting is typically required), alcohol consumption, diet, "
            "physical activity, and medications."
        ),
        "typical_panel": "Lipid Panel",
    },
    "HDL Cholesterol": {
        "summary_plain_name": "HDL Cholesterol (\"Good\" Cholesterol)",
        "what_it_measures": (
            "This test measures the amount of high-density lipoprotein (HDL) cholesterol "
            "in the blood. HDL particles carry cholesterol away from the arteries "
            "back to the liver."
        ),
        "what_it_reflects": (
            "HDL cholesterol reflects the level of cholesterol being transported "
            "away from the arteries. It is often referred to as \"good\" cholesterol "
            "because of this reverse transport function."
        ),
        "low_general_associations": (
            "Low levels are commonly associated with sedentary lifestyle, smoking, "
            "obesity, high-carbohydrate diets, type 2 diabetes, and certain medications."
        ),
        "high_general_associations": (
            "High levels are generally considered favorable. Very high levels "
            "may sometimes be seen with certain genetic conditions or excessive alcohol intake."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include physical activity, smoking status, "
            "body weight, diet, alcohol intake, genetics, and medications."
        ),
        "typical_panel": "Lipid Panel",
    },
    "LDL Cholesterol": {
        "summary_plain_name": "LDL Cholesterol (\"Bad\" Cholesterol)",
        "what_it_measures": (
            "This test measures or calculates the amount of low-density lipoprotein (LDL) "
            "cholesterol in the blood. LDL particles carry cholesterol to the arteries."
        ),
        "what_it_reflects": (
            "LDL cholesterol reflects the level of cholesterol being delivered to tissues "
            "and artery walls. It is often referred to as \"bad\" cholesterol because "
            "elevated levels are associated with arterial plaque buildup."
        ),
        "low_general_associations": (
            "Low levels are generally considered favorable and are not typically "
            "associated with health concerns."
        ),
        "high_general_associations": (
            "High levels may be seen in diets high in saturated and trans fats, "
            "genetic factors (familial hypercholesterolemia), hypothyroidism, "
            "diabetes, kidney disease, and obesity."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include diet, body weight, "
            "physical activity, genetics, age, and medications."
        ),
        "typical_panel": "Lipid Panel",
    },
    "VLDL Cholesterol": {
        "summary_plain_name": "VLDL Cholesterol",
        "what_it_measures": (
            "This test measures or estimates the amount of very low-density lipoprotein "
            "(VLDL) cholesterol in the blood. VLDL is primarily a triglyceride carrier."
        ),
        "what_it_reflects": (
            "VLDL levels reflect the amount of triglyceride-rich particles in the blood. "
            "The liver produces VLDL to transport triglycerides to tissues."
        ),
        "low_general_associations": (
            "Low levels are generally not clinically significant."
        ),
        "high_general_associations": (
            "High levels may be seen in obesity, diabetes, metabolic syndrome, "
            "kidney disease, hypothyroidism, and excessive alcohol intake."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include diet, body weight, "
            "alcohol intake, and fasting status. VLDL is usually estimated "
            "from triglycerides rather than measured directly."
        ),
        "typical_panel": "Lipid Panel",
    },
    "Total Cholesterol/HDL Ratio": {
        "summary_plain_name": "Total Cholesterol/HDL Ratio",
        "what_it_measures": (
            "This test calculates the ratio of total cholesterol to HDL cholesterol. "
            "It is a derived value, not a directly measured substance."
        ),
        "what_it_reflects": (
            "This ratio reflects the balance between total cholesterol and HDL. "
            "It is sometimes used as a general indicator of cardiovascular risk profile."
        ),
        "low_general_associations": (
            "Low ratios are generally considered favorable, indicating a higher proportion "
            "of HDL relative to total cholesterol."
        ),
        "high_general_associations": (
            "High ratios may be seen when total cholesterol is elevated relative to HDL, "
            "which can be influenced by diet, genetics, and activity level."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include all factors that affect "
            "total cholesterol and HDL individually — diet, exercise, smoking, "
            "body weight, genetics, and medications."
        ),
        "typical_panel": "Lipid Panel",
    },
    "Non-HDL Cholesterol": {
        "summary_plain_name": "Non-HDL Cholesterol",
        "what_it_measures": (
            "This test calculates the total cholesterol minus HDL cholesterol. "
            "It represents all cholesterol carried on potentially atherogenic particles "
            "(LDL, VLDL, and others)."
        ),
        "what_it_reflects": (
            "Non-HDL cholesterol reflects the total amount of cholesterol carried "
            "on all particles other than HDL. It provides a broader picture "
            "than LDL alone."
        ),
        "low_general_associations": (
            "Low levels are generally considered favorable."
        ),
        "high_general_associations": (
            "High levels may be seen in the same conditions that elevate LDL "
            "and triglycerides — diet, genetics, diabetes, and hypothyroidism."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include diet, body weight, "
            "physical activity, genetics, and fasting status."
        ),
        "typical_panel": "Lipid Panel",
    },

    # =========================================================================
    # Thyroid
    # =========================================================================
    "Thyroid Stimulating Hormone": {
        "summary_plain_name": "TSH (Thyroid Stimulating Hormone)",
        "what_it_measures": (
            "This test measures the amount of thyroid stimulating hormone (TSH) in the blood. "
            "TSH is produced by the pituitary gland and signals the thyroid gland "
            "to produce thyroid hormones."
        ),
        "what_it_reflects": (
            "TSH reflects how the pituitary gland perceives thyroid hormone levels. "
            "When thyroid hormone levels are low, TSH rises to stimulate production. "
            "When they are high, TSH decreases."
        ),
        "low_general_associations": (
            "Low levels are commonly associated with hyperthyroidism (overactive thyroid), "
            "excessive thyroid medication, and certain pituitary conditions."
        ),
        "high_general_associations": (
            "High levels may be seen in hypothyroidism (underactive thyroid), "
            "Hashimoto's thyroiditis, iodine deficiency, "
            "and insufficient thyroid medication dosing."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include time of day "
            "(TSH is highest in early morning), thyroid medications, biotin supplements, "
            "severe illness, and pregnancy."
        ),
        "typical_panel": "Thyroid Panel",
    },
    "Free T4": {
        "summary_plain_name": "Free T4 (Free Thyroxine)",
        "what_it_measures": (
            "This test measures the amount of free (unbound) T4 hormone in the blood. "
            "T4 is the main hormone produced by the thyroid gland."
        ),
        "what_it_reflects": (
            "Free T4 reflects the amount of active, available thyroid hormone. "
            "T4 is converted to the more active T3 in tissues throughout the body."
        ),
        "low_general_associations": (
            "Low levels are commonly associated with hypothyroidism, "
            "pituitary dysfunction, severe illness, and certain medications."
        ),
        "high_general_associations": (
            "High levels may be seen in hyperthyroidism, thyroiditis, "
            "excessive thyroid medication, and certain rare conditions."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include thyroid medications, "
            "biotin supplements, pregnancy, estrogen therapy, "
            "and severe non-thyroid illness."
        ),
        "typical_panel": "Thyroid Panel",
    },
    "Free T3": {
        "summary_plain_name": "Free T3 (Free Triiodothyronine)",
        "what_it_measures": (
            "This test measures the amount of free (unbound) T3 hormone in the blood. "
            "T3 is the most active form of thyroid hormone."
        ),
        "what_it_reflects": (
            "Free T3 reflects the body's most active thyroid hormone level. "
            "Most T3 is produced by converting T4 in tissues rather than "
            "directly by the thyroid gland."
        ),
        "low_general_associations": (
            "Low levels are commonly associated with hypothyroidism, "
            "severe illness (sick euthyroid syndrome), and malnutrition."
        ),
        "high_general_associations": (
            "High levels may be seen in hyperthyroidism, T3 thyrotoxicosis, "
            "and excessive thyroid medication."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include thyroid medications, "
            "severe illness, nutritional status, and certain medications."
        ),
        "typical_panel": "Thyroid Panel",
    },

    # =========================================================================
    # Diabetes / Glycemic
    # =========================================================================
    "Hemoglobin A1c": {
        "summary_plain_name": "Hemoglobin A1c (HbA1c)",
        "what_it_measures": (
            "This test measures the percentage of hemoglobin that has glucose attached to it. "
            "It reflects average blood sugar levels over the preceding 2 to 3 months."
        ),
        "what_it_reflects": (
            "A1c reflects long-term blood sugar control. Because red blood cells live "
            "about 90-120 days, the A1c provides a picture of average glucose exposure "
            "over that period."
        ),
        "low_general_associations": (
            "Low levels generally indicate lower average blood sugar. Very low levels "
            "may be seen in conditions that shorten red blood cell lifespan "
            "(hemolytic anemia) or with frequent hypoglycemia."
        ),
        "high_general_associations": (
            "High levels may be seen in diabetes, prediabetes, "
            "and conditions that prolong red blood cell lifespan "
            "(iron deficiency anemia, certain hemoglobin variants)."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include red blood cell lifespan, "
            "hemoglobin variants, iron deficiency, kidney disease, "
            "recent blood transfusions, and pregnancy."
        ),
        "typical_panel": "Hemoglobin A1c, Diabetes Panel",
    },
    "Estimated Average Glucose": {
        "summary_plain_name": "Estimated Average Glucose (eAG)",
        "what_it_measures": (
            "This value estimates the average blood glucose level over the past 2 to 3 months. "
            "It is calculated from the A1c result, not directly measured."
        ),
        "what_it_reflects": (
            "eAG provides the A1c result translated into the same units (mg/dL) used "
            "by home glucose meters, making it easier to relate to daily readings."
        ),
        "low_general_associations": (
            "Low values correspond to lower average blood sugar levels. "
            "The same factors that affect A1c also affect eAG."
        ),
        "high_general_associations": (
            "High values correspond to higher average blood sugar levels. "
            "The same conditions that raise A1c also raise eAG."
        ),
        "common_influencing_factors": (
            "Factors that can influence this value are the same as those for A1c, "
            "since eAG is derived directly from the A1c measurement."
        ),
        "typical_panel": "Hemoglobin A1c, Diabetes Panel",
    },

    # =========================================================================
    # Urinalysis
    # =========================================================================
    "Urine Color": {
        "summary_plain_name": "Urine Color",
        "what_it_measures": (
            "This test observes and records the color of a urine sample. "
            "Normal urine ranges from pale yellow to amber."
        ),
        "what_it_reflects": (
            "Urine color reflects hydration status and can provide clues about "
            "certain conditions. The yellow color comes from urochrome, "
            "a pigment produced during hemoglobin breakdown."
        ),
        "low_general_associations": "",
        "high_general_associations": "",
        "common_influencing_factors": (
            "Factors that can influence urine color include hydration level, "
            "diet (beets, berries), vitamins (especially B vitamins), "
            "medications, and certain medical conditions."
        ),
        "typical_panel": "Urinalysis",
    },
    "Urine Appearance": {
        "summary_plain_name": "Urine Appearance (Clarity)",
        "what_it_measures": (
            "This test describes the visual clarity of a urine sample. "
            "It is typically recorded as clear, slightly cloudy, cloudy, or turbid."
        ),
        "what_it_reflects": (
            "Urine clarity reflects whether there are particles, cells, "
            "or other substances present in the urine."
        ),
        "low_general_associations": "",
        "high_general_associations": "",
        "common_influencing_factors": (
            "Factors that can influence urine appearance include hydration, "
            "urinary tract infections, kidney stones, diet, "
            "and how long the sample sat before analysis."
        ),
        "typical_panel": "Urinalysis",
    },
    "Specific Gravity": {
        "summary_plain_name": "Specific Gravity",
        "what_it_measures": (
            "This test measures the concentration of dissolved substances in urine "
            "compared to pure water. It indicates how concentrated or dilute the urine is."
        ),
        "what_it_reflects": (
            "Specific gravity reflects the kidneys' ability to concentrate urine. "
            "It provides information about hydration status and kidney function."
        ),
        "low_general_associations": (
            "Low values (dilute urine) are commonly associated with high fluid intake, "
            "diabetes insipidus, and certain kidney conditions that impair concentrating ability."
        ),
        "high_general_associations": (
            "High values (concentrated urine) may be seen in dehydration, "
            "heart failure, liver disease, and conditions that cause fluid loss."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include fluid intake, "
            "sweating, kidney function, and certain medications."
        ),
        "typical_panel": "Urinalysis",
    },
    "Urine pH": {
        "summary_plain_name": "Urine pH",
        "what_it_measures": (
            "This test measures the acidity or alkalinity of urine on a scale from 0 to 14. "
            "Normal urine pH typically ranges from 5.0 to 8.0."
        ),
        "what_it_reflects": (
            "Urine pH reflects the body's acid-base balance and the kidneys' role "
            "in maintaining it. The kidneys adjust urine pH to help keep blood pH stable."
        ),
        "low_general_associations": (
            "Low values (acidic urine) are commonly associated with high-protein diets, "
            "certain metabolic conditions, and cranberry consumption."
        ),
        "high_general_associations": (
            "High values (alkaline urine) may be seen in vegetarian diets, "
            "urinary tract infections (especially with certain bacteria), "
            "and certain kidney conditions."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include diet, medications, "
            "urinary tract infections, and time since the sample was collected."
        ),
        "typical_panel": "Urinalysis",
    },
    "Urine Protein": {
        "summary_plain_name": "Urine Protein",
        "what_it_measures": (
            "This test detects the presence of protein in urine. "
            "Normally, very little protein passes into the urine."
        ),
        "what_it_reflects": (
            "Urine protein reflects kidney filtration function. "
            "Healthy kidneys prevent most protein from passing into the urine."
        ),
        "low_general_associations": (
            "Negative or trace levels are generally considered normal."
        ),
        "high_general_associations": (
            "Elevated levels may be seen in kidney disease, urinary tract infections, "
            "heart failure, diabetes, high blood pressure, "
            "and temporarily after strenuous exercise or fever."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include hydration, "
            "recent strenuous exercise, fever, urinary tract infection, "
            "and standing for long periods (orthostatic proteinuria)."
        ),
        "typical_panel": "Urinalysis",
    },
    "Urine Glucose": {
        "summary_plain_name": "Urine Glucose",
        "what_it_measures": (
            "This test detects the presence of glucose (sugar) in urine. "
            "Normally, glucose is reabsorbed by the kidneys and does not appear in urine."
        ),
        "what_it_reflects": (
            "Urine glucose reflects whether blood sugar levels have exceeded "
            "the kidney's reabsorption capacity (renal threshold)."
        ),
        "low_general_associations": (
            "Negative results are considered normal."
        ),
        "high_general_associations": (
            "Positive results may be seen in uncontrolled diabetes, "
            "certain kidney conditions that lower the renal threshold, "
            "and pregnancy."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include blood sugar levels, "
            "kidney function, certain medications (SGLT2 inhibitors), "
            "and pregnancy."
        ),
        "typical_panel": "Urinalysis",
    },
    "Ketones": {
        "summary_plain_name": "Urine Ketones",
        "what_it_measures": (
            "This test detects the presence of ketones in urine. "
            "Ketones are produced when the body breaks down fat for energy "
            "instead of glucose."
        ),
        "what_it_reflects": (
            "Urine ketones reflect the body's metabolic state, "
            "specifically whether it is relying on fat breakdown for energy."
        ),
        "low_general_associations": (
            "Negative results are considered normal under typical circumstances."
        ),
        "high_general_associations": (
            "Positive results may be seen in diabetic ketoacidosis, "
            "prolonged fasting, very low-carbohydrate diets, "
            "strenuous exercise, and severe illness with vomiting."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include fasting status, "
            "carbohydrate intake, blood sugar control, "
            "physical activity, and illness."
        ),
        "typical_panel": "Urinalysis",
    },
    "Urine Blood": {
        "summary_plain_name": "Urine Blood (Occult Blood)",
        "what_it_measures": (
            "This test detects the presence of blood (hemoglobin) in urine. "
            "It can detect both visible and microscopic amounts of blood."
        ),
        "what_it_reflects": (
            "Urine blood reflects whether red blood cells or hemoglobin "
            "are present in the urine, which is not normal."
        ),
        "low_general_associations": (
            "Negative results are considered normal."
        ),
        "high_general_associations": (
            "Positive results may be seen in urinary tract infections, kidney stones, "
            "bladder or kidney conditions, strenuous exercise, "
            "and menstrual contamination."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include menstruation, "
            "strenuous exercise, urinary tract infections, "
            "certain medications, and sample collection technique."
        ),
        "typical_panel": "Urinalysis",
    },
    "Leukocyte Esterase": {
        "summary_plain_name": "Leukocyte Esterase",
        "what_it_measures": (
            "This test detects the presence of leukocyte esterase, "
            "an enzyme produced by white blood cells, in urine."
        ),
        "what_it_reflects": (
            "Leukocyte esterase reflects whether white blood cells are present in the urine, "
            "which can indicate the body is responding to an infection or inflammation "
            "in the urinary tract."
        ),
        "low_general_associations": (
            "Negative results are considered normal."
        ),
        "high_general_associations": (
            "Positive results may be seen in urinary tract infections, "
            "kidney infections, and inflammatory conditions of the urinary tract."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include urinary tract infections, "
            "sample contamination, and certain medications "
            "(such as those containing vitamin C, which may cause false negatives)."
        ),
        "typical_panel": "Urinalysis",
    },
    "Nitrite": {
        "summary_plain_name": "Urine Nitrite",
        "what_it_measures": (
            "This test detects the presence of nitrites in urine. "
            "Certain bacteria convert nitrates (normally present in urine) to nitrites."
        ),
        "what_it_reflects": (
            "Nitrite detection reflects the presence of specific bacteria in the urine "
            "that are capable of producing nitrites, which can indicate a bacterial infection."
        ),
        "low_general_associations": (
            "Negative results are considered normal, though a negative result "
            "does not completely exclude infection, as not all bacteria produce nitrites."
        ),
        "high_general_associations": (
            "Positive results are commonly associated with urinary tract infections "
            "caused by gram-negative bacteria (such as E. coli)."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include the type of bacteria present, "
            "how long urine was in the bladder before collection, "
            "diet (nitrate-rich foods), and vitamin C intake."
        ),
        "typical_panel": "Urinalysis",
    },

    # =========================================================================
    # Inflammation
    # =========================================================================
    "C-Reactive Protein": {
        "summary_plain_name": "C-Reactive Protein (CRP)",
        "what_it_measures": (
            "This test measures the amount of C-reactive protein in the blood. "
            "CRP is produced by the liver in response to inflammation."
        ),
        "what_it_reflects": (
            "CRP is a general marker of inflammation in the body. "
            "It rises quickly when inflammation is present and falls when it resolves."
        ),
        "low_general_associations": (
            "Low levels are generally considered normal and indicate minimal inflammation."
        ),
        "high_general_associations": (
            "High levels may be seen in infections, autoimmune conditions, "
            "inflammatory diseases, tissue injury, obesity, "
            "and cardiovascular conditions."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include acute illness, "
            "chronic inflammatory conditions, obesity, smoking, "
            "medications, and recent surgery or injury."
        ),
        "typical_panel": "Inflammation Markers",
    },
    "Erythrocyte Sedimentation Rate": {
        "summary_plain_name": "Erythrocyte Sedimentation Rate (ESR / Sed Rate)",
        "what_it_measures": (
            "This test measures how quickly red blood cells settle to the bottom "
            "of a test tube over one hour. It is measured in millimeters per hour."
        ),
        "what_it_reflects": (
            "ESR is a non-specific marker of inflammation. When inflammation is present, "
            "certain proteins cause red blood cells to clump together and settle faster."
        ),
        "low_general_associations": (
            "Low levels are generally considered normal. Very low values "
            "may be seen in polycythemia and conditions with very high red blood cell counts."
        ),
        "high_general_associations": (
            "High levels may be seen in infections, autoimmune diseases, "
            "inflammatory conditions, cancer, anemia, pregnancy, and aging."
        ),
        "common_influencing_factors": (
            "Factors that can influence this test include age, sex, pregnancy, "
            "anemia, medications, and the presence of any inflammatory condition."
        ),
        "typical_panel": "Inflammation Markers",
    },
}


def seed_education(apps, schema_editor):
    """Create LabEducationContent for each seeded LabTestCatalog entry."""
    LabTestCatalog = apps.get_model("medical", "LabTestCatalog")
    LabEducationContent = apps.get_model("medical", "LabEducationContent")

    for test_name, content in EDUCATION_DATA.items():
        try:
            catalog_entry = LabTestCatalog.objects.get(name=test_name)
        except LabTestCatalog.DoesNotExist:
            # Skip if no matching catalog entry (shouldn't happen for seeded tests)
            continue

        LabEducationContent.objects.get_or_create(
            lab_test=catalog_entry,
            defaults={
                "id": uuid.uuid4(),
                "summary_plain_name": content["summary_plain_name"],
                "what_it_measures": content["what_it_measures"],
                "what_it_reflects": content["what_it_reflects"],
                "low_general_associations": content.get("low_general_associations", ""),
                "high_general_associations": content.get("high_general_associations", ""),
                "common_influencing_factors": content["common_influencing_factors"],
                "typical_panel": content.get("typical_panel", ""),
                "is_system_generated": True,
            },
        )


def reverse_education(apps, schema_editor):
    LabEducationContent = apps.get_model("medical", "LabEducationContent")
    LabEducationContent.objects.filter(is_system_generated=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0003_lab_education_content"),
    ]

    operations = [
        migrations.RunPython(seed_education, reverse_education),
    ]
