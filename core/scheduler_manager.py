# core/scheduler_manager.py

import json
import os
from datetime import datetime
from pytz import timezone, all_timezones
from filelock import FileLock

class SchedulerManager:
    def __init__(self, config_file='data/scheduler_config.json'):
        self.config_file = config_file
        self.lock = FileLock(f"{self.config_file}.lock")
        self.default_config = {
            "run_interval_seconds": 3 * 3600,  
            "exclusion_start_ist": "00:00",
            "exclusion_end_ist": "08:00",
            "is_enabled": True
        }
        self.config = self._load_config()

    def _load_config(self) -> dict:
        """Loads the configuration from the file, creating it if it doesn't exist."""
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        with self.lock:
            if not os.path.exists(self.config_file):
                with open(self.config_file, 'w') as f:
                    json.dump(self.default_config, f, indent=2)
                return self.default_config.copy()
            
            with open(self.config_file, 'r') as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    print("⚠️ Warning: scheduler_config.json is corrupted. Using default settings.")
                    return self.default_config.copy()

    def _save_config(self):
        """Saves the current in-memory config to the file."""
        with self.lock:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)

    def get_current_settings(self) -> str:
        """Returns a human-readable string of the current settings."""
        status = "✅ Enabled" if self.config['is_enabled'] else "❌ Disabled"
        interval_hours = self.config['run_interval_seconds'] / 3600
        return (
            f"--- 🗓️ Current Schedule Settings ---\n"
            f"Status: {status}\n"
            f"Run Frequency: Every {interval_hours:.1f} hours\n"
            f"Exclusion Window (IST): {self.config['exclusion_start_ist']} to {self.config['exclusion_end_ist']}"
        )

    def set_frequency(self, seconds: int) -> bool:
        """Sets the run interval in seconds."""
        if seconds < 60: return False
        self.config['run_interval_seconds'] = seconds
        self._save_config()
        return True

    def set_exclusion_window(self, start_time: str, end_time: str) -> bool:
        """Sets the exclusion window in HH:MM format."""
        try:
            # Validate time format
            datetime.strptime(start_time, '%H:%M')
            datetime.strptime(end_time, '%H:%M')
            self.config['exclusion_start_ist'] = start_time
            self.config['exclusion_end_ist'] = end_time
            self._save_config()
            return True
        except ValueError:
            return False

    def toggle_service(self, enable: bool):
        """Enables or disables the scheduled workflow runs."""
        self.config['is_enabled'] = enable
        self._save_config()

    def is_within_exclusion_window(self) -> bool:
        """Checks if the current time is within the sleep window in IST."""
        if not self.config['is_enabled']:
            print("SCHEDULER: Service is disabled by user config.")
            return True 

        try:
            ist = timezone('Asia/Kolkata')
            now_ist = datetime.now(ist)
            
            start_h, start_m = map(int, self.config['exclusion_start_ist'].split(':'))
            end_h, end_m = map(int, self.config['exclusion_end_ist'].split(':'))

            start_time = now_ist.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
            end_time = now_ist.replace(hour=end_h, minute=end_m, second=0, microsecond=0)

            # Handle overnight windows (e.g., 22:00 to 07:00)
            if start_time > end_time:
                # If current time is after start OR before end, we are in the window
                return now_ist >= start_time or now_ist <= end_time
            else:
                # Standard day window
                return start_time <= now_ist <= end_time
        except Exception as e:
            print(f"⚠️ Error checking exclusion window: {e}. Defaulting to not excluded.")
            return False

    @property
    def interval_seconds(self) -> int:
        """Returns the current run interval."""
        return self.config['run_interval_seconds']