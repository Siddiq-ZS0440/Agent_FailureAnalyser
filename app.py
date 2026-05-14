from __future__ import annotations

from pathlib import Path
import tempfile

import pandas as pd
import streamlit as st

from report_failure_extractor_v1 import ProfileDrivenReportAnalyzer
from report_failure_pipeline import run_pipeline

st.set_page_config(page_title="Automation Report Failure Analyzer", layout="wide")
st.title("Automation Report Failure Analyzer")
st.caption("Upload an HTML automation report, optionally choose a report type, then generate categorized Excel output.")

BASE_DIR = Path(__file__).resolve().parent
PROFILE_INDEX = BASE_DIR / "report_profiles.json"
PROFILES_DIR = BASE_DIR / "profiles"
CATEGORIZATION = BASE_DIR / "failure_categorization.json"
RESULTS_ROOT = BASE_DIR / "Results"


if "ui_logs" not in st.session_state:
    st.session_state.ui_logs = []
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None
if "analysis_error" not in st.session_state:
    st.session_state.analysis_error = ""
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0
if "selected_report_type" not in st.session_state:
    st.session_state.selected_report_type = "Auto Match"


def get_report_types() -> list[str]:
    analyzer = ProfileDrivenReportAnalyzer(
        profile_index_path=str(PROFILE_INDEX),
        profiles_dir=str(PROFILES_DIR),
    )
    return ["Auto Match"] + analyzer.list_available_report_types()


report_types = get_report_types()

log_placeholder = st.empty()
status_placeholder = st.empty()


def ui_log(message: str) -> None:
    st.session_state.ui_logs.append(message)
    log_placeholder.code("\n".join(st.session_state.ui_logs[-200:]), language="text")


def reset_analysis_state(clear_logs: bool = True, clear_upload: bool = False) -> None:
    st.session_state.analysis_result = None
    st.session_state.analysis_error = ""
    if clear_logs:
        st.session_state.ui_logs = []
    if clear_upload:
        st.session_state.uploader_key += 1
        st.session_state.pop("selected_report_type", None)


with st.sidebar:
    st.header("Inputs")
    uploaded_file = st.file_uploader(
        "Attach HTML report",
        type=["html", "htm"],
        accept_multiple_files=False,
        key=f"uploaded_file_{st.session_state.uploader_key}",
    )
    selected_report_type = st.selectbox(
        "Report type",
        report_types,
        index=report_types.index(st.session_state.selected_report_type)
        if st.session_state.selected_report_type in report_types
        else 0,
        key="selected_report_type",
    )
    run_clicked = st.button("Analyze Report", type="primary", use_container_width=True)
    reset_clicked = st.button("Upload New Report / Reset Analysis", use_container_width=True)

if reset_clicked:
    reset_analysis_state(clear_logs=True, clear_upload=True)
    st.rerun()

log_placeholder.code("\n".join(st.session_state.ui_logs[-200:]), language="text")

if run_clicked:
    if uploaded_file is None:
        reset_analysis_state(clear_logs=False, clear_upload=False)
        st.session_state.analysis_error = "Please attach an HTML report file."
    else:
        reset_analysis_state(clear_logs=True, clear_upload=False)
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                temp_html_path = Path(tmp_dir) / uploaded_file.name
                temp_html_path.write_bytes(uploaded_file.getbuffer())

                chosen_report_type = "" if selected_report_type == "Auto Match" else selected_report_type
                ui_log("INFO: Analysis started")
                ui_log(f"INFO: Uploaded report: {uploaded_file.name}")
                if chosen_report_type:
                    ui_log(f"INFO: Using selected report type: {chosen_report_type}")
                else:
                    ui_log("INFO: Using auto report type detection")

                result = run_pipeline(
                    html_report=str(temp_html_path),
                    report_type=chosen_report_type,
                    profile_index=str(PROFILE_INDEX),
                    profiles_dir=str(PROFILES_DIR),
                    categorization_config=str(CATEGORIZATION),
                    results_root=str(RESULTS_ROOT),
                    ui_callback=ui_log,
                )

            st.session_state.analysis_result = result
            st.session_state.analysis_error = ""
            ui_log("INFO: Analysis completed successfully")
        except Exception as exc:
            st.session_state.analysis_result = None
            st.session_state.analysis_error = f"Analysis failed: {exc}"
            ui_log(f"ERROR: {exc}")

if st.session_state.analysis_error:
    status_placeholder.error(st.session_state.analysis_error)
elif st.session_state.analysis_result:
    status_placeholder.success("Analysis completed successfully.")
else:
    status_placeholder.info("Attach an HTML report, optionally choose a report type, and click Analyze Report.")

if st.session_state.analysis_result:
    result = st.session_state.analysis_result
    data = result["categorized_data"]

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Tests", data.get("total_test_count", 0))
    col2.metric("Failed Tests", data.get("failed_test_count", 0))
    col3.metric("Report Type", data.get("report_type", ""))

    st.subheader("Summary")
    summary_rows = [
        {"Field": "Source HTML File", "Value": data.get("source_html_file", "")},
        {"Field": "Report Name", "Value": data.get("report_name", "")},
        {"Field": "Report Type", "Value": data.get("report_type", "")},
        {"Field": "Total Test Count", "Value": data.get("total_test_count", 0)},
        {"Field": "Failed Test Count", "Value": data.get("failed_test_count", 0)},
        {"Field": "Run Folder", "Value": result.get("run_dir", "")},
        {"Field": "Log File", "Value": result.get("log_path", "")},
    ]
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    category_summary = data.get("failure_category_summary", {}) or {}
    if category_summary:
        st.subheader("Category Summary")
        summary_df = pd.DataFrame(
            [{"Failure Category": key, "Count": value} for key, value in category_summary.items()]
        ).sort_values(["Count", "Failure Category"], ascending=[False, True])
        st.dataframe(summary_df, use_container_width=True, hide_index=True)
    else:
        st.info("No category summary was generated.")

    st.subheader("Details")
    details_df = pd.DataFrame(data.get("categorized_failed_test_list", []))
    if not details_df.empty:
        st.dataframe(details_df, use_container_width=True, hide_index=True)
    else:
        st.info("No failed test details were found.")

    excel_path = Path(result["excel_path"])
    st.download_button(
        "Download Excel Report",
        data=excel_path.read_bytes(),
        file_name=excel_path.name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    with st.expander("Generated file paths", expanded=False):
        st.json(
            {
                "run_dir": result["run_dir"],
                "extraction_json": result["extraction_json"],
                "categorization_json": result["categorization_json"],
                "excel_path": result["excel_path"],
                "log_path": result["log_path"],
            }
        )
