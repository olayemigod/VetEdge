from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, now_datetime

from vetedge.services.appointment_flow import sync_missed_appointment_from_source
from vetedge.services.front_desk_action_center import (
	get_appointment_queue_view,
	get_front_desk_link_options,
	get_front_desk_summary,
	get_guest_request_detail,
	get_guest_requests,
	get_missed_appointment_detail,
	get_missed_appointments,
	perform_appointment_queue_action,
	perform_guest_request_action,
	perform_missed_appointment_action,
)


class TestFrontDeskActionCenterIntegration(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		settings = frappe.get_single("Veterinary Settings")
		settings.enable_vetedge = 1
		settings.enable_appointments = 1
		settings.enable_guest_booking = 1
		settings.enable_registration_billing = 0
		settings.enable_notifications = 0
		settings.save(ignore_permissions=True)

	def unique(self, prefix: str) -> str:
		return f"{prefix}-{frappe.generate_hash(length=8)}"

	def create_branch(self) -> str:
		name = self.unique("Edge Front Desk Branch")
		return frappe.get_doc({"doctype": "Branch", "branch": name}).insert(ignore_permissions=True).name

	def create_species(self) -> str:
		name = self.unique("Edge Front Desk Species")
		return frappe.get_doc(
			{
				"doctype": "Veterinary Species",
				"species_name": name,
				"disabled": 0,
			}
		).insert(ignore_permissions=True).name

	def create_guest_request(
		self,
		*,
		branch: str,
		species: str,
		appointment_requested: int = 0,
		preferred_datetime=None,
	):
		marker = self.unique("Edge Guest")
		return frappe.get_doc(
			{
				"doctype": "Veterinary Guest Booking Request",
				"guest_name": marker,
				"guest_email": f"{marker.lower().replace(' ', '-')}@example.com",
				"pet_name": self.unique("Edge Pet"),
				"species": species,
				"preferred_branch": branch,
				"appointment_requested": appointment_requested,
				"preferred_datetime": preferred_datetime,
				"status": "Registration Requested",
				"source": "Guest Portal",
			}
		).insert(ignore_permissions=True)

	def create_guest_appointment(self, *, request, appointment_datetime):
		return frappe.get_doc(
			{
				"doctype": "Veterinary Appointment",
				"guest_booking_request": request.name,
				"branch": request.preferred_branch,
				"appointment_datetime": appointment_datetime,
				"status": "Awaiting Registration",
				"appointment_type": "Consultation",
				"created_from": "Guest",
			}
		).insert(ignore_permissions=True)

	def test_summary_and_lists_use_live_permission_aware_contracts(self):
		branch = self.create_branch()
		species = self.create_species()
		request = self.create_guest_request(branch=branch, species=species)

		summary = get_front_desk_summary(branch=branch)
		self.assertGreaterEqual(summary["guest_requests"], 1)

		guest_list = get_guest_requests(search=request.guest_name, branch=branch, page_length=5)
		self.assertEqual(guest_list["page_length"], 5)
		self.assertIn(request.name, {row.name for row in guest_list["rows"]})

		missed_list = get_missed_appointments(branch=branch, page_length=5)
		for key in ("rows", "total", "start", "page_length"):
			self.assertIn(key, missed_list)

	def test_queue_partitions_today_tomorrow_and_future(self):
		branch = self.create_branch()
		species = self.create_species()
		day = getdate()
		appointments = {}
		for bucket, value in (
			("today", f"{day} 10:00:00"),
			("tomorrow", f"{add_days(day, 1)} 10:00:00"),
			("future", f"{add_days(day, 3)} 10:00:00"),
		):
			request = self.create_guest_request(
				branch=branch,
				species=species,
				appointment_requested=1,
				preferred_datetime=value,
			)
			appointments[bucket] = self.create_guest_appointment(
				request=request,
				appointment_datetime=value,
			).name

		queue = get_appointment_queue_view(branch=branch, reference_date=str(day))
		for bucket, appointment in appointments.items():
			self.assertIn(appointment, {row.name for row in queue[bucket]})

	def test_guest_request_cancel_updates_placeholder_appointment_safely(self):
		branch = self.create_branch()
		species = self.create_species()
		preferred = add_days(now_datetime(), 3)
		request = self.create_guest_request(
			branch=branch,
			species=species,
			appointment_requested=1,
			preferred_datetime=preferred,
		)
		appointment = self.create_guest_appointment(request=request, appointment_datetime=preferred)
		request.linked_appointment = appointment.name
		request.save(ignore_permissions=True)

		detail = get_guest_request_detail(request.name)
		result = perform_guest_request_action(
			request.name,
			"cancel_request",
			modified=str(detail["modified"]),
		)

		self.assertEqual(result["status"], "Cancelled")
		self.assertEqual(frappe.db.get_value("Veterinary Appointment", appointment.name, "status"), "Cancelled")

	def test_guest_action_rejects_stale_snapshot(self):
		branch = self.create_branch()
		species = self.create_species()
		request = self.create_guest_request(branch=branch, species=species)
		detail = get_guest_request_detail(request.name)
		request.reason_for_visit = "Changed by another front desk user"
		request.save(ignore_permissions=True)

		with self.assertRaises(frappe.TimestampMismatchError):
			perform_guest_request_action(
				request.name,
				"cancel_request",
				modified=str(detail["modified"]),
			)

	def test_missed_action_marks_contacted_and_blocks_stale_snapshot(self):
		branch = self.create_branch()
		species = self.create_species()
		past = add_days(now_datetime(), -1)
		request = self.create_guest_request(
			branch=branch,
			species=species,
			appointment_requested=1,
			preferred_datetime=past,
		)
		appointment = self.create_guest_appointment(request=request, appointment_datetime=past)
		sync_missed_appointment_from_source(appointment)
		missed_name = frappe.db.get_value(
			"Veterinary Missed Appointment",
			{"appointment": appointment.name},
			"name",
		)
		self.assertTrue(missed_name)

		detail = get_missed_appointment_detail(missed_name)
		contacted = perform_missed_appointment_action(
			missed_name,
			"mark_contacted",
			modified=str(detail["modified"]),
			values={"note": "Owner called by front desk."},
		)
		self.assertEqual(contacted["status"], "Contacted")
		self.assertEqual(contacted["values"]["contact_note"], "Owner called by front desk.")

		stale = get_missed_appointment_detail(missed_name)
		missed = frappe.get_doc("Veterinary Missed Appointment", missed_name)
		missed.missed_reason = "Updated by hourly review"
		missed.save(ignore_permissions=True)
		with self.assertRaises(frappe.TimestampMismatchError):
			perform_missed_appointment_action(
				missed_name,
				"resolve",
				modified=str(stale["modified"]),
				values={"resolution_note": "Should not overwrite newer work."},
			)

	def test_queue_action_rejects_stale_appointment_snapshot(self):
		branch = self.create_branch()
		species = self.create_species()
		preferred = add_days(now_datetime(), 2)
		request = self.create_guest_request(
			branch=branch,
			species=species,
			appointment_requested=1,
			preferred_datetime=preferred,
		)
		appointment = self.create_guest_appointment(request=request, appointment_datetime=preferred)
		from vetedge.services.front_desk_action_center import get_appointment_action_detail

		detail = get_appointment_action_detail(appointment.name)
		appointment.notes = "Changed by another user"
		appointment.save(ignore_permissions=True)
		with self.assertRaises(frappe.TimestampMismatchError):
			perform_appointment_queue_action(
				appointment.name,
				"confirm",
				modified=str(detail["modified"]),
			)

	def test_practitioner_link_only_returns_enabled_doctor_users(self):
		marker = frappe.generate_hash(length=8).lower()
		doctor_email = f"doctor-{marker}@example.com"
		other_email = f"staff-{marker}@example.com"
		doctor = frappe.get_doc(
			{
				"doctype": "User",
				"email": doctor_email,
				"first_name": f"Doctor {marker}",
				"enabled": 1,
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
		doctor.add_roles("VetEdge Doctor")
		frappe.get_doc(
			{
				"doctype": "User",
				"email": other_email,
				"first_name": f"Staff {marker}",
				"enabled": 1,
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)

		options = get_front_desk_link_options("practitioner", marker)
		values = {row["value"] for row in options}
		self.assertIn(doctor_email, values)
		self.assertNotIn(other_email, values)
