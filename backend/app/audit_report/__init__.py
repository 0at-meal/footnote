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

__all__ = [
    "AuditReportCompiler",
    "ClassifierAuditEntry",
    "ClassifierAuditSummary",
    "CompiledAuditDataset",
    "DriftAuditSummary",
    "JobNotFoundError",
    "ManualOverrideItem",
    "ModelNotCompleteError",
    "ProvenanceMatrixItem",
    "ReconciliationSummaryItem",
    "ReportMetadata",
    "compile_audit_dataset",
]
