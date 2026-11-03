# Data Dictionary: Payroll Validation & Reconciliation System

This data dictionary documents all core entities, relationships, attributes, data types, constraints, and validation rules in accordance with Step 1 of the solution specification.

---

## 1. PayGroup
Represents organizational payroll classification governing standard hours, overtime thresholds, and pay frequency.

| Field Name | Type | Required / Optional | Allowed Values | Units | Uniqueness | Validation Rule / Constraint |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | Integer | Required (PK) | Auto-increment positive integer | IDs | Unique | Primary Key |
| `group_code` | String | Required | Alphanumeric (e.g., `PG-001`, `PG-002`, `PG-003`) | Code | Unique | Indexed, uppercase alphanumeric |
| `group_name` | String | Required | Valid department/worker group name | Text | Non-unique | Non-empty string |
| `pay_frequency`| String | Required | `MONTHLY`, `BIWEEKLY`, `WEEKLY` | Enum | Non-unique | Must belong to allowed frequency enum |
| `max_period_hours` | Float | Required | $0.0 \le x \le 300.0$ | Hours | Non-unique | Threshold for excessive hours rule |
| `standard_hours` | Float | Required | $0.0 \le x \le 200.0$ | Hours | Non-unique | Normal threshold before overtime kicks in |

**Cardinality:**
- 1 PayGroup to N Employees (1:N)

---

## 2. Employee
Represents master identity, employment status, statutory tax & banking credentials, and base compensation.

| Field Name | Type | Required / Optional | Allowed Values | Units | Uniqueness | Validation Rule / Constraint |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | Integer | Required (PK) | Auto-increment positive integer | IDs | Unique | Primary Key |
| `employee_id` | String | Required | Deterministic `EMP-000001` to `EMP-999999` | Code | Unique | 10 chars, regex `^EMP-\d{6}$` |
| `name` | String | Required | Standard synthetic full names | Text | Non-unique | Non-empty string |
| `email` | String | Required | Standard RFC 5322 email | Text | Unique | Valid email format |
| `department` | String | Optional | Engineering, Finance, HR, Operations, Sales | Text | Non-unique | Organization unit classification |
| `designation` | String | Optional | Professional job titles | Text | Non-unique | Standard job level |
| `bank_account` | String | Optional (Flagged if null) | `ACC-<employee-id>-<rand>` | Account | Non-unique | `RULE-BANK-001` flags null or empty |
| `tax_id` | String | Optional (Flagged if null) | `TAX-<employee-id>-<rand>` | Tax ID | Non-unique | `RULE-TAX-001` flags null or empty |
| `basic_salary` | Float | Required | $> 0.0$ (typically ₹25,000 - ₹150,000) | Currency (INR) | Non-unique | Positive numerical float |
| `employment_status` | String | Required | `ACTIVE`, `TERMINATED`, `ON_LEAVE` | Enum | Non-unique | Allowed enum validation |
| `pay_group_id` | Integer | Required (FK) | Foreign key to `pay_groups.id` | Foreign Key | Non-unique | Must reference existing PayGroup |
| `created_at` | DateTime | Required | Valid ISO 8601 UTC timestamp | Timestamp | Non-unique | Immutable creation date |

**Cardinality:**
- N Employees to 1 PayGroup (N:1)
- 1 Employee to N TimeEntries (1:N)
- 1 Employee to N LeaveRecords (1:N)
- 1 Employee to N Allowances (1:N)
- 1 Employee to N Deductions (1:N)
- 1 Employee to N PayrollInputs (1:N)

---

## 3. PayPeriod
Represents statutory payroll cycles and processing calendars.

| Field Name | Type | Required / Optional | Allowed Values | Units | Uniqueness | Validation Rule / Constraint |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | Integer | Required (PK) | Auto-increment positive integer | IDs | Unique | Primary Key |
| `period_code` | String | Required | Deterministic `PP-YYYY-MM` (e.g. `PP-2026-01`) | Code | Unique | Regex `^PP-\d{4}-\d{2}$` |
| `start_date` | Date | Required | Calendar date (e.g., `2026-01-01`) | Date | Non-unique | `start_date <= end_date` |
| `end_date` | Date | Required | Calendar date (e.g., `2026-01-31`) | Date | Non-unique | Date ordering validation |
| `payment_date` | Date | Optional | Calendar date (e.g., `2026-02-05`) | Date | Non-unique | Typically `payment_date >= end_date` |
| `status` | String | Required | `OPEN`, `PROCESSING`, `CLOSED` | Enum | Non-unique | Standard period lifecycle states |

**Cardinality:**
- 1 PayPeriod to N TimeEntries, LeaveRecords, Allowances, Deductions, PayrollInputs, Exports.

---

## 4. TimeEntry
Represents recorded attendance shifts submitted by employees or imported from timesheet devices.

| Field Name | Type | Required / Optional | Allowed Values | Units | Uniqueness | Validation Rule / Constraint |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | Integer | Required (PK) | Auto-increment positive integer | IDs | Unique | Primary Key |
| `time_id` | String | Required | `TIME-<employee-id>-<date>` | Code | Unique | Naming convention; immutable |
| `employee_id` | Integer | Required (FK) | Foreign key to `employees.id` | Foreign Key | Non-unique | Valid active employee |
| `pay_period_id` | Integer | Required (FK) | Foreign key to `pay_periods.id` | Foreign Key | Non-unique | Valid active period |
| `work_date` | Date | Required | Date within pay period date boundary | Date | Non-unique | Must fall between period start & end |
| `hours_worked` | Float | Required | $0.0 \le x \le 24.0$ | Hours | Non-unique | Non-negative hours |
| `approval_status`| String | Required | `PENDING`, `APPROVED`, `REJECTED` | Enum | Non-unique | `RULE-TIME-UNAPP-001` flags PENDING |
| `submission_ref` | String | Required | `SUB-<employee-id>-<date>` | Reference | Non-unique | `RULE-TIME-DUP-001` flags duplicate ref |
| `corrects_time_entry_id` | Integer | Optional (FK) | Foreign key to `time_entries.id` | Foreign Key | Non-unique | Audit link to corrected previous entry |

---

## 5. LeaveRecord
Represents approved or pending employee leave requests.

| Field Name | Type | Required / Optional | Allowed Values | Units | Uniqueness | Validation Rule / Constraint |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | Integer | Required (PK) | Auto-increment positive integer | IDs | Unique | Primary Key |
| `leave_id` | String | Required | `LEV-<employee-id>-<date>` | Code | Unique | Deterministic naming convention |
| `employee_id` | Integer | Required (FK) | Foreign key to `employees.id` | Foreign Key | Non-unique | Must reference existing employee |
| `pay_period_id` | Integer | Required (FK) | Foreign key to `pay_periods.id` | Foreign Key | Non-unique | Must reference existing pay period |
| `leave_type` | String | Required | `ANNUAL`, `SICK`, `CASUAL`, `UNPAID` | Enum | Non-unique | Allowed leave category enum |
| `start_date` | Date | Required | Calendar date | Date | Non-unique | `start_date <= end_date` |
| `end_date` | Date | Required | Calendar date | Date | Non-unique | Boundary check inside period |
| `days` | Float | Required | $> 0.0$ (typically 1.0, 2.0, 5.0) | Days | Non-unique | Positive numerical float |
| `approval_status`| String | Required | `PENDING`, `APPROVED`, `REJECTED` | Enum | Non-unique | Approval lifecycle state |
| `is_unpaid` | Boolean | Required | `True`, `False` | Boolean | Non-unique | If True, generates unpaid leave deduction |

---

## 6. Allowance
Represents recurring or variable earnings components added to base compensation.

| Field Name | Type | Required / Optional | Allowed Values | Units | Uniqueness | Validation Rule / Constraint |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | Integer | Required (PK) | Auto-increment positive integer | IDs | Unique | Primary Key |
| `allowance_id` | String | Required | `ALW-<employee-id>-<period>-<seq>` | Code | Unique | Deterministic naming convention |
| `employee_id` | Integer | Required (FK) | Foreign key to `employees.id` | Foreign Key | Non-unique | Must reference existing employee |
| `pay_period_id` | Integer | Required (FK) | Foreign key to `pay_periods.id` | Foreign Key | Non-unique | Must reference existing period |
| `allowance_type`| String | Required | `HOUSING`, `TRANSPORT`, `MEAL`, `MEDICAL` | Enum | Non-unique | Allowed allowance types |
| `amount` | Float | Required | $\ge 0.0$ | Currency (INR) | Non-unique | Non-negative numerical value |
| `effective_date`| Date | Required | Calendar date | Date | Non-unique | Within pay period boundaries |
| `reference_code`| String | Required | `REF-ALW-<employee-id>-<period>-<type>` | Reference | Non-unique | `RULE-ALW-DUP-001` flags duplicate ref |

---

## 7. Deduction
Represents statutory (Tax, PF) or voluntary adjustments subtracted from gross earnings.

| Field Name | Type | Required / Optional | Allowed Values | Units | Uniqueness | Validation Rule / Constraint |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | Integer | Required (PK) | Auto-increment positive integer | IDs | Unique | Primary Key |
| `deduction_id` | String | Required | `DED-<employee-id>-<period>-<seq>` | Code | Unique | Deterministic naming convention |
| `employee_id` | Integer | Required (FK) | Foreign key to `employees.id` | Foreign Key | Non-unique | Must reference existing employee |
| `pay_period_id` | Integer | Required (FK) | Foreign key to `pay_periods.id` | Foreign Key | Non-unique | Must reference existing period |
| `deduction_type`| String | Required | `TAX`, `PF`, `INSURANCE`, `UNPAID_LEAVE` | Enum | Non-unique | Allowed deduction types |
| `amount` | Float | Required | $\ge 0.0$ | Currency (INR) | Non-unique | Non-negative numerical value |
| `effective_date`| Date | Required | Calendar date | Date | Non-unique | Within pay period boundaries |
| `reference_code`| String | Required | `REF-DED-<employee-id>-<period>-<type>` | Reference | Non-unique | Indexed reference code |
| `leave_record_id`| Integer | Optional (FK) | Foreign key to `leave_records.id` | Foreign Key | Non-unique | `RULE-LEV-DUP-001` flags duplicate FK |

---

## 8. PayrollInput
Aggregated pre-export payroll record synthesizing all approved components for an employee in a pay period.

| Field Name | Type | Required / Optional | Allowed Values | Units | Uniqueness | Validation Rule / Constraint |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | Integer | Required (PK) | Auto-increment positive integer | IDs | Unique | Primary Key |
| `payroll_input_id` | String | Required | `PIN-<employee-id>-YYYY-MM` | Code | Unique | Indexed, regex `^PIN-EMP-\d{6}-\d{4}-\d{2}$` |
| `employee_id` | Integer | Required (FK) | Foreign key to `employees.id` | Foreign Key | Non-unique | Valid employee |
| `pay_period_id` | Integer | Required (FK) | Foreign key to `pay_periods.id` | Foreign Key | Non-unique | Valid pay period |
| `basic_salary` | Float | Required | Base salary derived from employee | Currency (INR) | Non-unique | Must match Employee.basic_salary |
| `overtime_amount` | Float | Required | Calculated from approved overtime hours | Currency (INR) | Non-unique | Overtime hours $\times$ hourly rate $\times 1.5$ |
| `allowance_total`| Float | Required | Sum of approved allowances | Currency (INR) | Non-unique | Derived aggregate |
| `deduction_total`| Float | Required | Sum of statutory & standard deductions | Currency (INR) | Non-unique | Derived aggregate |
| `unpaid_leave_deduction` | Float | Required | Deductions for approved unpaid leaves | Currency (INR) | Non-unique | Derived aggregate |
| `net_pay` | Float | Required | Basic + OT + Allow - Deduct - UnpaidLeave | Currency (INR) | Non-unique | `RULE-PAY-RECON-001` verifies math |
| `status` | String | Required | `DRAFT`, `PENDING`, `APPROVED`, `REJECTED`, `EXPORTED` | Enum | Non-unique | Controlled lifecycle transitions |
| `created_at` | DateTime | Required | ISO 8601 UTC timestamp | Timestamp | Non-unique | Record generation timestamp |

---

## 9. ValidationRule
Defines automated governance validation rules with severity and descriptions.

| Field Name | Type | Required / Optional | Allowed Values | Units | Uniqueness | Validation Rule / Constraint |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | Integer | Required (PK) | Auto-increment positive integer | IDs | Unique | Primary Key |
| `rule_code` | String | Required | `RULE-BANK-001`, `RULE-TAX-001`, etc. | Code | Unique | Standard convention |
| `rule_name` | String | Required | Human-readable name | Text | Non-unique | Descriptive title |
| `description` | String | Optional | Detailed explanation of what is flagged | Text | Non-unique | Explanatory notes |
| `severity` | String | Required | `HIGH`, `MEDIUM`, `LOW` | Enum | Non-unique | `HIGH` strictly blocks export & approval |
| `is_active` | Boolean | Required | `True`, `False` | Boolean | Non-unique | Enables or disables the rule |

---

## 10. ExceptionRecord
Tracks anomalies detected by validation rules against master data or transactions.

| Field Name | Type | Required / Optional | Allowed Values | Units | Uniqueness | Validation Rule / Constraint |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | Integer | Required (PK) | Auto-increment positive integer | IDs | Unique | Primary Key |
| `exception_id` | String | Required | `EXC-<record-context>-<type>` | Code | Unique | Deterministic exception key |
| `payroll_input_id`| Integer | Optional (FK) | Foreign key to `payroll_inputs.id` | Foreign Key | Non-unique | Linked payroll input |
| `validation_rule_id`| Integer | Optional (FK) | Foreign key to `validation_rules.id` | Foreign Key | Non-unique | Must reference registered rule |
| `employee_id` | Integer | Required (FK) | Foreign key to `employees.id` | Foreign Key | Non-unique | Affected employee |
| `issue_type` | String | Required | `MISSING_BANK_ACCOUNT`, `EXCESSIVE_WORKING_HOURS`, etc. | Enum | Non-unique | Categorical anomaly code |
| `description` | String | Optional | Detailed findings description | Text | Non-unique | Contextual diagnostic message |
| `status` | String | Required | `OPEN`, `RESOLVED` | Enum | Non-unique | State change requires verified fix |
| `severity` | String | Required | `HIGH`, `MEDIUM`, `LOW` | Enum | Non-unique | Inherited from rule severity |
| `source_entity` | String | Optional | `Employee`, `TimeEntry`, `Allowance`, etc. | Text | Non-unique | Source table name |
| `source_record_id` | String | Optional | Natural ID of the erroneous source row | Text | Non-unique | Source reference ID |
| `resolution_notes`| String | Optional | Audit explanation when marked resolved | Text | Non-unique | Required on manual resolution |
| `resolved_by` | String | Optional | Actor identity who verified the fix | Text | Non-unique | Audit tracking |
| `resolved_at` | DateTime | Optional | Timestamp when resolution confirmed | Timestamp | Non-unique | ISO 8601 UTC timestamp |
| `created_at` | DateTime | Required | Timestamp when anomaly detected | Timestamp | Non-unique | ISO 8601 UTC timestamp |

---

## 11. Approval
Maintains immutable governance approval and rejection event records.

| Field Name | Type | Required / Optional | Allowed Values | Units | Uniqueness | Validation Rule / Constraint |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | Integer | Required (PK) | Auto-increment positive integer | IDs | Unique | Primary Key |
| `approval_id` | String | Required | `APR-YYYY-MM-<seq:06d>` | Code | Unique | Immutable identifier |
| `payroll_input_id`| Integer | Required (FK) | Foreign key to `payroll_inputs.id` | Foreign Key | Non-unique | Target payroll input |
| `approver_name` | String | Required | Name of signing actor | Text | Non-unique | Non-empty string |
| `approver_role` | String | Required | `HR`, `MANAGER`, `ADMIN`, `IT_OPS` | Enum | Non-unique | Actor role |
| `decision` | String | Required | `APPROVED`, `REJECTED` | Enum | Non-unique | Strict governance decision |
| `comments` | String | Optional | Sign-off rationale or rejection reason | Text | Non-unique | Audit trail |
| `created_at` | DateTime | Required | ISO 8601 UTC timestamp | Timestamp | Non-unique | Immutable signing timestamp |

---

## 12. PayrollExport
Maintains immutable audit records of all official payroll exports.

| Field Name | Type | Required / Optional | Allowed Values | Units | Uniqueness | Validation Rule / Constraint |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | Integer | Required (PK) | Auto-increment positive integer | IDs | Unique | Primary Key |
| `export_id` | String | Required | `PEX-YYYY-<seq:06d>` (e.g. `PEX-2026-000001`) | Code | Unique | Zero-padded immutable export ID |
| `pay_period_id` | Integer | Required (FK) | Foreign key to `pay_periods.id` | Foreign Key | Non-unique | Exported cycle |
| `file_name` | String | Required | `payroll_export_<period>_<export-id>.csv` | Text | Non-unique | Standard export file name |
| `file_format` | String | Required | `CSV` | Format | Non-unique | Default CSV |
| `record_count` | Integer | Required | $\ge 0$ | Count | Non-unique | Number of exported rows |
| `total_amount` | Float | Required | $\ge 0.0$ | Currency (INR) | Non-unique | Sum of exported net pay |
| `export_status` | String | Required | `COMPLETED`, `FAILED` | Enum | Non-unique | Export outcome |
| `exported_by` | String | Required | Name/role of exporting actor | Text | Non-unique | Identity tracking |
| `exported_at` | DateTime | Required | ISO 8601 UTC timestamp | Timestamp | Non-unique | Export execution timestamp |

---

## 13. AuditLog
Persists immutable chronological event records for all state transitions and corrections.

| Field Name | Type | Required / Optional | Allowed Values | Units | Uniqueness | Validation Rule / Constraint |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | Integer | Required (PK) | Auto-increment positive integer | IDs | Unique | Primary Key |
| `log_id` | String | Required | `AUD-<uuid:10>` | Code | Unique | Unique audit identifier |
| `entity_name` | String | Required | Table name (`TimeEntry`, `Employee`, etc.) | Text | Non-unique | Target entity |
| `record_id` | String | Required | Natural ID of target record | Text | Non-unique | Target identifier |
| `action` | String | Required | `CREATE`, `UPDATE`, `APPROVE`, `REJECT`, `RESOLVE`, `EXPORT`, `RECALCULATE`, `DUPLICATE_VOID` | Enum | Non-unique | Executed action |
| `actor_role` | String | Required | `EMPLOYEE`, `MANAGER`, `HR`, `IT_OPS`, `ADMIN`, `SYSTEM` | Enum | Non-unique | Acting role |
| `actor_name` | String | Required | Name of person or automated service | Text | Non-unique | Non-empty identity |
| `old_values` | String | Optional | JSON string of prior attribute state | JSON | Non-unique | State history preservation |
| `new_values` | String | Optional | JSON string of modified attribute state | JSON | Non-unique | State history preservation |
| `reason` | String | Optional | Business rationale for change | Text | Non-unique | Required for governance audit |
| `timestamp` | DateTime | Required | ISO 8601 UTC timestamp | Timestamp | Non-unique | Event execution timestamp |

