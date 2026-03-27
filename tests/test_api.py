"""Tests for Flask API endpoints."""

import pytest
import json


class TestAuthEndpoints:
    """Tests for authentication."""

    def test_login_page_accessible(self, client):
        response = client.get('/login')
        assert response.status_code == 200

    def test_login_success(self, client):
        response = client.post('/login', data={
            'username': 'admin',
            'password': 'admin'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_login_failure(self, client):
        response = client.post('/login', data={
            'username': 'admin',
            'password': 'wrong'
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b'Invalid' in response.data or b'incorrect' in response.data.lower()

    def test_unauthenticated_redirect(self, client):
        response = client.get('/')
        assert response.status_code in (302, 401)


class TestFeedbackEndpoints:
    """Tests for feedback API."""

    def test_submit_feedback(self, auth_client):
        response = auth_client.post('/api/feedback', json={
            'category': 'Bug Report',
            'priority': 'High',
            'message': 'Test feedback message',
            'page': 'Dashboard'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

    def test_submit_feedback_with_status(self, auth_client):
        """New feedback should get 'New' status."""
        auth_client.post('/api/feedback', json={
            'category': 'Bug Report',
            'priority': 'Medium',
            'message': 'Test with status'
        })
        response = auth_client.get('/api/feedback')
        data = response.get_json()
        if data['feedback']:
            # Most recent entry should have 'New' status
            latest = data['feedback'][0]
            assert latest.get('status') == 'New'

    def test_submit_feedback_missing_message(self, auth_client):
        response = auth_client.post('/api/feedback', json={
            'category': 'Bug Report',
            'priority': 'High',
            'message': ''
        })
        assert response.status_code == 400

    def test_get_feedback_admin(self, auth_client):
        response = auth_client.get('/api/feedback')
        assert response.status_code == 200
        data = response.get_json()
        assert 'feedback' in data

    def test_update_feedback_status(self, auth_client):
        # Submit a feedback first
        auth_client.post('/api/feedback', json={
            'category': 'Bug Report',
            'priority': 'Medium',
            'message': 'Status test'
        })
        # Update its status
        response = auth_client.put('/api/feedback/0/status', json={
            'status': 'In-Work'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

    def test_update_feedback_status_visible_in_mine(self, auth_client):
        """Status change by admin should be visible in /api/feedback/mine."""
        # Submit feedback
        auth_client.post('/api/feedback', json={
            'category': 'Bug Report',
            'priority': 'Low',
            'message': 'Fix visibility test'
        })
        # Update status to Fixed (index 0 = newest in reversed list)
        response = auth_client.put('/api/feedback/0/status', json={
            'status': 'Fixed'
        })
        assert response.get_json()['success'] is True

        # Verify the status is reflected in the user's own feedback view
        response = auth_client.get('/api/feedback/mine')
        data = response.get_json()
        matching = [f for f in data['feedback'] if f['message'] == 'Fix visibility test']
        assert len(matching) == 1
        assert matching[0]['status'] == 'Fixed'

    def test_update_feedback_invalid_status(self, auth_client):
        response = auth_client.put('/api/feedback/0/status', json={
            'status': 'InvalidStatus'
        })
        assert response.status_code == 400


class TestNotificationEndpoints:
    """Tests for notification API."""

    def test_get_notifications(self, auth_client):
        response = auth_client.get('/api/notifications')
        assert response.status_code == 200
        data = response.get_json()
        assert 'notifications' in data
        assert 'unread_count' in data

    def test_mark_all_read(self, auth_client):
        response = auth_client.post('/api/notifications/read-all')
        assert response.status_code == 200

    def test_mark_nonexistent_read(self, auth_client):
        response = auth_client.post('/api/notifications/NTF-nonexistent/read')
        assert response.status_code == 404


class TestAlertEndpoints:
    """Tests for alert API."""

    def test_get_alerts_empty(self, auth_client):
        response = auth_client.get('/api/alerts')
        assert response.status_code == 200
        data = response.get_json()
        assert 'alerts' in data

    def test_generate_alerts_no_schedule(self, auth_client):
        """Generate alerts with no schedule data should return error."""
        response = auth_client.post('/api/alerts/generate')
        assert response.status_code in (200, 400)


class TestPageAccess:
    """Tests for page route accessibility."""

    def test_dashboard(self, auth_client):
        response = auth_client.get('/')
        assert response.status_code == 200

    def test_upload_page(self, auth_client):
        response = auth_client.get('/upload')
        assert response.status_code == 200

    def test_schedule_page(self, auth_client):
        response = auth_client.get('/schedule')
        assert response.status_code == 200

    def test_reports_page(self, auth_client):
        response = auth_client.get('/reports')
        assert response.status_code == 200

    def test_special_requests_page(self, auth_client):
        response = auth_client.get('/special-requests')
        assert response.status_code == 200

    def test_planner_page_admin(self, auth_client):
        response = auth_client.get('/planner')
        assert response.status_code == 200

    def test_update_log_page(self, auth_client):
        response = auth_client.get('/updates')
        assert response.status_code == 200

    def test_alerts_page(self, auth_client):
        response = auth_client.get('/alerts')
        assert response.status_code == 200

    def test_notifications_page(self, auth_client):
        response = auth_client.get('/notifications')
        assert response.status_code == 200


class TestSpecialRequestPurge:
    """Tests for the 14-day pending request purge logic."""

    def _make_request(self, wo, days_old, status='pending', matched=True):
        from datetime import datetime, timedelta
        submitted = (datetime.now() - timedelta(days=days_old)).isoformat()
        return {
            'id': f'SR-{wo}',
            'wo_number': wo,
            'status': status,
            'submitted_at': submitted,
            'matched': matched,
        }

    def test_recent_pending_not_expired(self, auth_client, app):
        """Pending requests < 14 days old should not be purged."""
        import gcs_storage
        req = self._make_request('WO-RECENT', days_old=5)
        gcs_storage.save_special_requests([req])

        response = auth_client.get('/api/special-requests')
        data = response.get_json()
        statuses = {r['id']: r['status'] for r in data['requests']}
        assert statuses.get('SR-WO-RECENT') == 'pending'

    def test_old_pending_gets_expired(self, auth_client, app):
        """Pending requests >= 14 days old should be expired."""
        import gcs_storage
        req = self._make_request('WO-OLD', days_old=15)
        gcs_storage.save_special_requests([req])

        response = auth_client.get('/api/special-requests')
        data = response.get_json()
        # Old pending should be expired and filtered out of 'pending' query
        pending_ids = [r['id'] for r in data['requests'] if r['status'] == 'pending']
        assert 'SR-WO-OLD' not in pending_ids

    def test_approved_request_never_purged(self, auth_client, app):
        """Approved requests older than 14 days must NOT be expired."""
        import gcs_storage
        req = self._make_request('WO-APPROVED', days_old=30, status='approved')
        gcs_storage.save_special_requests([req])

        response = auth_client.get('/api/special-requests')
        data = response.get_json()
        statuses = {r['id']: r['status'] for r in data['requests']}
        assert statuses.get('SR-WO-APPROVED') == 'approved'

    def test_unmatched_mode_b_uses_28_day_rule(self, auth_client, app):
        """Unmatched Mode B placeholder at 20 days should NOT be expired (uses 28-day rule)."""
        import gcs_storage
        req = self._make_request('WO-MODEB', days_old=20, matched=False)
        gcs_storage.save_special_requests([req])

        response = auth_client.get('/api/special-requests')
        data = response.get_json()
        statuses = {r['id']: r['status'] for r in data['requests']}
        # 20 days, unmatched Mode B: 28-day rule applies, should still be pending
        assert statuses.get('SR-WO-MODEB') == 'pending'


class TestFileHotListEndpoint:
    """Tests for GET /api/planner/file-hot-list."""

    def test_returns_empty_when_no_loader(self, auth_client, app):
        """Should return empty entries list when no planner session is active."""
        import app as app_module
        app_module.planner_state['loader'] = None

        response = auth_client.get('/api/planner/file-hot-list')
        assert response.status_code == 200
        data = response.get_json()
        assert data['entries'] == []

    def test_returns_entries_from_loader(self, auth_client, app):
        """Should return serialized hot list entries when loader has them."""
        from datetime import date
        import app as app_module

        class MockLoader:
            hot_list_entries = [
                {
                    'wo_number': 'WO-HOT-1',
                    'is_asap': True,
                    'need_by_date': None,
                    'rubber_override': None,
                    'comments': 'Rush job',
                    'customer': 'Acme Corp',
                    'description': 'Test stator',
                },
                {
                    'wo_number': 'WO-HOT-2',
                    'is_asap': False,
                    'need_by_date': date(2026, 3, 15),
                    'rubber_override': 'XE',
                    'comments': '',
                    'customer': 'Beta Ltd',
                    'description': 'Reline',
                },
            ]

        app_module.planner_state['loader'] = MockLoader()

        response = auth_client.get('/api/planner/file-hot-list')
        assert response.status_code == 200
        data = response.get_json()
        entries = data['entries']
        assert len(entries) == 2
        assert entries[0]['wo_number'] == 'WO-HOT-1'
        assert entries[0]['is_asap'] is True
        assert entries[0]['need_by_date'] is None
        assert entries[1]['wo_number'] == 'WO-HOT-2'
        assert entries[1]['need_by_date'] == '2026-03-15'
        assert entries[1]['rubber_override'] == 'XE'

        # Cleanup
        app_module.planner_state['loader'] = None

    def test_unauthenticated_denied(self, client):
        """Unauthenticated access should be redirected."""
        response = client.get('/api/planner/file-hot-list')
        assert response.status_code in (302, 401)
