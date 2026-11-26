# SLCM Specs

All module specs, guides, test plans and diagnostics for the `slcm` app, grouped by module.

## Admission
- [Admission Portal Restructure — Implementation Plan](admission/admission_portal_restructure.md)
- [Payment to Custom Success Page Flow (FLE / Razorpay)](admission/razorpay_success_integration_manual.md)
- [Interview — Test Scenarios & Specifications](admission/interview_test_scenarios.md)
- [Interview — Test Scenario Matrix Table](admission/interview_test_scenarios_table.md)
- [Eligibility Evaluation & National Test Exemption — QA Test Specification](admission/eligibility_test_scenarios.md)

## Attendance
- [Comprehensive Attendance System Workflow](attendance/attendance_workflows.md)
- [Deep Dive: Student Attendance System](attendance/attendance_modules_deep_dive.md)
- [Deep Dive: Attendance Session](attendance/attendance_session_deep_dive.md)
- [Attendance Module — Workflow & Testing Guide](attendance/attendance_testing_guide.md)
- [RFID Attendance API Contract](attendance/attendance_api_contract.md)
- [RFID SQL Agent — Setup, Connection & Verification Guide](attendance/rfid_sql_agent_guide.md)
- [Plan: OH, Class Participation and Small-Group Attendance](attendance/oh_cp_small_group_attendance_plan.md)

## Programme Management
- [Programme Management: User Guide](programme_management/programme_management_guide.md)
- [Audit log: removal of old-flow academic DocTypes and pages](programme_management/old_flow_doctype_removal_audit.md)

## Timetable
- [Timetable Calendar Diagnostic Report](timetable/08_Timetable_Calendar_Diagnostic.md)
- [Timetable Regression Diagnostic](timetable/09_Timetable_Regression_Diagnostic.md)

## ERPNext Bridge
- [ERPNext Coexistence — Test Checklist](erpnext_bridge/erpnext_coexistence_test_checklist.md)
- [SLCM Fees → ERPNext Accounting — Design and Test Checklist](erpnext_bridge/erpnext_fee_bridge_test_checklist.md)

## Portal
- [Student Portal — Design System Guidelines](portal/portal_theme.md)

## Other READMEs (kept in place)
- [App README](../README.md) — used by `pyproject.toml`
- [Frontend (Vue / frappe-ui) README](../frontend/README.md) — referenced by `frontend/vite.config.js`
- [RFID Sync Agent README](../rfid_sync_agent/README.md) — ships with the agent package
