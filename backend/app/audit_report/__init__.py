"""
Audit Report Package (Feature 8).

Compiles and renders structured PDF audit reports verifying provenance,
manual overrides, classifier governance, and drift history for completed models.
"""

from app.audit_report.compiler import (
    AuditReportCompiler,
    JobNotFoundError,
    ModelNotCompleteError,
    compile_audit_dataset,
)
from app.audit_report.models import (
    ClassifierAuditEntry,
    ClassifierAuditSummary,
    CompiledAuditDataset,
    DriftAuditSummary,
    ManualOverrideItem,
    ProvenanceMatrixItem,
    ReconciliationSummaryItem,
    ReportMetadata,
)
from app.audit_report.renderer import (
    NumberedCanvas,
    render_audit_report_pdf,
)
from app.audit_report.repository import AuditReportRepository
from app.audit_report.service import generate_audit_report

__all__ = [
    "AuditReportCompiler",
    "AuditReportRepository",
    "ClassifierAuditEntry",
    "ClassifierAuditSummary",
    "CompiledAuditDataset",
    "DriftAuditSummary",
    "JobNotFoundError",
    "ManualOverrideItem",
    "ModelNotCompleteError",
    "NumberedCanvas",
    "ProvenanceMatrixItem",
    "ReconciliationSummaryItem",
    "ReportMetadata",
    "compile_audit_dataset",
    "generate_audit_report",
    "render_audit_report_pdf",
]
