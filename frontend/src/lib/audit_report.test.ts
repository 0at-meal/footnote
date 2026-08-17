import { describe, it, expect } from 'vitest'
import {
  buildAuditReportDownloadUrl,
  buildAuditReportFilename,
  canDownloadAuditReport,
} from './audit_report'

describe('audit_report helpers', () => {
  describe('buildAuditReportDownloadUrl', () => {
    it('constructs correct URL without trailing slash', () => {
      const url = buildAuditReportDownloadUrl('http://localhost:8000', 'job-123')
      expect(url).toBe('http://localhost:8000/api/jobs/job-123/audit-report')
    })

    it('strips trailing slashes from apiBase', () => {
      const url = buildAuditReportDownloadUrl('http://localhost:8000///', 'job-123')
      expect(url).toBe('http://localhost:8000/api/jobs/job-123/audit-report')
    })

    it('URI-encodes special characters in jobId', () => {
      const url = buildAuditReportDownloadUrl('http://localhost:8000', 'job/special?id')
      expect(url).toBe('http://localhost:8000/api/jobs/job%2Fspecial%3Fid/audit-report')
    })
  })

  describe('buildAuditReportFilename', () => {
    it('formats filename matching backend attachment header convention', () => {
      expect(buildAuditReportFilename('job-456')).toBe('audit_report_job-456.pdf')
    })
  })

  describe('canDownloadAuditReport', () => {
    it('allows download only for completed jobs (done)', () => {
      expect(canDownloadAuditReport('done')).toBe(true)
      expect(canDownloadAuditReport('queued')).toBe(false)
      expect(canDownloadAuditReport('extracting')).toBe(false)
      expect(canDownloadAuditReport('failed')).toBe(false)
    })
  })
})
