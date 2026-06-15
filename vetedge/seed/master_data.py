from __future__ import annotations

import frappe


SPECIES = [
	{"species_name": "Dog"},
	{"species_name": "Cat"},
	{"species_name": "Rabbit"},
	{"species_name": "Bird"},
]

BREEDS = [
	{"breed_name": "Mixed Breed", "species": "Dog"},
	{"breed_name": "Labrador Retriever", "species": "Dog"},
	{"breed_name": "German Shepherd", "species": "Dog"},
	{"breed_name": "Domestic Short Hair", "species": "Cat"},
	{"breed_name": "Persian", "species": "Cat"},
	{"breed_name": "Mixed Breed", "species": "Cat"},
	{"breed_name": "New Zealand White", "species": "Rabbit"},
	{"breed_name": "Parakeet", "species": "Bird"},
]

SYMPTOMS = [
	{"symptom_name": "Vomiting", "body_system": "Digestive"},
	{"symptom_name": "Diarrhea", "body_system": "Digestive"},
	{"symptom_name": "Coughing", "body_system": "Respiratory"},
	{"symptom_name": "Lameness", "body_system": "Musculoskeletal"},
	{"symptom_name": "Loss of Appetite", "body_system": "General"},
]

DIAGNOSIS_CATEGORIES = [
	{"category_name": "Digestive"},
	{"category_name": "Respiratory"},
	{"category_name": "Dermatology"},
	{"category_name": "Ear"},
	{"category_name": "Eye"},
	{"category_name": "Dental"},
	{"category_name": "Trauma"},
	{"category_name": "Orthopedic"},
	{"category_name": "Neurological"},
	{"category_name": "Urinary"},
	{"category_name": "Reproductive"},
	{"category_name": "Preventive"},
	{"category_name": "General"},
]

DIAGNOSES = [
	{"diagnosis_name": "Gastroenteritis", "category": "Digestive"},
	{"diagnosis_name": "Upper Respiratory Infection", "category": "Respiratory"},
	{"diagnosis_name": "Dermatitis", "category": "Dermatology"},
	{"diagnosis_name": "Otitis Externa", "category": "Ear"},
	{"diagnosis_name": "Wound", "category": "Trauma"},
]

SERVICE_TYPES = [
	{"service_type_name": "Consultation", "service_category": "Clinical"},
	{"service_type_name": "Vaccination", "service_category": "Preventive"},
	{"service_type_name": "Laboratory", "service_category": "Diagnostics"},
	{"service_type_name": "Grooming", "service_category": "Wellness"},
	{"service_type_name": "Boarding", "service_category": "Boarding"},
]

TREATMENT_TYPES = [
	{"treatment_type_name": "Medication", "treatment_category": "Medication", "requires_dispensary": 1},
	{"treatment_type_name": "Injection", "treatment_category": "Medication", "requires_dispensary": 1},
	{"treatment_type_name": "Procedure", "treatment_category": "Procedure"},
	{"treatment_type_name": "Diet", "treatment_category": "Diet", "requires_dispensary": 1},
	{"treatment_type_name": "Consumable", "treatment_category": "Consumable", "requires_dispensary": 1},
]

CONSULTATION_TYPES = [
	{"consultation_type": "General Consultation", "sort_order": 10},
	{"consultation_type": "Follow-up Consultation", "sort_order": 20},
	{"consultation_type": "Emergency Consultation", "sort_order": 30},
	{"consultation_type": "House Call", "is_house_call": 1, "sort_order": 40},
	{"consultation_type": "Vaccination Consultation", "sort_order": 50},
	{"consultation_type": "Surgery Review", "sort_order": 60},
	{"consultation_type": "Grooming Consultation", "sort_order": 70},
	{"consultation_type": "Boarding Review", "sort_order": 80},
	{"consultation_type": "Hospitalisation", "sort_order": 90},
]


def seed_master_data() -> None:
	seed_records("Veterinary Species", SPECIES, ["species_name"])
	seed_records("Veterinary Breed", BREEDS, ["breed_name", "species"])
	seed_records("Veterinary Symptom", SYMPTOMS, ["symptom_name"])
	seed_records("Veterinary Diagnosis Category", DIAGNOSIS_CATEGORIES, ["category_name"])
	seed_records("Veterinary Diagnosis", DIAGNOSES, ["diagnosis_name"])
	seed_records("Veterinary Service Type", SERVICE_TYPES, ["service_type_name"])
	seed_records("Veterinary Treatment Type", TREATMENT_TYPES, ["treatment_type_name"])
	seed_records("Consultation Type", CONSULTATION_TYPES, ["consultation_type"])


def seed_records(doctype: str, records: list[dict], unique_fields: list[str]) -> None:
	if not frappe.db.exists("DocType", doctype) or not frappe.db.table_exists(doctype):
		return

	for record in records:
		filters = {fieldname: record[fieldname] for fieldname in unique_fields}
		if frappe.db.exists(doctype, filters):
			continue

		doc = frappe.get_doc({"doctype": doctype, **record})
		doc.insert(ignore_permissions=True)
