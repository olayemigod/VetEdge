from pathlib import Path
from unittest import TestCase

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE = REPO_ROOT / "vetedge" / "services" / "owner_register_optimized.py"
ROUTER = REPO_ROOT / "vetedge" / "services" / "reporting_logic_v3.py"


class TestOwnerRegisterEfficiencyContract(TestCase):
    def read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def test_owner_register_scopes_dependent_aggregates_to_visible_customers(self):
        service = self.read(SERVICE)

        self.assertIn("visible_customer_names = sorted(", service)
        self.assertIn('filters={owner_field: ("in", visible_customer_names)}', service)
        self.assertIn('"customer": ("in", visible_customer_names)', service)
        self.assertIn("if visible_customer_names and frappe.db.exists", service)
        self.assertIn("if visible_customer_names:", service)

    def test_branch_filter_is_not_added_to_pet_count_aggregate(self):
        service = self.read(SERVICE)
        pet_count_start = service.index("pet_counts = defaultdict(int)")
        outstanding_start = service.index("outstanding = defaultdict(float)", pet_count_start)
        pet_count_block = service[pet_count_start:outstanding_start]

        self.assertIn('filters={owner_field: ("in", visible_customer_names)}', pet_count_block)
        self.assertNotIn('filters.get("branch")', pet_count_block)
        self.assertNotIn("branch_field", pet_count_block)

    def test_reporting_v3_routes_owner_register_through_optimized_service(self):
        router = self.read(ROUTER)

        self.assertIn("from vetedge.services.owner_register_optimized import execute_owner_register", router)
        self.assertIn('if report_name == "Owner Register":', router)
        self.assertIn("return execute_owner_register(filters)", router)
        self.assertEqual(router.count("_execute_base_report(report_name, "), 2)
