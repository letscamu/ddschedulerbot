"""
Google Cloud Storage helper for EstradaBot.
Handles uploading, downloading, and listing files in GCS bucket.

Supports local filesystem fallback for development:
    Set USE_LOCAL_STORAGE=true in .env to use local filesystem instead of GCS.
"""

import os
import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


# ============== Storage Mode Detection ==============

USE_LOCAL_STORAGE = os.environ.get('USE_LOCAL_STORAGE', 'false').lower() == 'true'
LOCAL_STORAGE_DIR = os.environ.get('LOCAL_STORAGE_DIR',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))

if not USE_LOCAL_STORAGE:
    try:
        from google.cloud import storage
        from google.cloud.exceptions import NotFound
    except ImportError:
        print("[GCS] google-cloud-storage not installed, falling back to local storage")
        USE_LOCAL_STORAGE = True


# Bucket name - can be overridden via environment variable
BUCKET_NAME = os.environ.get('GCS_BUCKET', 'estradabot-files')

# Folders in the bucket
UPLOADS_FOLDER = 'uploads'
OUTPUTS_FOLDER = 'outputs'


# ============== Local Filesystem Storage ==============

def _local_path(folder: str, filename: str) -> str:
    """Get local filesystem path for a file."""
    base = os.path.abspath(LOCAL_STORAGE_DIR)
    path = os.path.join(base, folder, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def _local_upload_file(local_path: str, filename: str, folder: str = UPLOADS_FOLDER) -> str:
    dest = _local_path(folder, filename)
    shutil.copy2(local_path, dest)
    print(f"[LOCAL] Copied {filename} to {dest}")
    return f"{folder}/{filename}"


def _local_upload_file_object(file_obj, filename: str, folder: str = UPLOADS_FOLDER) -> str:
    dest = _local_path(folder, filename)
    file_obj.seek(0)
    with open(dest, 'wb') as f:
        f.write(file_obj.read())
    print(f"[LOCAL] Saved {filename} to {dest}")
    return f"{folder}/{filename}"


def _local_download_file(filename: str, local_path: str, folder: str = UPLOADS_FOLDER) -> bool:
    src = _local_path(folder, filename)
    if os.path.exists(src):
        shutil.copy2(src, local_path)
        return True
    return False


def _local_download_to_temp(filename: str, folder: str = UPLOADS_FOLDER) -> Optional[str]:
    src = _local_path(folder, filename)
    if not os.path.exists(src):
        return None
    suffix = Path(filename).suffix
    fd, temp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    shutil.copy2(src, temp_path)
    return temp_path


def _local_list_files(folder: str = UPLOADS_FOLDER, pattern: str = None) -> List[Dict]:
    base = os.path.join(os.path.abspath(LOCAL_STORAGE_DIR), folder)
    if not os.path.exists(base):
        return []
    files = []
    for f in os.listdir(base):
        full = os.path.join(base, f)
        if not os.path.isfile(full):
            continue
        if pattern and pattern.lower() not in f.lower():
            continue
        stat = os.stat(full)
        files.append({
            'name': f,
            'modified': datetime.fromtimestamp(stat.st_mtime),
            'size': stat.st_size
        })
    files.sort(key=lambda x: x['modified'], reverse=True)
    return files


def _local_delete_file(filename: str, folder: str = UPLOADS_FOLDER) -> bool:
    path = _local_path(folder, filename)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def _local_save_json(filepath: str, data) -> bool:
    full = os.path.join(os.path.abspath(LOCAL_STORAGE_DIR), filepath)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w') as f:
        json.dump(data, f, default=str)
    return True


def _local_load_json(filepath: str):
    full = os.path.join(os.path.abspath(LOCAL_STORAGE_DIR), filepath)
    if not os.path.exists(full):
        return None
    with open(full, 'r') as f:
        return json.load(f)


# ============== GCS Functions ==============


def get_client():
    """Get GCS client. Uses default credentials in Cloud Run."""
    if USE_LOCAL_STORAGE:
        return None
    return storage.Client()


def get_bucket():
    """Get the EstradaBot bucket."""
    if USE_LOCAL_STORAGE:
        return None
    client = get_client()
    return client.bucket(BUCKET_NAME)


def upload_file(local_path: str, filename: str, folder: str = UPLOADS_FOLDER) -> str:
    """
    Upload a file to GCS (or local filesystem in dev mode).

    Args:
        local_path: Path to local file
        filename: Name to use in GCS
        folder: Folder in bucket (uploads or outputs)

    Returns:
        GCS blob path
    """
    if USE_LOCAL_STORAGE:
        return _local_upload_file(local_path, filename, folder)
    bucket = get_bucket()
    blob_path = f"{folder}/{filename}"
    blob = bucket.blob(blob_path)
    blob.upload_from_filename(local_path)
    print(f"[GCS] Uploaded {filename} to gs://{BUCKET_NAME}/{blob_path}")
    return blob_path


def upload_file_object(file_obj, filename: str, folder: str = UPLOADS_FOLDER) -> str:
    """
    Upload a file object (like Flask's FileStorage) to GCS (or local filesystem in dev mode).

    Args:
        file_obj: File-like object with read() method
        filename: Name to use in GCS
        folder: Folder in bucket (uploads or outputs)

    Returns:
        GCS blob path
    """
    if USE_LOCAL_STORAGE:
        return _local_upload_file_object(file_obj, filename, folder)
    bucket = get_bucket()
    blob_path = f"{folder}/{filename}"
    blob = bucket.blob(blob_path)
    blob.upload_from_file(file_obj)
    print(f"[GCS] Uploaded {filename} to gs://{BUCKET_NAME}/{blob_path}")
    return blob_path


def download_file(filename: str, local_path: str, folder: str = UPLOADS_FOLDER) -> bool:
    """
    Download a file from GCS to local path.

    Args:
        filename: Name of file in GCS
        local_path: Local path to save to
        folder: Folder in bucket

    Returns:
        True if successful, False if not found
    """
    if USE_LOCAL_STORAGE:
        return _local_download_file(filename, local_path, folder)
    bucket = get_bucket()
    blob_path = f"{folder}/{filename}"
    blob = bucket.blob(blob_path)

    try:
        blob.download_to_filename(local_path)
        print(f"[GCS] Downloaded {filename} to {local_path}")
        return True
    except NotFound:
        print(f"[GCS] File not found: {blob_path}")
        return False


def download_to_temp(filename: str, folder: str = UPLOADS_FOLDER) -> Optional[str]:
    """
    Download a file from GCS to a temporary file.

    Args:
        filename: Name of file in GCS
        folder: Folder in bucket

    Returns:
        Path to temp file, or None if not found
    """
    if USE_LOCAL_STORAGE:
        return _local_download_to_temp(filename, folder)
    # Create temp file with same extension
    suffix = Path(filename).suffix
    fd, temp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)

    if download_file(filename, temp_path, folder):
        return temp_path
    else:
        os.unlink(temp_path)
        return None


def list_files(folder: str = UPLOADS_FOLDER, pattern: str = None) -> List[Dict]:
    """
    List files in a GCS folder.

    Args:
        folder: Folder in bucket
        pattern: Optional pattern to filter (e.g., "Core Mapping" to match files containing that string)

    Returns:
        List of dicts with name, modified, size
    """
    if USE_LOCAL_STORAGE:
        return _local_list_files(folder, pattern)
    bucket = get_bucket()
    prefix = f"{folder}/"

    files = []
    blobs = bucket.list_blobs(prefix=prefix)

    for blob in blobs:
        # Skip the folder itself
        if blob.name == prefix:
            continue

        filename = blob.name[len(prefix):]  # Remove prefix

        # Apply pattern filter if specified
        if pattern and pattern.lower() not in filename.lower():
            continue

        files.append({
            'name': filename,
            'modified': blob.updated,
            'size': blob.size
        })

    # Sort by modified time, newest first
    files.sort(key=lambda x: x['modified'], reverse=True)
    return files


def get_uploaded_files_info() -> Dict[str, Optional[Dict]]:
    """
    Get info about uploaded files, categorized by type.
    Similar to the original get_uploaded_files() but for GCS.

    Returns:
        Dict with keys: sales_order, shop_dispatch, hot_list, core_mapping, process_map
    """
    files = {
        'sales_order': None,
        'shop_dispatch': None,
        'hot_list': None,
        'core_mapping': None,
        'process_map': None,
        'dcp_report': None
    }

    all_files = list_files(UPLOADS_FOLDER)

    for file_info in all_files:
        filename = file_info['name']
        fname_lower = filename.lower().replace('_', ' ')

        if 'open sales order' in fname_lower or fname_lower.startswith('oso'):
            if files['sales_order'] is None or file_info['modified'] > files['sales_order']['modified']:
                files['sales_order'] = file_info
        elif 'shop dispatch' in fname_lower or fname_lower.startswith('sdr'):
            if files['shop_dispatch'] is None or file_info['modified'] > files['shop_dispatch']['modified']:
                files['shop_dispatch'] = file_info
        # Pegging Report removed in MVP 1.1
        elif 'hot list' in fname_lower or 'hot_list' in fname_lower:
            if files['hot_list'] is None or file_info['modified'] > files['hot_list']['modified']:
                files['hot_list'] = file_info
        elif 'core mapping' in fname_lower or 'core_mapping' in fname_lower:
            if files['core_mapping'] is None or file_info['modified'] > files['core_mapping']['modified']:
                files['core_mapping'] = file_info
        elif 'stators process' in fname_lower or 'process vsm' in fname_lower:
            if files['process_map'] is None or file_info['modified'] > files['process_map']['modified']:
                files['process_map'] = file_info
        elif 'dcpreport' in fname_lower or 'dcp report' in fname_lower:
            if files['dcp_report'] is None or file_info['modified'] > files['dcp_report']['modified']:
                files['dcp_report'] = file_info

    return files


def find_most_recent_file(pattern: str, folder: str = UPLOADS_FOLDER) -> Optional[str]:
    """
    Find the most recent file matching a pattern.

    Args:
        pattern: Pattern to match (e.g., "Core Mapping", "Open Sales Order")
        folder: Folder in bucket

    Returns:
        Filename of most recent match, or None
    """
    files = list_files(folder, pattern)
    if files:
        return files[0]['name']
    return None


def download_files_for_processing(local_dir: str) -> Dict[str, Optional[str]]:
    """
    Download all uploaded files to a local directory for processing.

    Args:
        local_dir: Local directory to download to

    Returns:
        Dict mapping file type to local path (or None if not found)
    """
    os.makedirs(local_dir, exist_ok=True)

    files_info = get_uploaded_files_info()
    local_paths = {}

    for file_type, info in files_info.items():
        if info:
            local_path = os.path.join(local_dir, info['name'])
            if download_file(info['name'], local_path, UPLOADS_FOLDER):
                local_paths[file_type] = local_path
            else:
                local_paths[file_type] = None
        else:
            local_paths[file_type] = None

    return local_paths


def delete_file(filename: str, folder: str = UPLOADS_FOLDER) -> bool:
    """
    Delete a file from GCS.

    Args:
        filename: Name of file in GCS
        folder: Folder in bucket

    Returns:
        True if deleted, False if not found
    """
    if USE_LOCAL_STORAGE:
        return _local_delete_file(filename, folder)
    bucket = get_bucket()
    blob_path = f"{folder}/{filename}"
    blob = bucket.blob(blob_path)

    try:
        blob.delete()
        print(f"[GCS] Deleted {blob_path}")
        return True
    except NotFound:
        print(f"[GCS] File not found for deletion: {blob_path}")
        return False


# ============== Schedule State Persistence ==============

SCHEDULE_STATE_FILE = 'state/current_schedule.json'


def save_schedule_state(schedule_data: dict) -> bool:
    """
    Save the current schedule state to GCS as JSON.

    Args:
        schedule_data: Dict with stats, reports, generated_at, and serialized orders

    Returns:
        True if saved successfully
    """
    if USE_LOCAL_STORAGE:
        try:
            _local_save_json(SCHEDULE_STATE_FILE, schedule_data)
            print(f"[LOCAL] Saved schedule state to {SCHEDULE_STATE_FILE}")
            return True
        except Exception as e:
            print(f"[LOCAL] Failed to save schedule state: {e}")
            return False

    bucket = get_bucket()
    blob = bucket.blob(SCHEDULE_STATE_FILE)

    try:
        json_data = json.dumps(schedule_data, default=str)
        blob.upload_from_string(json_data, content_type='application/json')
        print(f"[GCS] Saved schedule state to {SCHEDULE_STATE_FILE}")
        return True
    except Exception as e:
        print(f"[GCS] Failed to save schedule state: {e}")
        return False


def load_schedule_state() -> Optional[dict]:
    """
    Load the current schedule state from GCS.

    Returns:
        Schedule data dict, or None if not found
    """
    if USE_LOCAL_STORAGE:
        try:
            data = _local_load_json(SCHEDULE_STATE_FILE)
            if data:
                print(f"[LOCAL] Loaded schedule state from {SCHEDULE_STATE_FILE}")
            return data
        except Exception as e:
            print(f"[LOCAL] Failed to load schedule state: {e}")
            return None

    bucket = get_bucket()
    blob = bucket.blob(SCHEDULE_STATE_FILE)

    try:
        json_data = blob.download_as_text()
        data = json.loads(json_data)
        print(f"[GCS] Loaded schedule state from {SCHEDULE_STATE_FILE}")
        return data
    except NotFound:
        print(f"[GCS] No schedule state found")
        return None
    except Exception as e:
        print(f"[GCS] Failed to load schedule state: {e}")
        return None


# ============== User Feedback Persistence ==============

FEEDBACK_FILE = 'state/user_feedback.json'


def save_feedback(feedback_entry: dict) -> bool:
    """
    Append a feedback entry to the feedback JSON file.

    Args:
        feedback_entry: Dict with category, priority, page, message, username, submitted_at

    Returns:
        True if saved successfully
    """
    existing = load_feedback()
    existing.append(feedback_entry)

    if USE_LOCAL_STORAGE:
        try:
            _local_save_json(FEEDBACK_FILE, existing)
            print(f"[LOCAL] Saved feedback ({len(existing)} total entries)")
            return True
        except Exception as e:
            print(f"[LOCAL] Failed to save feedback: {e}")
            return False

    bucket = get_bucket()
    blob = bucket.blob(FEEDBACK_FILE)

    try:
        json_data = json.dumps(existing, default=str)
        blob.upload_from_string(json_data, content_type='application/json')
        print(f"[GCS] Saved feedback ({len(existing)} total entries)")
        return True
    except Exception as e:
        print(f"[GCS] Failed to save feedback: {e}")
        return False


def load_feedback() -> list:
    """
    Load all feedback entries.

    Returns:
        List of feedback dicts, newest first
    """
    if USE_LOCAL_STORAGE:
        try:
            data = _local_load_json(FEEDBACK_FILE)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    bucket = get_bucket()
    blob = bucket.blob(FEEDBACK_FILE)

    try:
        json_data = blob.download_as_text()
        data = json.loads(json_data)
        return data if isinstance(data, list) else []
    except NotFound:
        return []
    except Exception as e:
        print(f"[GCS] Failed to load feedback: {e}")
        return []


def update_feedback_dev_status(index: int, dev_status: str, updated_by: str = 'pipeline') -> bool:
    """
    Update the dev_status of a feedback entry by index.

    Args:
        index: Index in the feedback list (0-based, storage order)
        dev_status: New status - 'unprocessed', 'ingested', 'actioned', 'closed'
        updated_by: Who updated the status (default: 'pipeline')

    Returns:
        True if updated successfully
    """
    valid_statuses = ['unprocessed', 'ingested', 'actioned', 'closed']
    if dev_status not in valid_statuses:
        print(f"[Feedback] Invalid dev_status: {dev_status}")
        return False

    entries = load_feedback()
    if index < 0 or index >= len(entries):
        print(f"[Feedback] Index {index} out of range")
        return False

    entries[index]['dev_status'] = dev_status
    entries[index]['dev_status_updated_at'] = datetime.now().isoformat()
    entries[index]['dev_status_updated_by'] = updated_by

    if USE_LOCAL_STORAGE:
        try:
            _local_save_json(FEEDBACK_FILE, entries)
            return True
        except Exception as e:
            print(f"[LOCAL] Failed to update feedback dev_status: {e}")
            return False

    bucket = get_bucket()
    blob = bucket.blob(FEEDBACK_FILE)
    try:
        blob.upload_from_string(
            json.dumps(entries, default=str),
            content_type='application/json'
        )
        return True
    except Exception as e:
        print(f"[GCS] Failed to update feedback dev_status: {e}")
        return False


# ============== Special Request Persistence ==============

SPECIAL_REQUESTS_FILE = 'state/special_requests.json'


def save_special_requests(requests: list) -> bool:
    """
    Save all special requests.

    Args:
        requests: List of special request dicts

    Returns:
        True if saved successfully
    """
    if USE_LOCAL_STORAGE:
        try:
            _local_save_json(SPECIAL_REQUESTS_FILE, requests)
            print(f"[LOCAL] Saved special requests ({len(requests)} total)")
            return True
        except Exception as e:
            print(f"[LOCAL] Failed to save special requests: {e}")
            return False

    bucket = get_bucket()
    blob = bucket.blob(SPECIAL_REQUESTS_FILE)

    try:
        json_data = json.dumps(requests, default=str)
        blob.upload_from_string(json_data, content_type='application/json')
        print(f"[GCS] Saved special requests ({len(requests)} total)")
        return True
    except Exception as e:
        print(f"[GCS] Failed to save special requests: {e}")
        return False


def load_special_requests() -> list:
    """
    Load all special requests.

    Returns:
        List of special request dicts
    """
    if USE_LOCAL_STORAGE:
        try:
            data = _local_load_json(SPECIAL_REQUESTS_FILE)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    bucket = get_bucket()
    blob = bucket.blob(SPECIAL_REQUESTS_FILE)

    try:
        json_data = blob.download_as_text()
        data = json.loads(json_data)
        return data if isinstance(data, list) else []
    except NotFound:
        return []
    except Exception as e:
        print(f"[GCS] Failed to load special requests: {e}")
        return []


# ============== Published Schedule Persistence ==============

PUBLISHED_SCHEDULE_FILE = 'state/published_schedule.json'


def save_published_schedule(schedule_data: dict) -> bool:
    """
    Save the published (finalized) schedule.
    This is the working schedule visible to all users.

    Args:
        schedule_data: Dict with schedule info, orders, stats, mode config

    Returns:
        True if saved successfully
    """
    if USE_LOCAL_STORAGE:
        try:
            _local_save_json(PUBLISHED_SCHEDULE_FILE, schedule_data)
            print(f"[LOCAL] Published schedule saved")
            return True
        except Exception as e:
            print(f"[LOCAL] Failed to save published schedule: {e}")
            return False

    bucket = get_bucket()
    blob = bucket.blob(PUBLISHED_SCHEDULE_FILE)

    try:
        json_data = json.dumps(schedule_data, default=str)
        blob.upload_from_string(json_data, content_type='application/json')
        print(f"[GCS] Published schedule saved")
        return True
    except Exception as e:
        print(f"[GCS] Failed to save published schedule: {e}")
        return False


def load_published_schedule() -> Optional[dict]:
    """
    Load the published schedule.

    Returns:
        Published schedule dict, or None if not found
    """
    if USE_LOCAL_STORAGE:
        try:
            data = _local_load_json(PUBLISHED_SCHEDULE_FILE)
            if data:
                print(f"[LOCAL] Loaded published schedule")
            return data
        except Exception as e:
            print(f"[LOCAL] Failed to load published schedule: {e}")
            return None

    bucket = get_bucket()
    blob = bucket.blob(PUBLISHED_SCHEDULE_FILE)

    try:
        json_data = blob.download_as_text()
        data = json.loads(json_data)
        print(f"[GCS] Loaded published schedule")
        return data
    except NotFound:
        print(f"[GCS] No published schedule found")
        return None
    except Exception as e:
        print(f"[GCS] Failed to load published schedule: {e}")
        return None


# ============== Simulation Data Persistence ==============

SIMULATION_DATA_FILE = 'state/simulation_data.json'


def save_simulation_data(sim_data: dict) -> bool:
    """Save pre-formatted simulation data for the visual factory floor."""
    if USE_LOCAL_STORAGE:
        try:
            _local_save_json(SIMULATION_DATA_FILE, sim_data)
            print(f"[LOCAL] Simulation data saved")
            return True
        except Exception as e:
            print(f"[LOCAL] Failed to save simulation data: {e}")
            return False

    bucket = get_bucket()
    blob = bucket.blob(SIMULATION_DATA_FILE)

    try:
        json_data = json.dumps(sim_data, default=str)
        blob.upload_from_string(json_data, content_type='application/json')
        print(f"[GCS] Simulation data saved")
        return True
    except Exception as e:
        print(f"[GCS] Failed to save simulation data: {e}")
        return False


def load_simulation_data() -> Optional[dict]:
    """Load persisted simulation data."""
    if USE_LOCAL_STORAGE:
        try:
            data = _local_load_json(SIMULATION_DATA_FILE)
            if data:
                print(f"[LOCAL] Loaded simulation data")
            return data
        except Exception:
            return None

    bucket = get_bucket()
    blob = bucket.blob(SIMULATION_DATA_FILE)

    try:
        json_data = blob.download_as_text()
        data = json.loads(json_data)
        print(f"[GCS] Loaded simulation data")
        return data
    except NotFound:
        return None
    except Exception as e:
        print(f"[GCS] Failed to load simulation data: {e}")
        return None


# ============== Order Holds Persistence ==============

ORDER_HOLDS_FILE = 'state/order_holds.json'


def save_order_holds(holds: dict) -> bool:
    """Save order holds. holds = {wo_number: {held_by, held_at, reason}}"""
    if USE_LOCAL_STORAGE:
        try:
            _local_save_json(ORDER_HOLDS_FILE, holds)
            print(f"[LOCAL] Saved order holds ({len(holds)} total)")
            return True
        except Exception as e:
            print(f"[LOCAL] Failed to save order holds: {e}")
            return False

    bucket = get_bucket()
    blob = bucket.blob(ORDER_HOLDS_FILE)

    try:
        json_data = json.dumps(holds, default=str)
        blob.upload_from_string(json_data, content_type='application/json')
        print(f"[GCS] Saved order holds ({len(holds)} total)")
        return True
    except Exception as e:
        print(f"[GCS] Failed to save order holds: {e}")
        return False


def load_order_holds() -> dict:
    """Load order holds."""
    if USE_LOCAL_STORAGE:
        try:
            data = _local_load_json(ORDER_HOLDS_FILE)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    bucket = get_bucket()
    blob = bucket.blob(ORDER_HOLDS_FILE)

    try:
        json_data = blob.download_as_text()
        data = json.loads(json_data)
        return data if isinstance(data, dict) else {}
    except NotFound:
        return {}
    except Exception as e:
        print(f"[GCS] Failed to load order holds: {e}")
        return {}


# ============== Notification Persistence ==============

NOTIFICATIONS_FILE = 'state/notifications.json'


def save_notifications(notifications: list) -> bool:
    """Save all notifications."""
    if USE_LOCAL_STORAGE:
        try:
            _local_save_json(NOTIFICATIONS_FILE, notifications)
            print(f"[LOCAL] Saved notifications ({len(notifications)} total)")
            return True
        except Exception as e:
            print(f"[LOCAL] Failed to save notifications: {e}")
            return False

    bucket = get_bucket()
    blob = bucket.blob(NOTIFICATIONS_FILE)

    try:
        json_data = json.dumps(notifications, default=str)
        blob.upload_from_string(json_data, content_type='application/json')
        print(f"[GCS] Saved notifications ({len(notifications)} total)")
        return True
    except Exception as e:
        print(f"[GCS] Failed to save notifications: {e}")
        return False


def load_notifications() -> list:
    """Load all notifications."""
    if USE_LOCAL_STORAGE:
        try:
            data = _local_load_json(NOTIFICATIONS_FILE)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    bucket = get_bucket()
    blob = bucket.blob(NOTIFICATIONS_FILE)

    try:
        json_data = blob.download_as_text()
        data = json.loads(json_data)
        return data if isinstance(data, list) else []
    except NotFound:
        return []
    except Exception as e:
        print(f"[GCS] Failed to load notifications: {e}")
        return []


# ============== Alert Persistence ==============

ALERTS_FILE = 'state/alerts.json'


def save_alerts(alerts: dict) -> bool:
    """Save alert report data. alerts = {generated_at, alerts: [...], summary: {...}}"""
    if USE_LOCAL_STORAGE:
        try:
            _local_save_json(ALERTS_FILE, alerts)
            print(f"[LOCAL] Saved alerts")
            return True
        except Exception as e:
            print(f"[LOCAL] Failed to save alerts: {e}")
            return False

    bucket = get_bucket()
    blob = bucket.blob(ALERTS_FILE)

    try:
        json_data = json.dumps(alerts, default=str)
        blob.upload_from_string(json_data, content_type='application/json')
        print(f"[GCS] Saved alerts")
        return True
    except Exception as e:
        print(f"[GCS] Failed to save alerts: {e}")
        return False


def load_alerts() -> Optional[dict]:
    """Load alert report data."""
    if USE_LOCAL_STORAGE:
        try:
            data = _local_load_json(ALERTS_FILE)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    bucket = get_bucket()
    blob = bucket.blob(ALERTS_FILE)

    try:
        json_data = blob.download_as_text()
        data = json.loads(json_data)
        return data if isinstance(data, dict) else None
    except NotFound:
        return None
    except Exception as e:
        print(f"[GCS] Failed to load alerts: {e}")
        return None


# ============== Schedule Reorder Persistence ==============

REORDER_STATE_FILE = 'state/reorder_state.json'


def save_reorder_state(reorder_data: dict) -> bool:
    """Save schedule reorder state. reorder_data = {mode, sequence, created_by, created_at, ...}"""
    if USE_LOCAL_STORAGE:
        try:
            _local_save_json(REORDER_STATE_FILE, reorder_data)
            print(f"[LOCAL] Saved reorder state")
            return True
        except Exception as e:
            print(f"[LOCAL] Failed to save reorder state: {e}")
            return False

    bucket = get_bucket()
    blob = bucket.blob(REORDER_STATE_FILE)

    try:
        json_data = json.dumps(reorder_data, default=str)
        blob.upload_from_string(json_data, content_type='application/json')
        print(f"[GCS] Saved reorder state")
        return True
    except Exception as e:
        print(f"[GCS] Failed to save reorder state: {e}")
        return False


def load_reorder_state() -> Optional[dict]:
    """Load schedule reorder state."""
    if USE_LOCAL_STORAGE:
        try:
            data = _local_load_json(REORDER_STATE_FILE)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    bucket = get_bucket()
    blob = bucket.blob(REORDER_STATE_FILE)

    try:
        json_data = blob.download_as_text()
        data = json.loads(json_data)
        return data if isinstance(data, dict) else None
    except NotFound:
        return None
    except Exception as e:
        print(f"[GCS] Failed to load reorder state: {e}")
        return None


def clear_reorder_state() -> bool:
    """Clear (delete) the reorder state."""
    if USE_LOCAL_STORAGE:
        return _local_delete_file(REORDER_STATE_FILE.split('/')[-1],
                                   REORDER_STATE_FILE.rsplit('/', 1)[0])

    bucket = get_bucket()
    blob = bucket.blob(REORDER_STATE_FILE)
    try:
        blob.delete()
        print(f"[GCS] Cleared reorder state")
        return True
    except NotFound:
        return True  # Already cleared
    except Exception as e:
        print(f"[GCS] Failed to clear reorder state: {e}")
        return False
