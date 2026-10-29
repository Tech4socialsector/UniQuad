frappe.pages['slcm-module-flow'].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: 'SLCM Module Flow',
		single_column: true,
	});

	$(wrapper).find('.page-content').css({ padding: '0', background: '#0f172a' });

	$(wrapper).find('.page-content').html(`
	<style>
	* { box-sizing: border-box; margin: 0; padding: 0; }
	.smf-wrap { font-family: var(--font-stack,'Inter',sans-serif); background:#0f172a; color:#e2e8f0; min-height:100vh; padding:28px 36px 80px; }

	/* Header */
	.smf-header { display:flex; align-items:center; gap:14px; margin-bottom:24px; padding:18px 22px; background:#1e293b; border-radius:14px; border:1px solid #334155; }
	.smf-hicon  { width:46px; height:46px; background:linear-gradient(135deg,#3b82f6,#8b5cf6); border-radius:12px; display:flex; align-items:center; justify-content:center; font-size:22px; flex-shrink:0; }
	.smf-htitle { font-size:20px; font-weight:800; color:#f1f5f9; }
	.smf-hsub   { font-size:12px; color:#64748b; margin-top:2px; }
	.smf-hbadge { margin-left:auto; background:#1e3a5f; color:#60a5fa; border:1px solid #2563eb44; border-radius:20px; padding:6px 16px; font-size:12px; font-weight:600; }

	/* Legend */
	.smf-legend { display:flex; flex-wrap:wrap; gap:10px; margin-bottom:20px; padding:14px 18px; background:#1e293b; border-radius:12px; border:1px solid #334155; }
	.smf-legend-title { font-size:10px; font-weight:700; color:#64748b; text-transform:uppercase; letter-spacing:.8px; width:100%; margin-bottom:4px; }
	.smf-legend-item { display:flex; align-items:center; gap:6px; font-size:11px; color:#94a3b8; }
	.smf-legend-dot  { width:10px; height:10px; border-radius:3px; flex-shrink:0; }

	/* Top actions */
	.smf-actions { display:flex; gap:10px; margin-bottom:20px; align-items:center; }
	.smf-btn { padding:8px 16px; border-radius:8px; font-size:12px; font-weight:600; cursor:pointer; border:1.5px solid #334155; background:#1e293b; color:#94a3b8; transition:all .15s; }
	.smf-btn:hover { background:#263348; color:#e2e8f0; border-color:#475569; }
	.smf-tip { margin-left:auto; font-size:12px; color:#475569; }

	/* Module card */
	.smf-card { background:#1e293b; border:1px solid #334155; border-radius:16px; margin-bottom:10px; overflow:hidden; transition:border-color .2s; }
	.smf-card:hover { border-color:var(--accent,#3b82f6); }
	.smf-card-header { display:flex; align-items:center; gap:14px; padding:15px 20px; cursor:pointer; user-select:none; border-bottom:1px solid transparent; transition:background .15s; }
	.smf-card-header:hover { background:#263348; }
	.smf-card-header.open { border-bottom-color:#334155; }
	.smf-num  { width:28px; height:28px; border-radius:8px; background:var(--nbg,#1e3a5f); color:var(--accent,#60a5fa); font-size:12px; font-weight:800; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
	.smf-mname { font-size:15px; font-weight:700; color:#f1f5f9; flex:1; }
	.smf-mdesc { font-size:12px; color:#64748b; }
	.smf-marrow { font-size:11px; color:#475569; transition:transform .2s; }
	.smf-marrow.open { transform:rotate(90deg); }

	/* Card body */
	.smf-body { display:none; padding:18px 22px 22px; }
	.smf-body.open { display:block; }

	/* Flow row */
	.smf-row-label { font-size:10px; font-weight:700; color:#475569; text-transform:uppercase; letter-spacing:.8px; margin-bottom:6px; margin-top:14px; }
	.smf-row-label:first-child { margin-top:0; }
	.smf-flow { display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin-bottom:4px; }

	/* DocType chip */
	.smf-dt { display:inline-flex; align-items:center; gap:5px; padding:6px 12px; border-radius:8px; font-size:12px; font-weight:600; cursor:pointer; border:1.5px solid transparent; text-decoration:none; transition:all .15s; white-space:nowrap; }
	.smf-dt:hover { transform:translateY(-2px); box-shadow:0 4px 12px rgba(0,0,0,.35); }
	.smf-dt.c-blue   { background:#1e3a5f; color:#60a5fa; border-color:#2563eb44; }
	.smf-dt.c-blue:hover   { background:#2563eb; color:#fff; }
	.smf-dt.c-green  { background:#064e3b; color:#34d399; border-color:#05966944; }
	.smf-dt.c-green:hover  { background:#059669; color:#fff; }
	.smf-dt.c-yellow { background:#451a03; color:#fbbf24; border-color:#d9770644; }
	.smf-dt.c-yellow:hover { background:#d97706; color:#fff; }
	.smf-dt.c-red    { background:#450a0a; color:#f87171; border-color:#dc262644; }
	.smf-dt.c-red:hover    { background:#dc2626; color:#fff; }
	.smf-dt.c-purple { background:#2e1065; color:#c4b5fd; border-color:#7c3aed44; }
	.smf-dt.c-purple:hover { background:#7c3aed; color:#fff; }
	.smf-dt.c-teal   { background:#042f2e; color:#5eead4; border-color:#0d948844; }
	.smf-dt.c-teal:hover   { background:#0d9488; color:#fff; }
	.smf-dt.c-pink   { background:#500724; color:#f9a8d4; border-color:#db277744; }
	.smf-dt.c-pink:hover   { background:#db2777; color:#fff; }
	.smf-dt.c-orange { background:#431407; color:#fb923c; border-color:#ea580c44; }
	.smf-dt.c-orange:hover { background:#ea580c; color:#fff; }

	/* Arrow */
	.smf-arrow { color:#475569; font-size:14px; flex-shrink:0; }

	/* Status flow */
	.smf-status { display:flex; flex-wrap:wrap; align-items:center; gap:6px; margin-top:12px; padding:12px 16px; background:#0f172a; border-radius:10px; border:1px solid #1e293b; }
	.smf-status-lbl { font-size:10px; font-weight:700; color:#475569; text-transform:uppercase; letter-spacing:.8px; width:100%; margin-bottom:4px; }
	.sc { padding:4px 10px; border-radius:6px; font-size:11px; font-weight:600; }
	.sc-gray   { background:#1e293b; color:#94a3b8; }
	.sc-yellow { background:#451a03; color:#fbbf24; }
	.sc-blue   { background:#1e3a5f; color:#60a5fa; }
	.sc-green  { background:#064e3b; color:#34d399; }
	.sc-red    { background:#450a0a; color:#f87171; }
	.sc-purple { background:#2e1065; color:#c4b5fd; }
	.smf-sarrow { color:#334155; font-size:11px; }

	/* Connector */
	.smf-connector { display:flex; flex-direction:column; align-items:center; margin:3px 0; gap:1px; }
	.smf-conn-line  { width:2px; height:18px; background:linear-gradient(to bottom,#334155,#1e293b); }
	.smf-conn-dot   { width:8px; height:8px; border-radius:50%; background:#3b82f6; box-shadow:0 0 8px #3b82f644; }

	/* 2-col grid */
	.smf-2col { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
	@media(max-width:860px){ .smf-2col { grid-template-columns:1fr; } }
	</style>

	<div class="smf-wrap">

	  <!-- Header -->
	  <div class="smf-header">
	    <div class="smf-hicon">🎓</div>
	    <div>
	      <div class="smf-htitle">SLCM Module Flow</div>
	      <div class="smf-hsub">Click any DocType to open it · Click module header to expand/collapse</div>
	    </div>
	    <div class="smf-hbadge">11 Modules · 60+ DocTypes</div>
	  </div>

	  <!-- Legend -->
	  <div class="smf-legend">
	    <div class="smf-legend-title">DocType Colour Guide</div>
	    <div class="smf-legend-item"><div class="smf-legend-dot" style="background:#2563eb"></div>Core / Primary</div>
	    <div class="smf-legend-item"><div class="smf-legend-dot" style="background:#059669"></div>Status / Result</div>
	    <div class="smf-legend-item"><div class="smf-legend-dot" style="background:#d97706"></div>Configuration / Setup</div>
	    <div class="smf-legend-item"><div class="smf-legend-dot" style="background:#dc2626"></div>Alert / Exception</div>
	    <div class="smf-legend-item"><div class="smf-legend-dot" style="background:#7c3aed"></div>Schema / Template</div>
	    <div class="smf-legend-item"><div class="smf-legend-dot" style="background:#0d9488"></div>Tracking / Log</div>
	    <div class="smf-legend-item"><div class="smf-legend-dot" style="background:#db2777"></div>Report / Publish</div>
	    <div class="smf-legend-item"><div class="smf-legend-dot" style="background:#ea580c"></div>Tool / Utility</div>
	  </div>

	  <!-- Actions -->
	  <div class="smf-actions">
	    <button class="smf-btn" onclick="smfExpandAll()">Expand All</button>
	    <button class="smf-btn" onclick="smfCollapseAll()">Collapse All</button>
	    <span class="smf-tip">Click a DocType chip to navigate directly</span>
	  </div>

	  <!-- MODULE 1 — ADMISSION -->
	  <div class="smf-card" style="--accent:#3b82f6; --nbg:#1e3a5f;">
	    <div class="smf-card-header" onclick="smfToggle(this)">
	      <div class="smf-num">1</div>
	      <div><div class="smf-mname">Admission</div><div class="smf-mdesc">Application → Merit → Seat → Offer → Acceptance</div></div>
	      <div class="smf-marrow">▶</div>
	    </div>
	    <div class="smf-body">
	      <div class="smf-row-label">Main Flow</div>
	      <div class="smf-flow">
	        <a class="smf-dt c-blue" onclick="smfNav('applicant')">👤 Applicant</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-blue" onclick="smfNav('application')">📋 Application</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-yellow" onclick="smfNav('admission-round')">📅 Admission Round</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-green" onclick="smfNav('merit-list')">🏆 Merit List</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-green" onclick="smfNav('seat-allotment')">💺 Seat Allotment</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-green" onclick="smfNav('offer-letter')">📨 Offer Letter</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-green" onclick="smfNav('admission-acceptance')">✅ Admission Acceptance</a>
	      </div>
	      <div class="smf-status">
	        <div class="smf-status-lbl">Application Status Flow</div>
	        <span class="sc sc-gray">Draft</span><span class="smf-sarrow">→</span>
	        <span class="sc sc-yellow">Submitted</span><span class="smf-sarrow">→</span>
	        <span class="sc sc-blue">Under Review</span><span class="smf-sarrow">→</span>
	        <span class="sc sc-green">Accepted</span><span class="smf-sarrow">/</span>
	        <span class="sc sc-red">Rejected</span>
	      </div>
	    </div>
	  </div>

	  <div class="smf-connector"><div class="smf-conn-line"></div><div class="smf-conn-dot"></div><div class="smf-conn-line"></div></div>

	  <!-- MODULE 2 — STUDENT REGISTRATION -->
	  <div class="smf-card" style="--accent:#8b5cf6; --nbg:#2e1065;">
	    <div class="smf-card-header" onclick="smfToggle(this)">
	      <div class="smf-num" style="background:#2e1065;color:#c4b5fd;">2</div>
	      <div><div class="smf-mname">Student Registration</div><div class="smf-mdesc">10-step multi-department onboarding workflow</div></div>
	      <div class="smf-marrow">▶</div>
	    </div>
	    <div class="smf-body">
	      <div class="smf-row-label">Core DocTypes</div>
	      <div class="smf-flow">
	        <a class="smf-dt c-purple" onclick="smfNav('student-master')">🎓 Student Master</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-purple" onclick="smfNav('student-enrollment')">📚 Student Enrollment</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-teal" onclick="smfNav('student-workflow-history')">🔄 Workflow History</a>
	      </div>
	      <div class="smf-row-label">Supporting DocTypes</div>
	      <div class="smf-flow">
	        <a class="smf-dt c-purple" onclick="smfNav('student-parent')">👨‍👩‍👧 Student Parent</a>
	        <a class="smf-dt c-purple" onclick="smfNav('student-qualification')">🎓 Student Qualification</a>
	      </div>
	      <div class="smf-status">
	        <div class="smf-status-lbl">Registration Workflow (10 Steps)</div>
	        <span class="sc sc-gray">Draft</span><span class="smf-sarrow">→</span>
	        <span class="sc sc-yellow">Selected</span><span class="smf-sarrow">→</span>
	        <span class="sc sc-yellow">Pending REGO</span><span class="smf-sarrow">→</span>
	        <span class="sc sc-yellow">Pending FINO</span><span class="smf-sarrow">→</span>
	        <span class="sc sc-yellow">Pending Registration</span><span class="smf-sarrow">→</span>
	        <span class="sc sc-yellow">Pending Print &amp; Scan</span><span class="smf-sarrow">→</span>
	        <span class="sc sc-yellow">Pending Residences</span><span class="smf-sarrow">→</span>
	        <span class="sc sc-yellow">Pending IT</span><span class="smf-sarrow">→</span>
	        <span class="sc sc-blue">Final Verification</span><span class="smf-sarrow">→</span>
	        <span class="sc sc-green">Completed ✓</span>
	      </div>
	    </div>
	  </div>

	  <div class="smf-connector"><div class="smf-conn-line"></div><div class="smf-conn-dot"></div><div class="smf-conn-line"></div></div>

	  <!-- MODULE 3 — ACADEMIC SETUP -->
	  <div class="smf-card" style="--accent:#f59e0b; --nbg:#451a03;">
	    <div class="smf-card-header" onclick="smfToggle(this)">
	      <div class="smf-num" style="background:#451a03;color:#fbbf24;">3</div>
	      <div><div class="smf-mname">Academic Setup</div><div class="smf-mdesc">Foundation structure — must be configured before anything else</div></div>
	      <div class="smf-marrow">▶</div>
	    </div>
	    <div class="smf-body">
	      <div class="smf-row-label">Setup Order (Follow this sequence)</div>
	      <div class="smf-flow">
	        <a class="smf-dt c-yellow" onclick="smfNav('department')">🏛️ Department</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-yellow" onclick="smfNav('academic-year')">📅 Academic Year</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-yellow" onclick="smfNav('academic-term')">📆 Academic Term</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-yellow" onclick="smfNav('program')">🎓 Program</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-yellow" onclick="smfNav('course')">📖 Course</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-yellow" onclick="smfNav('curriculum')">🗺️ Curriculum</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-yellow" onclick="smfNav('student-batch-name')">👥 Student Batch</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-yellow" onclick="smfNav('classes')">📋 Classes</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-orange" onclick="smfNav('course-schedule')">🗓️ Course Schedule</a>
	      </div>
	    </div>
	  </div>

	  <div class="smf-connector"><div class="smf-conn-line"></div><div class="smf-conn-dot"></div><div class="smf-conn-line"></div></div>

	  <!-- MODULE 4 — ATTENDANCE -->
	  <div class="smf-card" style="--accent:#10b981; --nbg:#064e3b;">
	    <div class="smf-card-header" onclick="smfToggle(this)">
	      <div class="smf-num" style="background:#064e3b;color:#34d399;">4</div>
	      <div><div class="smf-mname">Attendance</div><div class="smf-mdesc">RFID / Manual marking → Summary → Exam eligibility</div></div>
	      <div class="smf-marrow">▶</div>
	    </div>
	    <div class="smf-body">
	      <div class="smf-row-label">RFID Setup</div>
	      <div class="smf-flow">
	        <a class="smf-dt c-yellow" onclick="smfNav('attendance-settings')">⚙️ Attendance Settings</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-teal" onclick="smfNav('rfid-device')">📡 RFID Device</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-teal" onclick="smfNav('student-rfid-card')">💳 Student RFID Card</a>
	      </div>
	      <div class="smf-row-label">Daily Flow</div>
	      <div class="smf-flow">
	        <a class="smf-dt c-green" onclick="smfNav('attendance-session')">📋 Attendance Session</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-orange" onclick="smfNav('student-attendance-tool')">🛠️ Attendance Tool</a>
	        <span class="smf-arrow">/</span>
	        <a class="smf-dt c-teal" onclick="smfNav('attendance-log')">📡 Attendance Log</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-green" onclick="smfNav('student-attendance')">✅ Student Attendance</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-green" onclick="smfNav('attendance-summary')">📊 Attendance Summary</a>
	      </div>
	      <div class="smf-row-label">If Below Minimum %</div>
	      <div class="smf-flow">
	        <a class="smf-dt c-red" onclick="smfNav('student-attendance-condonation')">📝 Condonation</a>
	        <span class="smf-arrow">/</span>
	        <a class="smf-dt c-red" onclick="smfNav('attendance-fa-mfa-reference')">🏥 FA / MFA Reference</a>
	      </div>
	    </div>
	  </div>

	  <div class="smf-connector"><div class="smf-conn-line"></div><div class="smf-conn-dot"></div><div class="smf-conn-line"></div></div>

	  <!-- MODULE 5 — ID CARD -->
	  <div class="smf-card" style="--accent:#06b6d4; --nbg:#042f2e;">
	    <div class="smf-card-header" onclick="smfToggle(this)">
	      <div class="smf-num" style="background:#042f2e;color:#5eead4;">5</div>
	      <div><div class="smf-mname">ID Card (IT Team)</div><div class="smf-mdesc">Template → Generate → Print → Issue → RFID</div></div>
	      <div class="smf-marrow">▶</div>
	    </div>
	    <div class="smf-body">
	      <div class="smf-row-label">Setup → Generation → Print</div>
	      <div class="smf-flow">
	        <a class="smf-dt c-purple" onclick="smfNav('id-card-template')">🎨 ID Card Template</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-orange" onclick="smfNav('id-card-generation-tool')">🛠️ Generation Tool</a>
	        <span class="smf-arrow">/</span>
	        <a class="smf-dt c-teal" onclick="smfNav('student-id-card')">🪪 Student ID Card</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-teal" onclick="smfNav('id-card-print-log')">🖨️ Print Log</a>
	      </div>
	      <div class="smf-status">
	        <div class="smf-status-lbl">Card Status Flow</div>
	        <span class="sc sc-gray">Draft</span><span class="smf-sarrow">→</span>
	        <span class="sc sc-green">Generated</span><span class="smf-sarrow">→</span>
	        <span class="sc sc-blue">Printed</span><span class="smf-sarrow">→</span>
	        <span class="sc sc-red">Cancelled / Expired</span>
	      </div>
	    </div>
	  </div>

	  <div class="smf-connector"><div class="smf-conn-line"></div><div class="smf-conn-dot"></div><div class="smf-conn-line"></div></div>

	  <!-- MODULE 6 — EXAMINATIONS -->
	  <div class="smf-card" style="--accent:#f43f5e; --nbg:#500724;">
	    <div class="smf-card-header" onclick="smfToggle(this)">
	      <div class="smf-num" style="background:#500724;color:#f9a8d4;">6</div>
	      <div><div class="smf-mname">Examinations</div><div class="smf-mdesc">Schema → Plan → Marks → Grade → Publish → Transcript</div></div>
	      <div class="smf-marrow">▶</div>
	    </div>
	    <div class="smf-body">
	      <div class="smf-row-label">One-Time Setup</div>
	      <div class="smf-flow">
	        <a class="smf-dt c-yellow" onclick="smfNav('examination-settings')">⚙️ Exam Settings</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-purple" onclick="smfNav('exam-assessment-type')">📝 Assessment Type</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-purple" onclick="smfNav('exam-component')">🧩 Exam Component</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-purple" onclick="smfNav('evaluation-schema')">📊 Evaluation Schema</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-purple" onclick="smfNav('grading-schema')">🏅 Grading Schema</a>
	      </div>
	      <div class="smf-row-label">Per Term Flow</div>
	      <div class="smf-flow">
	        <a class="smf-dt c-pink" onclick="smfNav('exam-plan')">📅 Exam Plan</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-pink" onclick="smfNav('exam-course-schedule')">🗓️ Exam Course Schedule</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-yellow" onclick="smfNav('access-result-settings')">🔐 Result Settings</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-pink" onclick="smfNav('student-course-marks')">📝 Student Course Marks</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-green" onclick="smfNav('student-result-publish')">📢 Result Publish</a>
	      </div>
	      <div class="smf-row-label">Re-Exam / Improvement</div>
	      <div class="smf-flow">
	        <a class="smf-dt c-red" onclick="smfNav('re-exam-course-setting')">⚙️ Re-Exam Setting</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-red" onclick="smfNav('re-exam-registration')">📋 Re-Exam Registration</a>
	        <span class="smf-arrow">/</span>
	        <a class="smf-dt c-orange" onclick="smfNav('improvement-exam-registration')">📈 Improvement Exam</a>
	      </div>
	      <div class="smf-row-label">Reports &amp; Transcript</div>
	      <div class="smf-flow">
	        <a class="smf-dt c-teal" onclick="smfNav('exam-barcode')">🔖 Exam Barcode</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-pink" onclick="smfNav('publish-result-setting')">📋 Publish Setting</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-purple" onclick="smfNav('transcript-template')">🎨 Transcript Template</a>
	        <span class="smf-arrow">→</span>
	        <a class="smf-dt c-green" onclick="smfNav('student-transcript')">📄 Student Transcript</a>
	      </div>
	      <div class="smf-status">
	        <div class="smf-status-lbl">Marks Status Flow</div>
	        <span class="sc sc-gray">Draft</span><span class="smf-sarrow">→</span>
	        <span class="sc sc-green">Submitted</span><span class="smf-sarrow">→</span>
	        <span class="sc sc-purple">Locked</span>
	      </div>
	    </div>
	  </div>

	  <div class="smf-connector"><div class="smf-conn-line"></div><div class="smf-conn-dot"></div><div class="smf-conn-line"></div></div>

	  <!-- 2-col grid -->
	  <div class="smf-2col">

	    <!-- MODULE 7 — VENUE BOOKING -->
	    <div class="smf-card" style="--accent:#14b8a6; --nbg:#042f2e;">
	      <div class="smf-card-header" onclick="smfToggle(this)">
	        <div class="smf-num" style="background:#042f2e;color:#5eead4;">7</div>
	        <div><div class="smf-mname">Venue Booking</div><div class="smf-mdesc">Room → Book → Approve → Swap</div></div>
	        <div class="smf-marrow">▶</div>
	      </div>
	      <div class="smf-body">
	        <div class="smf-flow">
	          <a class="smf-dt c-teal" onclick="smfNav('room')">🏛️ Room</a>
	          <span class="smf-arrow">→</span>
	          <a class="smf-dt c-teal" onclick="smfNav('venue-booking')">📅 Venue Booking</a>
	          <span class="smf-arrow">→</span>
	          <a class="smf-dt c-teal" onclick="smfNav('venue-swap-log')">🔄 Swap Log</a>
	        </div>
	        <div class="smf-status">
	          <div class="smf-status-lbl">Booking Status</div>
	          <span class="sc sc-yellow">Pending</span><span class="smf-sarrow">→</span>
	          <span class="sc sc-green">Approved</span><span class="smf-sarrow">/</span>
	          <span class="sc sc-red">Rejected</span>
	        </div>
	      </div>
	    </div>

	    <!-- MODULE 8 — HELPDESK -->
	    <div class="smf-card" style="--accent:#f87171; --nbg:#450a0a;">
	      <div class="smf-card-header" onclick="smfToggle(this)">
	        <div class="smf-num" style="background:#450a0a;color:#f87171;">8</div>
	        <div><div class="smf-mname">Helpdesk / Grievance</div><div class="smf-mdesc">Raise → Review → Resolve → Close</div></div>
	        <div class="smf-marrow">▶</div>
	      </div>
	      <div class="smf-body">
	        <div class="smf-flow">
	          <a class="smf-dt c-red" onclick="smfNav('student-grievance')">🎫 Student Grievance</a>
	        </div>
	        <div class="smf-status">
	          <div class="smf-status-lbl">Grievance Status</div>
	          <span class="sc sc-red">Open</span><span class="smf-sarrow">→</span>
	          <span class="sc sc-yellow">In Progress</span><span class="smf-sarrow">→</span>
	          <span class="sc sc-green">Resolved</span><span class="smf-sarrow">→</span>
	          <span class="sc sc-blue">Closed</span>
	        </div>
	      </div>
	    </div>

	    <!-- MODULE 9 — PROMOTION -->
	    <div class="smf-card" style="--accent:#a78bfa; --nbg:#2e1065;">
	      <div class="smf-card-header" onclick="smfToggle(this)">
	        <div class="smf-num" style="background:#2e1065;color:#c4b5fd;">9</div>
	        <div><div class="smf-mname">Promotion Policy</div><div class="smf-mdesc">Policy → Evaluate → Promote → Next Year</div></div>
	        <div class="smf-marrow">▶</div>
	      </div>
	      <div class="smf-body">
	        <div class="smf-flow">
	          <a class="smf-dt c-purple" onclick="smfNav('promotion-policy')">📜 Promotion Policy</a>
	          <span class="smf-arrow">→</span>
	          <a class="smf-dt c-purple" onclick="smfNav('student-promotion')">🎓 Student Promotion</a>
	        </div>
	        <div class="smf-status">
	          <div class="smf-status-lbl">Promotion Result</div>
	          <span class="sc sc-green">Promoted</span><span class="smf-sarrow">/</span>
	          <span class="sc sc-yellow">Conditional</span><span class="smf-sarrow">/</span>
	          <span class="sc sc-red">Not Promoted</span><span class="smf-sarrow">→</span>
	          <span class="sc sc-blue">Override</span>
	        </div>
	      </div>
	    </div>

	    <!-- MODULE 10 — REPORTS -->
	    <div class="smf-card" style="--accent:#f59e0b; --nbg:#451a03;">
	      <div class="smf-card-header" onclick="smfToggle(this)">
	        <div class="smf-num" style="background:#451a03;color:#fbbf24;">10</div>
	        <div><div class="smf-mname">Reports &amp; Analytics</div><div class="smf-mdesc">Script Reports + Analytics Dashboard</div></div>
	        <div class="smf-marrow">▶</div>
	      </div>
	      <div class="smf-body">
	        <div class="smf-row-label">Script Reports</div>
	        <div class="smf-flow">
	          <a class="smf-dt c-yellow" onclick="smfPage('query-report/Comprehensive Attendance Report')">📊 Attendance Report</a>
	          <a class="smf-dt c-yellow" onclick="smfPage('query-report/Daily Absentees')">📋 Daily Absentees</a>
	          <a class="smf-dt c-yellow" onclick="smfPage('query-report/Consecutive Absents')">⚠️ Consecutive Absents</a>
	          <a class="smf-dt c-yellow" onclick="smfPage('query-report/Course Completion')">✅ Course Completion</a>
	          <a class="smf-dt c-yellow" onclick="smfPage('query-report/Monthly Venue Booking Report')">🏛️ Venue Report</a>
	          <a class="smf-dt c-yellow" onclick="smfPage('query-report/Schema Change Audit')">🔍 Schema Audit</a>
	        </div>
	        <div class="smf-row-label">Dashboard Pages</div>
	        <div class="smf-flow">
	          <a class="smf-dt c-orange" onclick="smfPage('slcm-analytics-dashboard')">📈 Analytics Dashboard</a>
	          <a class="smf-dt c-orange" onclick="smfPage('examination-result')">📝 Exam Result</a>
	          <a class="smf-dt c-orange" onclick="smfPage('term-result')">🏆 Term Result</a>
	          <a class="smf-dt c-orange" onclick="smfPage('publish-result')">📢 Publish Results</a>
	          <a class="smf-dt c-orange" onclick="smfPage('transcript-management-page')">📄 Transcripts</a>
	        </div>
	      </div>
	    </div>

	  </div><!-- /2col -->

	  <div class="smf-connector"><div class="smf-conn-line"></div><div class="smf-conn-dot"></div><div class="smf-conn-line"></div></div>

	  <!-- MODULE 11 — EXPORT/IMPORT -->
	  <div class="smf-card" style="--accent:#94a3b8; --nbg:#1e293b;">
	    <div class="smf-card-header" onclick="smfToggle(this)">
	      <div class="smf-num" style="background:#1e293b;color:#94a3b8;">11</div>
	      <div><div class="smf-mname">Export &amp; Import</div><div class="smf-mdesc">Bulk data load and extract via Frappe Data Import tool</div></div>
	      <div class="smf-marrow">▶</div>
	    </div>
	    <div class="smf-body">
	      <div class="smf-flow">
	        <a class="smf-dt c-blue" onclick="smfNav('data-import')">⬆️ Data Import</a>
	        <span class="smf-arrow">→</span>
	        <span style="font-size:12px;color:#64748b;">Download Template → Fill → Upload → Validate → Import</span>
	      </div>
	      <div style="font-size:12px;color:#64748b;margin-top:10px;">
	        To Export: Open any DocType List → Menu (⋮) → Export → CSV / Excel
	      </div>
	    </div>
	  </div>

	</div><!-- /smf-wrap -->

	<script>
	  function smfToggle(header) {
	    const body  = header.nextElementSibling;
	    const arrow = header.querySelector('.smf-marrow');
	    const open  = body.classList.toggle('open');
	    header.classList.toggle('open', open);
	    arrow.classList.toggle('open', open);
	  }
	  function smfExpandAll() {
	    document.querySelectorAll('.smf-body').forEach(b => b.classList.add('open'));
	    document.querySelectorAll('.smf-card-header').forEach(h => h.classList.add('open'));
	    document.querySelectorAll('.smf-marrow').forEach(a => a.classList.add('open'));
	  }
	  function smfCollapseAll() {
	    document.querySelectorAll('.smf-body').forEach(b => b.classList.remove('open'));
	    document.querySelectorAll('.smf-card-header').forEach(h => h.classList.remove('open'));
	    document.querySelectorAll('.smf-marrow').forEach(a => a.classList.remove('open'));
	  }
	  function smfNav(dt) { frappe.set_route('List', frappe.model.unscrub(dt)); }
	  function smfPage(p) { frappe.set_route(p); }
	  smfExpandAll();
	<\/script>
	`);
};
