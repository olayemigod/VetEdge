from pathlib import Path
from unittest import TestCase

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE = REPO_ROOT / "vetedge" / "services" / "owner_register_optimized.py"
ROUTER = REPO_ROOT / "vetedge" / "services" / "reporting_logic_v3.py"


class TestOwnerRegisterEfficiencyContract(TestCase):
    def read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def test_filtered_owner_register_scopes_dependent_aggregates_to_visible_customers(self):
        service = self.read(SERVICE)

        self.assertIn("visible_customer_names = sorted(", service)
        self.assertIn("scope_dependents = branch_owner_names is not None or bool(filters.get(\"owner\"))", service)
        self.assertIn('pet_filters = {owner_field: ("in", visible_customer_names)} if scope_dependents else {}', service)
        self.assertIn('invoice_filters["customer"] = ("in", visible_customer_names)', service)

    def test_unfiltered_full_report_avoids_giant_customer_in_filters(self):
        service = self.read(SERVICE)

        self.assertIn("if (visible_customer_names or not scope_dependents)", service)
        self.assertIn("if visible_customer_names or not scope_dependents:", service)
        self.assertIn('pet_filters = {owner_field: ("in", visible_customer_names)} if scope_dependents else {}', service)
        self.assertIn("if scope_dependents:", service)

    def test_branch_filter_is_not_added_to_pet_count_aggregate(self):
        service = self.read(SERVICE)
        pet_count_start = service.index("pet_counts = defaultdict(int)")
        outstanding_start = service.index("outstanding = defaultdict(float)", pet_count_start)
        pet_count_block = service[pet_count_start:outstanding_start]

        self.assertIn('pet_filters = {owner_field: ("in", visible_customer_names)} if scope_dependents else {}', pet_count_block)
        self.assertNotIn('filters.get("branch")', pet_count_block)
        self.assertNotIn("branch_field", pet_count_block)

    def test_reporting_v3_routes_owner_register_through_optimized_service(self):
        router = self.read(ROUTER)

        self.assertIn("from vetedge.services.owner_register_optimized import execute_owner_register", router)
        self.assertIn('if report_name == "Owner Register":', router)
        self.assertIn("return execute_owner_register(filters)", router)
        self.assertEqual(router.count("_execute_base_report(report_name, "), 2)
